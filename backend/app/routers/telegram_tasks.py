"""Webhook do bot de Tarefas via Telegram (Tarefas_sui_bot).

Endpoints:
  POST /telegram-tarefas/webhook          — recebe updates do Telegram
  POST /telegram-tarefas/webhook/registrar — registra o webhook no Telegram
  GET  /telegram-tarefas/webhook/status   — info do webhook atual
"""
from __future__ import annotations

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

    parts = data.split(":")
    if len(parts) < 4:
        return

    ns, kind, ref_hex, action = parts[0], parts[1], parts[2], parts[3]
    if ns != "tg":
        return

    # ── Ações de item individual (toggle na seleção) ──────────────────────
    if kind == "item" and action == "toggle":
        session = tg.get_or_create_session(db, chat_id)
        if not session.current_batch_id:
            return
        payload = dict(session.payload or {})
        selected = set(payload.get("selected_item_ids") or [])
        if ref_hex in selected:
            selected.discard(ref_hex)
        else:
            selected.add(ref_hex)
        payload["selected_item_ids"] = list(selected)
        session.payload = payload
        db.commit()

        batch = db.query(TelegramTaskBatch).filter(TelegramTaskBatch.id == session.current_batch_id).first()
        if batch:
            text_out, markup = tg.build_selection_message(db, batch.id, selected)
            tg.edit_message(chat_id, message_id, text_out, markup)
        return

    # ── Ações de lote ─────────────────────────────────────────────────────
    if kind != "batch":
        return

    batch = _batch_or_404(db, ref_hex)

    if action == "done":
        tg.edit_message(chat_id, message_id, "✅ Tarefas salvas! Veja no menu Tarefas do LexOps.")
        batch.status = "concluido"
        db.commit()
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

@router.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    _validate_secret(x_telegram_bot_api_secret_token)
    body = await request.json()
    update = _TelegramUpdate(**body)

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

    return {"ok": True}


@router.post("/webhook/registrar")
def registrar_webhook(base_url: str) -> dict:
    result = tg.register_webhook(base_url)
    return {"ok": True, "resultado": result}


@router.get("/webhook/status")
def status_webhook() -> dict:
    return tg.get_webhook_info() or {}
