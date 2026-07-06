"""Webhook do bot de Tarefas via Telegram (Tarefas_sui_bot).

Endpoints:
  POST /telegram-tarefas/webhook          — recebe updates do Telegram
  POST /telegram-tarefas/webhook/registrar — registra o webhook no Telegram
  GET  /telegram-tarefas/webhook/status   — info do webhook atual
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.telegram_task import TelegramTaskBatch
from app.services import telegram_tasks as tg

router = APIRouter(prefix="/telegram-tarefas", tags=["telegram-tarefas"])


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

class _TelegramUpdate(BaseModel):
    update_id: int | None = None
    message: dict | None = None
    callback_query: dict | None = None


def _validate_secret(secret: str | None) -> None:
    expected = settings.telegram_tarefas_webhook_secret.strip()
    if expected and secret != expected:
        raise HTTPException(status_code=403, detail="Secret inválido")


def _batch_or_404(db: Session, batch_hex: str) -> TelegramTaskBatch:
    try:
        batch_id = uuid.UUID(hex=batch_hex)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Batch inválido") from exc
    batch = db.query(TelegramTaskBatch).filter(TelegramTaskBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch não encontrado")
    return batch


def _send_batch_summary(db: Session, batch: TelegramTaskBatch, chat_id: str) -> None:
    items = tg.load_batch_items(db, batch.id)
    has_duplicates = any(item.duplicada_de_tarefa_id for item in items)
    tg.send_message(chat_id, tg.build_batch_summary(db, batch), tg.batch_actions_markup(batch, has_duplicates))


def _handle_pending_input(db: Session, chat_id: str, text: str) -> bool:
    """Verifica se há ação pendente (aguardando data ou período) e resolve."""
    from app.models.telegram_task import TelegramChatSession
    session = tg.get_or_create_session(db, chat_id)
    if not session.pending_action or not session.current_batch_id:
        return False

    batch = db.query(TelegramTaskBatch).filter(TelegramTaskBatch.id == session.current_batch_id).first()
    if not batch:
        tg.reset_session(session)
        db.commit()
        return False

    payload = session.payload or {}
    selected_ids = payload.get("selected_item_ids")

    if session.pending_action == "awaiting_fixed_date":
        parsed = tg.parse_date_input(text)
        if not parsed:
            tg.send_message(chat_id, "Não entendi a data. Envie em DD/MM, DD/MM/AAAA ou YYYY-MM-DD.", tg.default_reply_markup())
            return True
        count = tg.apply_fixed_date(db, batch.id, parsed, selected_ids)
        tg.reset_session(session)
        db.commit()
        tg.send_message(chat_id, f"✅ Data aplicada em {count} tarefa(s).")
        return True

    if session.pending_action == "awaiting_period":
        parsed_period = tg.parse_period_input(text)
        if not parsed_period:
            tg.send_message(chat_id, "Não entendi o período. Use o formato: 10/06 a 14/06", tg.default_reply_markup())
            return True
        start, end = parsed_period
        count = tg.apply_period(db, batch.id, start, end, selected_ids)
        tg.reset_session(session)
        db.commit()
        tg.send_message(chat_id, f"✅ Período aplicado em {count} tarefa(s).")
        return True

    if session.pending_action == "awaiting_responsavel":
        import re as _re
        raw = text.strip()
        if not raw:
            tg.send_message(chat_id, "Digite o nome do responsável.", tg.default_reply_markup())
            return True
        # Aceita "Nome Sobrenome <email@exemplo.com>" ou só "Nome"
        email_match = _re.search(r"<([^>]+@[^>]+)>", raw)
        email = email_match.group(1).strip() if email_match else None
        nome = _re.sub(r"\s*<[^>]+>", "", raw).strip()
        count = tg.apply_responsavel(db, batch.id, nome, email)
        tg.reset_session(session)
        db.commit()
        msg = f"✅ Responsável: {nome} ({count} tarefa(s))."
        if email:
            msg += f"\nNotificação será enviada para {email}."
        prompt_text, prompt_markup = tg.build_post_responsavel_prompt(batch)
        tg.send_message(chat_id, f"{msg}\n\n{prompt_text}", prompt_markup)
        return True

    return False


def _handle_message(db: Session, message: dict) -> None:
    chat_id = str(message["chat"]["id"])
    text = (message.get("text") or "").strip()
    message_id = message.get("message_id")

    # Comandos de info
    if text in {"/start", "/ajuda", "/help"}:
        tg.send_message(
            chat_id,
            "Olá! Mande uma lista de tarefas (uma por linha) e eu salvo tudo no LexOps.\n\n"
            "Exemplo:\n"
            "Petição Garcia\n"
            "Ligar para cliente Silva\n"
            "Revisar contrato Almeida\n\n"
            "Depois você pode definir datas em bloco ou deixar como está.",
        )
        return

    if text == "/status":
        info = tg.get_webhook_info()
        tg.send_message(chat_id, str(info))
        return

    # Se há ação pendente (data/período aguardando), resolve antes
    if _handle_pending_input(db, chat_id, text):
        return

    # Texto novo → criar lote de tarefas
    lines = tg.parse_task_lines(text)
    if not lines:
        tg.send_message(chat_id, "Não encontrei tarefas para salvar. Mande uma lista, uma por linha.")
        return

    batch, items = tg.create_batch_from_text(db, chat_id, message_id, text)
    _send_batch_summary(db, batch, chat_id)


def _handle_callback(db: Session, callback_query: dict) -> None:
    from app.models.telegram_task import TelegramChatSession
    query_id = callback_query["id"]
    chat_id = str(callback_query["message"]["chat"]["id"])
    message_id = callback_query["message"]["message_id"]
    data = callback_query.get("data", "")

    tg.answer_callback(query_id)

    # tg:global:skip
    if data == "tg:global:skip":
        tg.edit_message(chat_id, message_id, "Ok, tarefas salvas sem alteração.")
        return

    # Limita a 4 segmentos para que nomes com ":" (raro mas possível) não quebrem o parse.
    # Ex: "tg:batch:{hex}:resp_set:Lucas" → action = "resp_set:Lucas"
    parts = data.split(":", 3)
    if len(parts) < 4:
        return

    ns, kind, ref_hex, action = parts
    if ns != "tg":
        return

    # ── Ações de item individual (toggle + vínculo com macro) ────────────
    if kind == "item":
        item_hex = ref_hex
        # toggle de seleção (lógica existente)
        if action == "toggle":
            session = tg.get_or_create_session(db, chat_id)
            if not session.current_batch_id:
                return
            payload = dict(session.payload or {})
            selected = set(payload.get("selected_item_ids") or [])
            if item_hex in selected:
                selected.discard(item_hex)
            else:
                selected.add(item_hex)
            payload["selected_item_ids"] = list(selected)
            session.payload = payload
            db.commit()
            batch = db.query(TelegramTaskBatch).filter(TelegramTaskBatch.id == session.current_batch_id).first()
            if batch:
                text_out, markup = tg.build_selection_message(db, batch.id, selected)
                tg.edit_message(chat_id, message_id, text_out, markup)
            return

        # card_proj — pede filtro de projeto para vincular a uma macro
        if action == "card_proj":
            try:
                uuid.UUID(hex=item_hex)
            except ValueError:
                return
            text_out, markup = tg.build_projeto_menu_for_item(db, item_hex)
            tg.edit_message(chat_id, message_id, text_out, markup)
            return

        # card_p:<idx|all> — escolheu projeto (ou sem filtro), mostra macros
        if action.startswith("card_p:"):
            proj_part = action[len("card_p:"):]
            projeto_id = None
            if proj_part != "all":
                try:
                    idx = int(proj_part)
                    projetos = tg._active_projetos(db)
                    if idx < len(projetos):
                        projeto_id = projetos[idx].id
                except ValueError:
                    pass
            try:
                uuid.UUID(hex=item_hex)
            except ValueError:
                return
            # Guarda o projeto escolhido na sessão para o handler card_m reconstruir
            # exatamente a mesma lista filtrada (senão os índices não batem).
            session = tg.get_or_create_session(db, chat_id)
            payload = dict(session.payload or {})
            payload["card_link_projeto_id"] = str(projeto_id) if projeto_id else None
            session.payload = payload
            db.commit()
            text_out, markup = tg.build_macro_menu_for_item(db, item_hex, projeto_id)
            tg.edit_message(chat_id, message_id, text_out, markup)
            return

        # card_m:<idx> — escolheu macro, vincula e volta ao menu do lote
        if action.startswith("card_m:"):
            try:
                macro_idx = int(action[len("card_m:"):])
                item_id = uuid.UUID(hex=item_hex)
            except ValueError:
                tg.edit_message(chat_id, message_id, "Erro. Tente novamente.")
                return
            from app.models.telegram_task import TelegramTaskItem as _Item
            item = db.query(_Item).filter(_Item.id == item_id).first()
            if not item:
                tg.edit_message(chat_id, message_id, "Item não encontrado.")
                return
            # Reconstrói a MESMA lista filtrada que foi mostrada ao usuário
            session = tg.get_or_create_session(db, chat_id)
            payload = session.payload or {}
            projeto_id_str = payload.get("card_link_projeto_id")
            projeto_id = uuid.UUID(projeto_id_str) if projeto_id_str else None
            macros = tg._open_macros(db, projeto_id)
            if macro_idx >= len(macros):
                tg.edit_message(chat_id, message_id, "Macro não encontrada.")
                return
            macro = macros[macro_idx]
            tg.link_item_to_macro(db, item, macro)
            # Volta ao menu de vínculo do lote para continuar com outras tarefas
            session = tg.get_or_create_session(db, chat_id)
            if session.current_batch_id:
                batch = db.query(TelegramTaskBatch).filter(TelegramTaskBatch.id == session.current_batch_id).first()
                if batch:
                    text_out, markup = tg.build_card_link_menu(db, batch)
                    tg.edit_message(chat_id, message_id, f"✅ Vinculado a: {macro.titulo}\n\n{text_out}", markup)
                    return
            tg.edit_message(chat_id, message_id, f"✅ Vinculado a: {macro.titulo}")
            return

        # card_cancel — mantém como card avulso, volta ao menu do lote
        if action == "card_cancel":
            session = tg.get_or_create_session(db, chat_id)
            if session.current_batch_id:
                batch = db.query(TelegramTaskBatch).filter(TelegramTaskBatch.id == session.current_batch_id).first()
                if batch:
                    text_out, markup = tg.build_card_link_menu(db, batch)
                    tg.edit_message(chat_id, message_id, text_out, markup)
                    return
            tg.edit_message(chat_id, message_id, "Ok, mantido como card avulso.")
            return

        return  # item action não reconhecida

    # ── Ações de lote ─────────────────────────────────────────────────────
    if kind != "batch":
        return

    batch = _batch_or_404(db, ref_hex)

    if action == "done":
        tg.edit_message(chat_id, message_id, "✅ Tarefas salvas! Veja no menu Tarefas e Tarefas em Cards do LexOps.")
        batch.status = "concluido"
        db.commit()
        return

    if action == "resp":
        text_out, markup = tg.build_responsavel_menu(db, batch.id)
        tg.edit_message(chat_id, message_id, text_out, markup)
        return

    # resp_set:<idx> — clicou num usuário da lista (índice numérico para caber nos 64 bytes)
    if action.startswith("resp_set:"):
        try:
            idx = int(action[len("resp_set:"):])
        except ValueError:
            tg.edit_message(chat_id, message_id, "Erro ao identificar usuário. Tente novamente.")
            return
        usuarios = tg._active_usuarios(db)
        if idx >= len(usuarios):
            tg.edit_message(chat_id, message_id, "Usuário não encontrado.")
            return
        u = usuarios[idx]
        count = tg.apply_responsavel(db, batch.id, u.nome, u.email)
        # Dispara emails em background para cada tarefa do lote
        import threading
        from app.services.tarefa_email import notificar_responsavel
        from app.database import SessionLocal
        items = tg.load_batch_items(db, batch.id)
        tarefa_ids = [item.tarefa_id for item in items]
        def _enviar_lote():
            _db = SessionLocal()
            try:
                from app.models.tarefa import Tarefa
                for tid in tarefa_ids:
                    _t = _db.query(Tarefa).filter(Tarefa.id == tid).first()
                    if _t and _t.responsavel_email:
                        notificar_responsavel(_db, _t, dry_run=False)
            finally:
                _db.close()
        threading.Thread(target=_enviar_lote, daemon=True).start()

        prompt_text, prompt_markup = tg.build_post_responsavel_prompt(batch)
        tg.edit_message(
            chat_id, message_id,
            f"✅ Responsável: {u.nome} ({count} tarefa(s)).\nEmail de notificação será enviado para {u.email}.\n\n{prompt_text}",
            prompt_markup,
        )
        return

    if action == "resp_custom":
        session = tg.get_or_create_session(db, chat_id)
        session.pending_action = "awaiting_responsavel"
        session.current_batch_id = batch.id
        db.commit()
        tg.send_message(chat_id, "Digite o nome do responsável (e email se quiser notificação, ex: João Silva <joao@email.com>):", tg.default_reply_markup())
        return

    if action == "card_link":
        text_out, markup = tg.build_card_link_menu(db, batch)
        tg.edit_message(chat_id, message_id, text_out, markup)
        return

    if action == "dates":
        text_out, markup = tg.build_dates_menu(batch.id, selected_mode=False)
        tg.edit_message(chat_id, message_id, text_out, markup)
        return

    if action == "select":
        session = tg.get_or_create_session(db, chat_id)
        session.payload = {"selected_item_ids": []}
        db.commit()
        text_out, markup = tg.build_selection_message(db, batch.id, set())
        tg.edit_message(chat_id, message_id, text_out, markup)
        return

    if action == "selected_dates":
        session = tg.get_or_create_session(db, chat_id)
        payload = session.payload or {}
        selected = payload.get("selected_item_ids")
        if not selected:
            tg.edit_message(chat_id, message_id, "Selecione ao menos uma tarefa antes.")
            return
        text_out, markup = tg.build_dates_menu(batch.id, selected_mode=True)
        tg.edit_message(chat_id, message_id, text_out, markup)
        return

    if action == "clear_selection":
        session = tg.get_or_create_session(db, chat_id)
        session.payload = {"selected_item_ids": []}
        db.commit()
        text_out, markup = tg.build_selection_message(db, batch.id, set())
        tg.edit_message(chat_id, message_id, text_out, markup)
        return

    if action == "dupes":
        items = tg.load_batch_items(db, batch.id)
        dupe_items = [item for item in items if item.duplicada_de_tarefa_id]
        lines = ["Possíveis duplicadas detectadas:", ""]
        for item in dupe_items:
            score_pct = int((item.duplicada_score or 0) * 100)
            lines.append(f"• {item.titulo_original} ({score_pct}% similar)")
        lines.append("")
        lines.append("Deseja remover as duplicadas?")
        markup = {"inline_keyboard": [
            [
                {"text": "🗑 Remover duplicadas", "callback_data": f"tg:batch:{batch.id.hex}:drop_dupes"},
                {"text": "Manter todas", "callback_data": f"tg:batch:{batch.id.hex}:done"},
            ]
        ]}
        tg.edit_message(chat_id, message_id, "\n".join(lines), markup)
        return

    if action == "drop_dupes":
        removed = tg.drop_probable_duplicates(db, batch.id)
        tg.edit_message(chat_id, message_id, f"🗑 {removed} tarefa(s) duplicada(s) removida(s).")
        return

    # Ações de data (sem seleção ou com seleção via sel_ prefix)
    selected_mode = action.startswith("sel_")
    date_action = action[4:] if selected_mode else action  # remove "sel_"

    session = tg.get_or_create_session(db, chat_id)
    payload = dict(session.payload or {})
    selected_ids = payload.get("selected_item_ids") if selected_mode else None

    if date_action in {"open", "today", "tomorrow", "week"}:
        count = tg.apply_date_mode(db, batch.id, date_action, selected_ids)
        label = {"open": "sem data", "today": "hoje", "tomorrow": "amanhã", "week": "esta semana"}[date_action]
        tg.edit_message(chat_id, message_id, f"✅ {count} tarefa(s) marcada(s) para {label}.")
        tg.reset_session(session)
        db.commit()
        return

    if date_action == "fixed":
        session.pending_action = "awaiting_fixed_date"
        if selected_mode:
            payload["selected_item_ids"] = selected_ids
        session.payload = payload
        session.current_batch_id = batch.id
        db.commit()
        tg.send_message(chat_id, "Digite a data (DD/MM ou DD/MM/AAAA):", tg.default_reply_markup())
        return

    if date_action == "period":
        session.pending_action = "awaiting_period"
        if selected_mode:
            payload["selected_item_ids"] = selected_ids
        session.payload = payload
        session.current_batch_id = batch.id
        db.commit()
        tg.send_message(chat_id, "Digite o período (ex: 10/06 a 14/06):", tg.default_reply_markup())
        return


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _process_update(update: _TelegramUpdate) -> None:
    """Processamento síncrono (DB + chamadas HTTP ao Telegram) rodado fora do event loop."""
    db: Session = SessionLocal()
    try:
        if update.message:
            _handle_message(db, update.message)
        elif update.callback_query:
            _handle_callback(db, update.callback_query)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("Erro no webhook de tarefas: %s", exc)
    finally:
        db.close()


@router.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    _validate_secret(x_telegram_bot_api_secret_token)
    body = await request.json()
    update = _TelegramUpdate(**body)

    # _process_update faz DB queries síncronas e chamadas HTTP bloqueantes ao
    # Telegram (answer_callback + edit_message, cada uma até 20s de timeout).
    # Rodar isso direto num "async def" travaria o event loop inteiro — toda
    # outra requisição ao LexOps (inclusive o frontend) ficaria parada até
    # terminar. asyncio.to_thread despacha para uma worker thread e libera
    # o loop imediatamente, evitando o travamento que fazia parecer necessário
    # clicar 2x no bot.
    await asyncio.to_thread(_process_update, update)

    return {"ok": True}


@router.post("/webhook/registrar")
def registrar_webhook(base_url: str) -> dict:
    result = tg.register_webhook(base_url)
    return {"ok": True, "resultado": result}


@router.get("/webhook/status")
def status_webhook() -> dict:
    return tg.get_webhook_info() or {}
