"""Bot de Reembolsos no Telegram.

Arquitetura de performance:
  • Callbacks (botões) e texto → síncronos no webhook → resposta em <1s
  • Fotos → APENAS o download + visão IA vai em background thread
  • Lock por chat apenas durante a visão (5-10s), NÃO durante a interação

Fluxo:
  foto(s) → enfileira rápido → visão IA (background) → "imagem X de N, R$ Y. É?"
    nova  → Cliente → Natureza → Pasta → Descrição → Valor → Confirma → grava
    add   → Cliente → despesa em aberto (⬅️ ou nova) → anexa doc
  ao confirmar: se há próxima na fila, inicia visão da próxima (background)
  ao final do lote: mostra totais por pasta e opção de enviar cobrança

Comandos: /manual /pendentes /resumo /cancelar /ajuda
"""
from __future__ import annotations

import asyncio
import copy
import difflib
import re
import threading
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from sqlalchemy import func as sa_func

from app.config import settings
from app.database import SessionLocal
from app.models.cliente import Cliente
from app.models.reembolso import ComprovanteItem, ItemReembolso, Reembolso
from app.models.telegram_conversa import TelegramConversa, TelegramDoc
from app.services import ia_reembolso, telegram_api
from app.services.ia_reembolso import NATUREZAS
from app.routers.reembolsos import (
    BCC_EMAIL_FIXO,
    UPLOADS_DIR,
    _build_email_html,
    _fmt_brl,
    _get_pdf_with_drive_link,
    _refresh_if_needed,
    _reembolso_folder_name,
    _send_gmail,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])

OPEN_STATUSES = ("rascunho", "aguardando_pagamento")
TZ_BR = ZoneInfo("America/Sao_Paulo")

# Lock per-chat: só mantido durante download + visão IA (5-10s máx).
# Callbacks e texto NÃO usam este lock — rodam síncronos.
_vision_locks: dict[int, threading.Lock] = {}
_vision_locks_guard = threading.Lock()


def _vision_lock(chat_id: int) -> threading.Lock:
    with _vision_locks_guard:
        if chat_id not in _vision_locks:
            _vision_locks[chat_id] = threading.Lock()
        return _vision_locks[chat_id]


# ── Timezone ──────────────────────────────────────────────────────────────────

def _now_br() -> datetime:
    return datetime.now(TZ_BR)


def _fmt_dt_br(dt: datetime | None = None) -> str:
    dt = dt or _now_br()
    return dt.strftime("%d/%m %H:%M")


# ── Estado da conversa ────────────────────────────────────────────────────────

def _get_conversa(db: Session, chat_id: int) -> TelegramConversa:
    c = db.query(TelegramConversa).filter(TelegramConversa.chat_id == chat_id).first()
    if not c:
        c = TelegramConversa(chat_id=chat_id, state="idle", data={})
        db.add(c)
        db.commit()
        db.refresh(c)
    return c


def _save(db: Session, c: TelegramConversa, state: str, data: dict) -> None:
    c.state = state
    c.data = data
    flag_modified(c, "data")
    db.add(c)
    db.commit()


def _reset(db: Session, c: TelegramConversa) -> None:
    _save(db, c, "idle", {})


def _draft(data: dict) -> dict:
    d = data.get("draft")
    if not isinstance(d, dict):
        d = {}
        data["draft"] = d
    return d


# ── Clientes ──────────────────────────────────────────────────────────────────

def _match_clientes(db: Session, query: str | None, limit: int = 6) -> list[Cliente]:
    """Busca clientes com ILIKE no banco — evita carregar todos para Python."""
    if not query:
        return db.query(Cliente).order_by(Cliente.nome).limit(limit).all()
    q = query.strip()
    # Busca ILIKE (usa índice quando disponível)
    resultados = (
        db.query(Cliente)
        .filter(sa_func.lower(Cliente.nome).contains(q.lower()))
        .order_by(Cliente.nome)
        .limit(limit)
        .all()
    )
    if resultados:
        return resultados
    # Fallback fuzzy só se ILIKE não achou nada
    todos = db.query(Cliente).order_by(Cliente.nome).all()
    ranked = sorted(
        todos,
        key=lambda c: difflib.SequenceMatcher(None, q.lower(), (c.nome or "").lower()).ratio(),
        reverse=True,
    )
    return ranked[:limit]


def _clientes_com_pasta_aberta(db: Session) -> list[Cliente]:
    """Retorna apenas clientes que têm pelo menos uma pasta em aberto."""
    ids = (
        db.query(Reembolso.cliente_id)
        .filter(Reembolso.status.in_(OPEN_STATUSES))
        .distinct()
        .all()
    )
    if not ids:
        return []
    return (
        db.query(Cliente)
        .filter(Cliente.id.in_([r.cliente_id for r in ids]))
        .order_by(Cliente.nome)
        .all()
    )


def _botoes_clientes(clientes: list[Cliente]) -> list[list[tuple[str, str]]]:
    botoes = [[(f"👤 {c.nome}", f"cli:{c.id}")] for c in clientes]
    botoes.append([("🔍 Digitar nome", "cli:busca")])
    return botoes


# ── Render ────────────────────────────────────────────────────────────────────

def _progresso(data: dict) -> str:
    total = data.get("batch_total", 1)
    if total <= 1:
        return ""
    done = data.get("batch_done", 0)
    return f"🧾 *Imagem {done + 1} de {total}*\n"


def _ref_valor(draft: dict) -> str:
    v = draft.get("valor")
    return _fmt_brl(float(v)) if v is not None else "valor a definir"


def _resumo_rascunho(draft: dict) -> str:
    docs = [d for d in [draft.get("doc")] + draft.get("extra_docs", []) if d]
    return (
        "*Resumo da despesa*\n"
        f"👤 {draft.get('cliente_nome', '—')}\n"
        f"🏷️ {draft.get('natureza', '—')}\n"
        f"📝 {draft.get('descricao', '—')}\n"
        f"💰 {_ref_valor(draft)}\n"
        f"📎 {len(docs)} comprovante(s)"
    )


def _ctx_lote(data: dict) -> str:
    """Linha de contexto resumida do lote/despesa atual para mensagens de feedback.
    Ex: "lote de 3 comprovante(s) • R$ 150,00 • João Silva"
    """
    partes = []
    total = data.get("batch_total", 0)
    done = data.get("batch_done", 0)
    fila = len(data.get("queue", []))
    processados = done + (1 if isinstance(data.get("draft"), dict) and data["draft"] else 0)
    if total > 0:
        partes.append(f"lote de {total} comprovante(s)")
        if processados > 0:
            partes.append(f"{processados} já processado(s)")
        if fila > 0:
            partes.append(f"{fila} na fila")
    draft = data.get("draft")
    if isinstance(draft, dict) and draft:
        if draft.get("cliente_nome"):
            partes.append(draft["cliente_nome"])
        if draft.get("valor") is not None:
            partes.append(_fmt_brl(float(draft["valor"])))
    touched = data.get("touched", [])
    if touched and not draft:
        partes.append(f"{len(touched)} pasta(s) em aberto")
    return " • ".join(partes) if partes else "nenhuma despesa em andamento"


def _titulo_pasta(cliente_nome: str) -> str:
    return f"Reembolso {cliente_nome} - Inclusão Automática {_fmt_dt_br()}"


# ── Persistência ──────────────────────────────────────────────────────────────

def _gravar_despesa(db: Session, draft: dict) -> Reembolso:
    cliente = db.query(Cliente).filter(Cliente.id == uuid.UUID(draft["cliente_id"])).first()

    reembolso_id = draft.get("reembolso_id")
    if reembolso_id:
        r = db.query(Reembolso).filter(Reembolso.id == uuid.UUID(reembolso_id)).first()
    else:
        r = Reembolso(
            cliente_id=cliente.id,
            titulo=_titulo_pasta(cliente.nome),
            data_emissao=date.today(),
            status="rascunho",
        )
        db.add(r)
        db.commit()
        db.refresh(r)

    data_despesa = date.today()
    draft.pop("data_invalida", None)
    if draft.get("data_despesa"):
        try:
            data_despesa = date.fromisoformat(str(draft["data_despesa"]).strip())
        except (TypeError, ValueError):
            # Data inexistente/ilegível (ex.: "2026-06-31"). Cai para hoje e
            # sinaliza para o caller avisar o usuário em vez de gravar lixo.
            draft["data_invalida"] = str(draft["data_despesa"])

    item = ItemReembolso(
        reembolso_id=r.id,
        data=data_despesa,
        descricao=draft.get("descricao") or "Despesa",
        natureza=draft.get("natureza") or "Outros",
        valor=float(draft.get("valor") or 0),
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    docs = [d for d in [draft.get("doc")] + draft.get("extra_docs", []) if d]
    _anexar_docs(db, r, item, docs)
    db.commit()
    db.refresh(r)
    return r


def _anexar_docs(db: Session, r: Reembolso, item: ItemReembolso, docs: list[dict]) -> None:
    from app.services.google_drive import get_folder_link, upload_arquivo
    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
    folder_name = _reembolso_folder_name(r)
    for idx, doc in enumerate(docs):
        conteudo = telegram_api.download_file(doc["file_id"])
        if not conteudo:
            continue
        filename = doc.get("filename") or f"comprovante_{idx + 1}.jpg"
        ext = Path(filename).suffix or ".jpg"
        mime = doc.get("mime") or "image/jpeg"
        nome_arquivo = f"comprovante_{item.id}_{idx + 1}{ext}"
        destino = UPLOADS_DIR / nome_arquivo
        destino.write_bytes(conteudo)
        if item.comprovante_path is None:
            item.comprovante_path = str(destino)
            if not item.documento_comprobatorio:
                item.documento_comprobatorio = filename
        drive_link = None
        try:
            if cliente:
                drive_link = upload_arquivo(
                    conteudo, nome_arquivo, cliente.nome, "Reembolsos", mime,
                    sub_subfolder=folder_name,
                )
                # Guarda o link da pasta no reembolso logo no primeiro upload
                if not r.drive_link:
                    link = get_folder_link(cliente.nome, "Reembolsos", sub_subfolder=folder_name)
                    if link:
                        r.drive_link = link
        except Exception:
            pass
        db.add(ComprovanteItem(
            item_id=item.id, filename=filename, file_path=str(destino),
            drive_link=drive_link, mime=mime,
        ))
        if doc.get("row_id"):
            row = db.query(TelegramDoc).filter(TelegramDoc.id == uuid.UUID(doc["row_id"])).first()
            if row:
                row.status = "catalogado"
                row.item_id = item.id
    db.commit()


def _enviar_cobranca(db: Session, r: Reembolso) -> str:
    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
    if not cliente or not cliente.email:
        return "⚠️ Cliente sem e-mail cadastrado. Cadastre no sistema para enviar."
    pdf_bytes = _get_pdf_with_drive_link(r, db)
    nome_arquivo = f"nota_reembolso_{r.id}.pdf"
    destino = UPLOADS_DIR / nome_arquivo
    destino.write_bytes(pdf_bytes)
    r.pdf_path = str(destino)
    try:
        from app.services.google_drive import get_folder_link, upload_pdf
        folder_name = _reembolso_folder_name(r)
        upload_pdf(pdf_bytes, nome_arquivo, cliente.nome, "Reembolsos", sub_subfolder=folder_name)
        r.drive_link = get_folder_link(cliente.nome, "Reembolsos", sub_subfolder=folder_name)
    except Exception:
        pass
    db.commit()
    access_token = _refresh_if_needed()
    if not access_token:
        return "⚠️ Google não autenticado. Faça OAuth em /auth/google."
    try:
        _send_gmail(
            access_token=access_token,
            to=cliente.email,
            subject=f"Nota de Reembolso — {r.titulo}",
            html=_build_email_html(r),
            pdf_bytes=pdf_bytes,
            pdf_filename=f"Nota de Reembolso - {cliente.nome}.pdf",
            bcc=[BCC_EMAIL_FIXO],
        )
    except Exception as e:
        return f"❌ Falha ao enviar: {e}"
    from datetime import timezone
    r.status = "enviado"
    r.email_destinatario = cliente.email
    r.ultimo_lembrete_em = datetime.now(timezone.utc)
    db.commit()
    return f"✅ Cobrança enviada para *{cliente.email}* — total {_fmt_brl(r.total)}."


# ── Webhook ───────────────────────────────────────────────────────────────────

@router.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    if settings.telegram_webhook_secret:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.telegram_webhook_secret:
            return {"ok": True}
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    if "callback_query" in update:
        # Botões: processamento continua síncrono e rápido (<1s), mas despachado
        # para uma worker thread — _run faz queries SQLAlchemy sync e chamadas
        # HTTP bloqueantes ao Telegram; rodar isso direto num "async def" travaria
        # o event loop inteiro (toda outra requisição do LexOps ficaria parada
        # até terminar). asyncio.to_thread libera o loop imediatamente.
        await asyncio.to_thread(_run, update)
    elif "message" in update:
        has_media = bool(update["message"].get("photo") or update["message"].get("document"))
        if has_media:
            # Fotos: enfileira SINCRONAMENTE (fast), visão IA em background
            background_tasks.add_task(_run_vision, update)
        else:
            await asyncio.to_thread(_run, update)
    return {"ok": True}


def _run(update: dict) -> None:
    """Processa callbacks e texto síncronos — sem lock."""
    db = SessionLocal()
    try:
        if "callback_query" in update:
            _handle_callback(db, update["callback_query"])
        else:
            _handle_message(db, update["message"])
    except Exception:
        import traceback; traceback.print_exc()
    finally:
        db.close()


def _run_vision(update: dict) -> None:
    """Processa fotos em background com lock por chat (apenas para visão IA)."""
    chat_id = update["message"]["chat"]["id"]
    with _vision_lock(chat_id):
        db = SessionLocal()
        try:
            _handle_message(db, update["message"])
        except Exception:
            import traceback; traceback.print_exc()
        finally:
            db.close()


def _autorizado(user_id: int, chat_id: int | None = None) -> bool:
    """Autoriza se:
    - Nenhum filtro configurado (dev/teste) → libera tudo
    - user_id está na lista individual, OU
    - chat_id é um grupo autorizado (qualquer membro do grupo é aceito)
    """
    allowed_users = settings.telegram_allowed_ids
    allowed_groups = settings.telegram_allowed_group_ids_set
    if not allowed_users and not allowed_groups:
        return True  # sem configuração → libera (dev)
    if allowed_users and user_id in allowed_users:
        return True
    if allowed_groups and chat_id is not None and chat_id in allowed_groups:
        return True
    return False


# ── Mensagens ─────────────────────────────────────────────────────────────────

def _extrair_doc(message: dict) -> dict | None:
    if message.get("photo"):
        maior = message["photo"][-1]
        return {"file_id": maior["file_id"], "file_unique_id": maior.get("file_unique_id"),
                "filename": "foto.jpg", "mime": "image/jpeg"}
    if "document" in message:
        doc = message["document"]
        return {"file_id": doc["file_id"], "file_unique_id": doc.get("file_unique_id"),
                "filename": doc.get("file_name", "documento"),
                "mime": doc.get("mime_type", "application/octet-stream")}
    return None


def _handle_message(db: Session, message: dict) -> None:
    user_id = message.get("from", {}).get("id")
    chat_id = message["chat"]["id"]
    if not _autorizado(user_id, chat_id):
        return

    c = _get_conversa(db, chat_id)
    data = copy.deepcopy(c.data or {})
    texto = (message.get("text") or message.get("caption") or "").strip()
    doc = _extrair_doc(message)

    low = texto.lower()
    if low.startswith("/cancelar") or low.startswith("/cancel"):
        ctx = _ctx_lote(data)
        _reset(db, c)
        telegram_api.send_message(chat_id, f"❌ Lote cancelado.\n_{ctx}_")
        return
    if low.startswith("/ajuda") or low.startswith("/start") or low.startswith("/help"):
        telegram_api.send_message(chat_id, _AJUDA)
        return
    if low.startswith("/pendentes"):
        _listar_pendentes(db, c, chat_id)
        return
    if low.startswith("/resumo"):
        _listar_resumo(db, chat_id)
        return
    if low.startswith("/manual"):
        _iniciar_manual(db, c, data, chat_id, texto[len("/manual"):].strip())
        return
    if low.startswith("catalogar"):
        _iniciar_manual(db, c, data, chat_id, texto)
        return

    if doc:
        _on_doc(db, c, data, chat_id, doc, texto)
        return

    # Texto livre no idle: tenta detectar se parece uma despesa e inicia /manual.
    # Ignora mensagens muito curtas (≤3 palavras) para não spammar o grupo com
    # conversas normais que não sejam despesas.
    if c.state == "idle" and texto and _parece_despesa(texto):
        _iniciar_manual(db, c, data, chat_id, texto)
        return

    if c.state == "cliente_busca":
        clientes = _match_clientes(db, texto)
        if not clientes:
            telegram_api.send_message(chat_id, "Nenhum cliente encontrado. Tente outro nome.")
            return
        _save(db, c, "cliente", data)
        telegram_api.send_message(chat_id, "Selecione o cliente:", _botoes_clientes(clientes))
        return

    if c.state == "descricao_edit":
        _draft(data)["descricao"] = ia_reembolso.limpar_descricao(texto)
        _ir_para_valor(db, c, data, chat_id)
        return

    if c.state == "valor_edit":
        valor = _parse_valor(texto)
        if valor is None:
            telegram_api.send_message(chat_id, "Não entendi. Envie só o número, ex: 150,00")
            return
        _draft(data)["valor"] = valor
        _ir_para_confirmacao(db, c, data, chat_id)
        return


def _on_doc(db: Session, c: TelegramConversa, data: dict, chat_id: int, doc: dict, caption: str) -> None:
    # Registra no TelegramDoc para /pendentes
    row = TelegramDoc(
        chat_id=chat_id, file_id=doc["file_id"], file_unique_id=doc.get("file_unique_id"),
        filename=doc.get("filename"), mime=doc.get("mime"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    doc["row_id"] = str(row.id)
    if caption:
        doc["caption"] = caption

    # Se há draft ativo, acumula como extra doc
    if isinstance(data.get("draft"), dict) and data["draft"]:
        d = data["draft"]
        d.setdefault("extra_docs", []).append(doc)
        data.setdefault("batch_total", 1)
        data["batch_total"] += 1
        _save(db, c, c.state, data)
        ref = f"despesa de *{_ref_valor(d)}*" + (f" — {d['cliente_nome']}" if d.get("cliente_nome") else "")
        total_docs = 1 + len(d["extra_docs"])
        telegram_api.send_message(
            chat_id,
            f"📎 Acumulado na {ref} ({total_docs} doc(s) no total).\n"
            "Para despesa nova, finalize a atual primeiro."
        )
        return

    # Enfileira (o lock de visão garante que só um é processado por vez)
    data.setdefault("queue", []).append(doc)
    data["batch_total"] = data.get("batch_total", 0) + 1
    _save(db, c, c.state, data)

    # Se já há outro sendo processado, só notifica
    if data.get("draft"):
        d = data["draft"]
        ref = f"despesa de *{_ref_valor(d)}*" + (f" — {d['cliente_nome']}" if d.get("cliente_nome") else "")
        telegram_api.send_message(
            chat_id,
            f"📥 Na fila (posição {len(data['queue'])}). Processo após a {ref}."
        )
        return

    # Inicia visão para este doc (já estamos no background thread com lock)
    _processar_proximo(db, c, data, chat_id)


def _processar_proximo(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    """Pega o próximo doc da fila e inicia o fluxo ou encerra lote."""
    fila: list = data.get("queue", [])
    if not fila:
        _mostrar_lote_fim(db, c, data, chat_id)
        return

    doc = fila.pop(0)
    draft: dict = {"doc": doc, "extra_docs": [], "mode": "nova"}
    if doc.get("caption"):
        draft["descricao_seed"] = doc["caption"]

    telegram_api.send_message(
        chat_id,
        f"⏳ Lendo comprovante ({data.get('batch_done', 0) + 1}/{data.get('batch_total', 1)})…"
    )
    conteudo = telegram_api.download_file(doc["file_id"])
    vision = ia_reembolso.extrair_dados(conteudo, doc.get("mime", ""), doc.get("caption")) if conteudo else {}
    draft["vision"] = vision
    if vision.get("valor") is not None:
        draft["valor"] = vision["valor"]
        if doc.get("row_id"):
            row = db.query(TelegramDoc).filter(TelegramDoc.id == uuid.UUID(doc["row_id"])).first()
            if row:
                row.valor_detectado = vision["valor"]
                db.commit()
    if vision.get("data"):
        draft["data_despesa"] = vision["data"]
    if vision.get("natureza") in NATUREZAS:
        draft["natureza"] = vision["natureza"]

    data["draft"] = draft
    _save(db, c, "tipo", data)
    telegram_api.send_message(
        chat_id,
        f"{_progresso(data)}📄 Comprovante de *{_ref_valor(draft)}*. Esse documento é:",
        [
            [("🆕 Despesa nova", "tipo:nova")],
            [("📎 Anexar a despesa já salva", "tipo:add")],
            [("❌ Cancelar lote", "fim:cancel")],
        ],
    )


# ── Callbacks ─────────────────────────────────────────────────────────────────

def _handle_callback(db: Session, cq: dict) -> None:
    user_id = cq.get("from", {}).get("id")
    chat_id = cq.get("message", {}).get("chat", {}).get("id")
    cb_id = cq.get("id")
    payload = cq.get("data", "")

    if not _autorizado(user_id, chat_id):
        telegram_api.answer_callback(cb_id, "Não autorizado.")
        return
    telegram_api.answer_callback(cb_id)

    c = _get_conversa(db, chat_id)
    data = copy.deepcopy(c.data or {})
    draft = _draft(data)

    if ":" not in payload:
        return
    prefixo, valor = payload.split(":", 1)

    if prefixo == "tipo":
        draft["mode"] = "nova" if valor == "nova" else "add"
        _save(db, c, "cliente", data)
        if draft["mode"] == "add":
            # "Anexar": só mostra clientes com pasta em aberto
            clientes = _clientes_com_pasta_aberta(db)
            if not clientes:
                telegram_api.send_message(
                    chat_id,
                    f"Nenhum cliente tem pasta em aberto. Tratando como despesa nova — *{_ref_valor(draft)}*.",
                )
                draft["mode"] = "nova"
                clientes = _match_clientes(db, (draft.get("vision") or {}).get("cliente_nome"))
            telegram_api.send_message(chat_id, "Qual o cliente (com pasta aberta)?", _botoes_clientes(clientes))
        else:
            # "Nova": IA tenta sugerir o cliente pelo comprovante
            clientes = _match_clientes(db, (draft.get("vision") or {}).get("cliente_nome"))
            telegram_api.send_message(chat_id, "Qual o cliente?", _botoes_clientes(clientes))
        return

    if prefixo == "cli":
        if valor == "busca":
            _save(db, c, "cliente_busca", data)
            telegram_api.send_message(chat_id, "Digite parte do nome do cliente:")
            return
        cliente = db.query(Cliente).filter(Cliente.id == uuid.UUID(valor)).first()
        if not cliente:
            telegram_api.send_message(chat_id, "Cliente não encontrado.")
            return
        draft["cliente_id"] = str(cliente.id)
        draft["cliente_nome"] = cliente.nome
        if draft.get("mode") == "add":
            _passo_add_despesa(db, c, data, chat_id)
        else:
            _passo_natureza(db, c, data, chat_id)
        return

    if prefixo == "nat":
        try:
            draft["natureza"] = NATUREZAS[int(valor)]
        except (ValueError, IndexError):
            draft["natureza"] = "Outros"
        _passo_pasta(db, c, data, chat_id)
        return

    if prefixo == "pasta":
        draft["reembolso_id"] = None if valor == "new" else valor
        _passo_descricao(db, c, data, chat_id)
        return

    if prefixo == "desc":
        if valor == "edit":
            _save(db, c, "descricao_edit", data)
            telegram_api.send_message(chat_id, "Escreva a descrição:")
            return
        _ir_para_valor(db, c, data, chat_id)
        return

    if prefixo == "val":
        if valor == "edit":
            _save(db, c, "valor_edit", data)
            telegram_api.send_message(chat_id, "Qual o valor? (ex: 150,00)")
            return
        _checar_duplicata_e_confirmar(db, c, data, chat_id)
        return

    if prefixo == "dup":
        if valor == "ok":
            # Usuário confirmou que é duplicata intencional — descarta
            ctx = _ctx_lote(data)
            _reset(db, c)
            telegram_api.send_message(chat_id, f"🗑️ Despesa descartada (duplicata confirmada).\n_{ctx}_")
        else:  # nova
            # Usuário confirmou que NÃO é duplicata — segue para confirmação
            _ir_para_confirmacao(db, c, data, chat_id)
        return

    if prefixo == "fim":
        if valor == "cancel":
            ctx = _ctx_lote(data)
            _reset(db, c)
            telegram_api.send_message(chat_id, f"❌ Lote cancelado.\n_{ctx}_")
            return
        if valor == "edit":
            _passo_natureza(db, c, data, chat_id)
            return
        _finalizar(db, c, data, chat_id)
        return

    if prefixo == "aditem":
        if valor == "nova":
            draft["mode"] = "nova"
            _passo_natureza(db, c, data, chat_id)
            return
        _anexar_em_despesa_existente(db, c, data, chat_id, valor)
        return

    if prefixo == "send":
        _enviar_cobranca_lote(db, c, data, chat_id, valor)
        return

    if prefixo == "lote" and valor == "fim":
        touched = data.get("touched", [])
        linhas = []
        for rid in touched:
            r = db.query(Reembolso).filter(Reembolso.id == uuid.UUID(rid)).first()
            if r:
                cli = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
                nome = cli.nome if cli else "—"
                linhas.append(f"📁 {nome} — {r.titulo}: {_fmt_brl(r.total)}")
        _reset(db, c)
        detalhe = "\n".join(linhas) if linhas else "nenhuma pasta identificada"
        telegram_api.send_message(chat_id, f"🕐 Deixadas em aberto:\n{detalhe}")
        return

    if prefixo == "desc_p":
        _descartar_pendente(db, chat_id, valor)
        return

    if prefixo == "cat_p":
        _catalogar_pendente(db, c, data, chat_id, valor)
        return


# ── Passos ────────────────────────────────────────────────────────────────────

def _passo_natureza(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    _save(db, c, "natureza", data)
    draft = _draft(data)
    botoes, linha = [], []
    for i, nat in enumerate(NATUREZAS):
        linha.append((nat, f"nat:{i}"))
        if len(linha) == 2:
            botoes.append(linha)
            linha = []
    if linha:
        botoes.append(linha)
    sug = f" (sugestão: {draft['natureza']})" if draft.get("natureza") else ""
    telegram_api.send_message(chat_id, f"{_progresso(data)}Tipo de despesa{sug}:", botoes)


def _passo_pasta(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    _save(db, c, "pasta", data)
    draft = _draft(data)
    cliente_id = uuid.UUID(draft["cliente_id"])
    abertas = (
        db.query(Reembolso)
        .filter(Reembolso.cliente_id == cliente_id, Reembolso.status.in_(OPEN_STATUSES))
        .order_by(Reembolso.created_at.desc())
        .all()
    )
    if abertas:
        botoes = [[(f"📁 {r.titulo} — {_fmt_brl(r.total)}", f"pasta:{r.id}")] for r in abertas]
        botoes.append([("➕ Nova pasta", "pasta:new")])
        telegram_api.send_message(
            chat_id,
            f"Há pasta(s) em aberto para *{draft['cliente_nome']}*:",
            botoes,
        )
    else:
        telegram_api.send_message(
            chat_id,
            f"Nenhuma pasta em aberto para *{draft['cliente_nome']}*. Criar nova?",
            [[("➕ Criar nova pasta", "pasta:new")], [("❌ Cancelar lote", "fim:cancel")]],
        )


def _passo_descricao(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    draft = _draft(data)
    seed = (draft.get("vision") or {}).get("descricao") or draft.get("descricao_seed") or ""
    if seed:
        draft["descricao"] = seed
        _save(db, c, "descricao", data)
        telegram_api.send_message(
            chat_id, f"Descrição sugerida:\n*{seed}*",
            [[("✅ Ok", "desc:ok"), ("✏️ Editar", "desc:edit")]],
        )
    else:
        _save(db, c, "descricao_edit", data)
        telegram_api.send_message(chat_id, "Escreva uma breve descrição da despesa:")


def _ir_para_valor(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    draft = _draft(data)
    if draft.get("valor") is not None:
        _save(db, c, "valor", data)
        telegram_api.send_message(
            chat_id, f"Valor: *{_fmt_brl(float(draft['valor']))}*. Confirma?",
            [[("✅ Confirmar", "val:ok"), ("✏️ Corrigir", "val:edit")]],
        )
    else:
        _save(db, c, "valor_edit", data)
        telegram_api.send_message(chat_id, "Não identifiquei o valor. Qual é? (ex: 150,00)")


def _checar_duplicata_e_confirmar(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    """Se há itens com mesmo cliente + valor com comprovante, dispara checagem em background.
    Caso contrário, vai direto para a tela de confirmação."""
    draft = _draft(data)
    cliente_id = draft.get("cliente_id")
    valor = draft.get("valor")
    doc = draft.get("doc")

    if not cliente_id or valor is None:
        _ir_para_confirmacao(db, c, data, chat_id)
        return

    margem = 0.02  # tolerância de centavos
    is_manual = draft.get("manual") or not doc

    # Para entrada manual (sem foto): checa apenas por valor+cliente — sem comparação visual
    filtro_comprovante = [] if is_manual else [ItemReembolso.comprovante_path.isnot(None)]
    candidatos = (
        db.query(ItemReembolso)
        .join(Reembolso)
        .filter(
            Reembolso.cliente_id == uuid.UUID(cliente_id),
            ItemReembolso.valor.between(valor - margem, valor + margem),
            *filtro_comprovante,
        )
        .order_by(ItemReembolso.data.desc())
        .limit(3)
        .all()
    )

    if not candidatos:
        _ir_para_confirmacao(db, c, data, chat_id)
        return

    # Manual: sem imagem para comparar → alerta direto sem background
    if is_manual:
        nomes = ", ".join(
            f"*{it.descricao}* ({it.data.strftime('%d/%m/%Y')})" for it in candidatos
        )
        _save(db, c, "dup_check", data)
        telegram_api.send_message(
            chat_id,
            f"⚠️ *Possível duplicata:* já existe despesa de *{_fmt_brl(float(valor))}* "
            f"para *{draft.get('cliente_nome', 'este cliente')}*: {nomes}\n\n"
            "Como deseja prosseguir?",
            [
                [("✅ É despesa nova mesmo, confirmar", "dup:nova")],
                [("🗑️ É duplicata, descartar", "dup:ok")],
            ],
        )
        return

    # Com foto: dispara comparação visual em background
    _save(db, c, "dup_check", data)
    ids = [str(it.id) for it in candidatos]
    telegram_api.send_message(
        chat_id,
        f"🔍 Encontrei {len(candidatos)} despesa(s) de *{_fmt_brl(float(valor))}* "
        f"já catalogada(s) para *{draft.get('cliente_nome', 'este cliente')}*. "
        "Verificando se é duplicata... (~10s)"
    )
    threading.Thread(
        target=_comparar_duplicata_bg,
        args=(chat_id, doc["file_id"], doc.get("mime", "image/jpeg"), ids),
        daemon=True,
    ).start()


def _comparar_duplicata_bg(chat_id: int, file_id: str, mime: str, item_ids: list[str]) -> None:
    """Compara a foto nova com os comprovantes existentes. Roda em thread.

    Estratégia de obtenção da imagem existente (em ordem de preferência):
    1. Arquivo local em disco (comprovante_path)
    2. Re-download via Telegram file_id (TelegramDoc.item_id)
    Se nenhum conseguir a imagem → alerta suave (não silencia).
    """
    from app.services.ia_reembolso import comparar_comprovantes

    img_nova = telegram_api.download_file(file_id)
    if not img_nova or mime not in ("image/jpeg", "image/png"):
        _enviar_resultado_dup(chat_id, duplicata=False, razao=None)
        return

    db = SessionLocal()
    try:
        sem_imagem: list[ItemReembolso] = []  # candidatos cuja imagem não foi possível obter

        for iid in item_ids:
            item = db.query(ItemReembolso).filter(ItemReembolso.id == uuid.UUID(iid)).first()
            if not item:
                continue

            img_exist: bytes | None = None
            mime_exist = "image/jpeg"

            # 1. Tenta arquivo local
            if item.comprovante_path:
                path = Path(item.comprovante_path)
                if path.exists():
                    img_exist = path.read_bytes()
                    mime_exist = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"

            # 2. Tenta re-download via TelegramDoc (file_id original ainda válido no Telegram)
            if img_exist is None:
                tg_doc = (
                    db.query(TelegramDoc)
                    .filter(TelegramDoc.item_id == item.id)
                    .first()
                )
                if tg_doc and tg_doc.file_id:
                    img_exist = telegram_api.download_file(tg_doc.file_id)
                    mime_exist = tg_doc.mime or "image/jpeg"
                    if mime_exist not in ("image/jpeg", "image/png"):
                        img_exist = None

            if img_exist is None:
                sem_imagem.append(item)
                continue

            resultado = comparar_comprovantes(img_nova, mime, img_exist, mime_exist)
            if resultado.get("duplicado") and resultado.get("confianca") in ("alta", "media"):
                _enviar_resultado_dup(chat_id, duplicata=True,
                                      razao=resultado.get("razao", ""),
                                      item_descricao=item.descricao, item_data=item.data)
                return

        # Se havia candidatos cuja imagem não foi possível comparar → alerta suave
        if sem_imagem:
            nomes = ", ".join(
                f"*{it.descricao}* ({it.data.strftime('%d/%m/%Y')})" for it in sem_imagem
            )
            _enviar_resultado_dup(chat_id, duplicata=None,
                                  razao=f"Não consegui acessar a imagem para comparar: {nomes}")
            return

        # Comparou tudo e não achou duplicata
        _enviar_resultado_dup(chat_id, duplicata=False, razao=None)
    except Exception:
        import traceback; traceback.print_exc()
        _enviar_resultado_dup(chat_id, duplicata=False, razao=None)
    finally:
        db.close()


def _enviar_resultado_dup(
    chat_id: int,
    duplicata: bool | None,  # True=duplicata confirmada, False=ok, None=alerta suave
    razao: str | None,
    item_descricao: str | None = None,
    item_data=None,
) -> None:
    """Envia o resultado da checagem de duplicata e retoma o fluxo."""
    db = SessionLocal()
    try:
        c = _get_conversa(db, chat_id)
        data = copy.deepcopy(c.data or {})

        if duplicata is True:
            ref_existente = ""
            if item_descricao:
                ref_existente = f"\n📌 Despesa existente: *{item_descricao}*"
                if item_data:
                    ref_existente += f" em {item_data.strftime('%d/%m/%Y')}"
            telegram_api.send_message(
                chat_id,
                f"⚠️ *Possível duplicata detectada!*{ref_existente}\n_{razao}_\n\nComo prosseguir?",
                [
                    [("✅ É despesa nova mesmo, confirmar", "dup:nova")],
                    [("🗑️ É duplicata, descartar", "dup:ok")],
                ],
            )
        elif duplicata is None:
            # Alerta suave: havia candidatos mas não foi possível comparar as imagens
            telegram_api.send_message(
                chat_id,
                f"⚠️ *Atenção:* há despesas com o mesmo valor para este cliente, "
                f"mas não consegui comparar as imagens ({razao}).\n\n"
                "É uma despesa nova ou duplicata?",
                [
                    [("✅ É nova, confirmar", "dup:nova")],
                    [("🗑️ É duplicata, descartar", "dup:ok")],
                ],
            )
        else:
            # Tudo ok → vai para confirmação
            _ir_para_confirmacao(db, c, data, chat_id)
    finally:
        db.close()


def _ir_para_confirmacao(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    _save(db, c, "confirm", data)
    telegram_api.send_message(
        chat_id,
        _progresso(data) + _resumo_rascunho(_draft(data)) + "\n\nConfirmar?",
        [[("✅ Confirmar", "fim:ok")], [("✏️ Editar", "fim:edit"), ("❌ Cancelar lote", "fim:cancel")]],
    )


def _finalizar(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    draft = _draft(data)
    r = _gravar_despesa(db, draft)
    total, itens = r.total, list(r.itens)
    linhas = "\n".join(f"• {i.descricao} — {_fmt_brl(float(i.valor))}" for i in itens)
    aviso_data = ""
    if draft.get("data_invalida"):
        aviso_data = (
            f"\n⚠️ A data lida (`{draft['data_invalida']}`) não existe — usei "
            f"*{date.today().strftime('%d/%m/%Y')}*. Edite a despesa se precisar ajustar."
        )
    telegram_api.send_message(
        chat_id,
        f"✅ Incluído!\n\n📁 *{r.titulo}*\n{linhas}\n"
        f"━━━━━━━━━━\n*Total em aberto: {_fmt_brl(total)}*{aviso_data}",
    )
    data["batch_done"] = data.get("batch_done", 0) + 1
    touched: list = data.setdefault("touched", [])
    if str(r.id) not in touched:
        touched.append(str(r.id))
    data["draft"] = None
    _save(db, c, "idle", data)

    # Próxima da fila: inicia visão em background para não bloquear
    if data.get("queue"):
        threading.Thread(target=_processar_proximo_bg, args=(chat_id,), daemon=True).start()
    else:
        _mostrar_lote_fim(db, c, data, chat_id)


def _processar_proximo_bg(chat_id: int) -> None:
    """Roda em thread separada para processar próximo doc da fila."""
    with _vision_lock(chat_id):
        db = SessionLocal()
        try:
            c = _get_conversa(db, chat_id)
            data = copy.deepcopy(c.data or {})
            _processar_proximo(db, c, data, chat_id)
        except Exception:
            import traceback; traceback.print_exc()
        finally:
            db.close()


def _mostrar_lote_fim(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    touched = data.get("touched", [])
    if not touched:
        _reset(db, c)
        return
    botoes = []
    linhas = []
    for rid in touched:
        r = db.query(Reembolso).filter(Reembolso.id == uuid.UUID(rid)).first()
        if not r:
            continue
        cli = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
        nome = cli.nome if cli else "—"
        linhas.append(f"📁 {nome}: *{_fmt_brl(r.total)}*")
        botoes.append([(f"📧 Cobrar {nome}", f"send:{rid}")])
    botoes.append([("🕐 Deixar em aberto", "lote:fim")])
    _save(db, c, "lote_fim", data)
    telegram_api.send_message(
        chat_id,
        "🏁 *Lote concluído.*\n" + "\n".join(linhas) + "\n\nEnviar cobrança?",
        botoes,
    )


def _enviar_cobranca_lote(db: Session, c: TelegramConversa, data: dict, chat_id: int, rid: str) -> None:
    r = db.query(Reembolso).filter(Reembolso.id == uuid.UUID(rid)).first()
    msg = _enviar_cobranca(db, r) if r else "Pasta não encontrada."
    telegram_api.send_message(chat_id, msg)
    data["touched"] = [t for t in data.get("touched", []) if t != rid]
    if data["touched"]:
        _mostrar_lote_fim(db, c, data, chat_id)
    else:
        _reset(db, c)


# ── Fluxo "add" ───────────────────────────────────────────────────────────────

def _passo_add_despesa(db: Session, c: TelegramConversa, data: dict, chat_id: int) -> None:
    draft = _draft(data)
    cliente_id = uuid.UUID(draft["cliente_id"])
    abertas = (
        db.query(Reembolso)
        .filter(Reembolso.cliente_id == cliente_id, Reembolso.status.in_(OPEN_STATUSES))
        .all()
    )
    itens: list[ItemReembolso] = []
    for r in abertas:
        itens.extend(r.itens)
    if not itens:
        telegram_api.send_message(
            chat_id,
            f"Nenhuma despesa em aberto para *{draft.get('cliente_nome', 'este cliente')}* — tratando como nova despesa."
        )
        draft["mode"] = "nova"
        _passo_natureza(db, c, data, chat_id)
        return
    _save(db, c, "add_despesa", data)
    botoes = [[(f"{i.descricao} — {_fmt_brl(float(i.valor))}", f"aditem:{i.id}")] for i in itens]
    botoes.append([("⬅️ Não, é despesa nova", "aditem:nova")])
    telegram_api.send_message(chat_id, "A qual despesa esse documento pertence?", botoes)


def _anexar_em_despesa_existente(db: Session, c: TelegramConversa, data: dict, chat_id: int, item_id: str) -> None:
    draft = _draft(data)
    item = db.query(ItemReembolso).filter(ItemReembolso.id == uuid.UUID(item_id)).first()
    if not item:
        telegram_api.send_message(chat_id, "Despesa não encontrada.")
        return
    r = db.query(Reembolso).filter(Reembolso.id == item.reembolso_id).first()
    docs = [d for d in [draft.get("doc")] + draft.get("extra_docs", []) if d]
    _anexar_docs(db, r, item, docs)
    cli = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
    nome_cli = cli.nome if cli else "—"
    telegram_api.send_message(
        chat_id,
        f"📎 Documento anexado à despesa *{item.descricao}* ({_fmt_brl(float(item.valor))}) "
        f"— pasta de *{nome_cli}*."
    )
    data["batch_done"] = data.get("batch_done", 0) + 1
    touched: list = data.setdefault("touched", [])
    rid = str(r.id)
    if rid not in touched:
        touched.append(rid)
    data["draft"] = None
    _save(db, c, "idle", data)
    if data.get("queue"):
        threading.Thread(target=_processar_proximo_bg, args=(chat_id,), daemon=True).start()
    else:
        _mostrar_lote_fim(db, c, data, chat_id)


# ── /manual ───────────────────────────────────────────────────────────────────

def _iniciar_manual(db: Session, c: TelegramConversa, data: dict, chat_id: int, texto: str) -> None:
    valor, nome = _parse_catalogar(texto)
    draft: dict = {"manual": True, "doc": None, "extra_docs": [], "mode": "nova"}
    if valor is not None:
        draft["valor"] = valor
    data = {"draft": draft, "batch_total": 1, "batch_done": 0, "queue": [], "touched": []}
    if nome:
        achados = _match_clientes(db, nome, limit=4)
        if len(achados) == 1:
            draft["cliente_id"] = str(achados[0].id)
            draft["cliente_nome"] = achados[0].nome
            _passo_natureza(db, c, data, chat_id)
            return
        if achados:
            _save(db, c, "cliente", data)
            telegram_api.send_message(chat_id, f'Qual cliente (busquei "{nome}")?', _botoes_clientes(achados))
            return
    _save(db, c, "cliente", data)
    telegram_api.send_message(chat_id, "📝 Despesa manual. Qual o cliente?", _botoes_clientes(_match_clientes(db, None)))


def _parse_catalogar(texto: str) -> tuple[float | None, str | None]:
    if not texto:
        return None, None
    valor = None
    m = re.search(r"r?\$?\s*([\d.]+,\d{2}|\d+[.,]?\d*)", texto, re.IGNORECASE)
    if m:
        valor = _parse_valor(m.group(1))
    nome = None
    m2 = re.search(r"\bpara\s+(.+)$", texto, re.IGNORECASE)
    if m2:
        nome = m2.group(1).strip()
    return valor, nome


# ── /pendentes ────────────────────────────────────────────────────────────────

def _listar_pendentes(db: Session, c: TelegramConversa, chat_id: int) -> None:
    pendentes = (
        db.query(TelegramDoc)
        .filter(TelegramDoc.chat_id == chat_id, TelegramDoc.status == "pendente")
        .order_by(TelegramDoc.created_at)
        .all()
    )
    if not pendentes:
        telegram_api.send_message(chat_id, "✅ Nenhum comprovante pendente.")
        return
    linhas, botoes = [], []
    for d in pendentes:
        v = _fmt_brl(float(d.valor_detectado)) if d.valor_detectado is not None else "valor ?"
        quando = d.created_at.astimezone(TZ_BR).strftime("%d/%m %H:%M") if d.created_at else ""
        linhas.append(f"• {v} — recebido {quando}")
        botoes.append([
            (f"📋 Catalogar {v}", f"cat_p:{d.id}"),
            (f"🗑️ Descartar", f"desc_p:{d.id}"),
        ])
    telegram_api.send_message(
        chat_id,
        f"📋 *{len(pendentes)} comprovante(s) pendente(s):*\n" + "\n".join(linhas),
        botoes,
    )


def _catalogar_pendente(db: Session, c: TelegramConversa, data: dict, chat_id: int, doc_id: str) -> None:
    """Retoma o fluxo de catalogação para um comprovante que ficou pendente."""
    d = db.query(TelegramDoc).filter(TelegramDoc.id == uuid.UUID(doc_id)).first()
    if not d:
        telegram_api.send_message(chat_id, "Comprovante não encontrado.")
        return
    if d.status != "pendente":
        telegram_api.send_message(chat_id, "Este comprovante já foi catalogado ou descartado.")
        return
    # Recoloca na fila e inicia o fluxo normalmente
    doc = {
        "file_id": d.file_id,
        "file_unique_id": d.file_unique_id,
        "filename": d.filename or "foto.jpg",
        "mime": d.mime or "image/jpeg",
        "row_id": str(d.id),
    }
    data = copy.deepcopy(c.data or {})
    data.setdefault("queue", []).insert(0, doc)  # insere na frente da fila
    data["batch_total"] = data.get("batch_total", 0) + 1
    data["draft"] = None
    _save(db, c, "idle", data)
    threading.Thread(target=_processar_proximo_bg, args=(chat_id,), daemon=True).start()


def _descartar_pendente(db: Session, chat_id: int, doc_id: str) -> None:
    d = db.query(TelegramDoc).filter(TelegramDoc.id == uuid.UUID(doc_id)).first()
    if d:
        d.status = "descartado"
        db.commit()
        v = _fmt_brl(float(d.valor_detectado)) if d.valor_detectado is not None else "valor ?"
        quando = d.created_at.astimezone(TZ_BR).strftime("%d/%m %H:%M") if d.created_at else ""
        telegram_api.send_message(chat_id, f"🗑️ Comprovante descartado — *{v}* recebido em {quando}.")


# ── /resumo ───────────────────────────────────────────────────────────────────

def _listar_resumo(db: Session, chat_id: int) -> None:
    abertas = (
        db.query(Reembolso)
        .filter(Reembolso.status.in_(OPEN_STATUSES))
        .order_by(Reembolso.cliente_id, Reembolso.created_at.desc())
        .all()
    )
    pendentes_count = (
        db.query(TelegramDoc)
        .filter(TelegramDoc.chat_id == chat_id, TelegramDoc.status == "pendente")
        .count()
    )
    if not abertas and not pendentes_count:
        telegram_api.send_message(chat_id, "✅ Nenhuma pasta em aberto e nenhum comprovante pendente.")
        return
    linhas = []
    if abertas:
        linhas.append("📂 *Pastas em aberto:*")
        ultimo_cli = None
        for r in abertas:
            cli = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
            nome_cli = cli.nome if cli else "—"
            if nome_cli != ultimo_cli:
                linhas.append(f"\n👤 *{nome_cli}*")
                ultimo_cli = nome_cli
            n_itens = len(r.itens)
            linhas.append(f"  📁 {r.titulo} — {_fmt_brl(r.total)} ({n_itens} despesa(s))")
    if pendentes_count:
        linhas.append(f"\n📋 *{pendentes_count} comprovante(s) recebido(s) ainda não catalogado(s).*")
        linhas.append("Use /pendentes para ver detalhes.")
    telegram_api.send_message(chat_id, "\n".join(linhas))


# ── Util ──────────────────────────────────────────────────────────────────────

def _parece_despesa(texto: str) -> bool:
    """Heurística: o texto parece descrever uma despesa a catalogar?
    Critério: tem um valor monetário (R$ ou número decimal) OU
    contém palavra-chave de despesa jurídica.
    Ignora mensagens curtas de conversa casual (≤ 3 palavras sem valor).
    """
    t = texto.lower()
    # Tem valor monetário explícito
    if re.search(r"r\$\s*[\d]|[\d]+[,.][\d]{2}", t):
        return True
    # Contém palavra-chave de despesa
    keywords = ("diligência", "diligencia", "custa", "custas", "certidão", "certidao",
                 "honorário", "honorario", "cartório", "cartorio", "reembolso",
                 "despesa", "pagamento", "correios", "taxa", "protocolo")
    if any(k in t for k in keywords):
        return True
    # Tem padrão "para <nome>" com valor — ex: "R$ 76 para Pedro"
    if re.search(r"\bpara\s+\w+", t) and re.search(r"\d", t):
        return True
    return False


def _parse_valor(texto: str) -> float | None:
    t = (texto or "").replace("R$", "").replace("r$", "").strip().replace(".", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


_AJUDA = (
    "🤖 *Bot de Reembolsos — Sui*\n\n"
    "Envie o(s) print(s) do pagamento — leio o valor e guio o cadastro.\n"
    "Vários prints juntos: processo um a um (imagem X de N).\n\n"
    "*Comandos*\n"
    "/manual — despesa só por texto (ou: `catalogar R$ 76 para Pedro`)\n"
    "/resumo — pastas em aberto + comprovantes pendentes\n"
    "/pendentes — comprovantes recebidos não catalogados\n"
    "/cancelar — descarta o lote em andamento\n"
    "/ajuda — esta mensagem"
)


# ── Setup do webhook ──────────────────────────────────────────────────────────

_COMMANDS = [
    ("manual",    "Catalogar despesa só por texto (sem foto)"),
    ("resumo",    "Ver pastas em aberto e comprovantes pendentes"),
    ("pendentes", "Listar comprovantes recebidos não catalogados"),
    ("cancelar",  "Cancelar o lote em andamento"),
    ("ajuda",     "Mostrar todos os comandos disponíveis"),
]


@router.post("/set-webhook")
def set_webhook_endpoint(base_url: str):
    result = telegram_api.set_webhook(f"{base_url.rstrip('/')}/telegram/webhook")
    telegram_api.set_my_commands(_COMMANDS)
    return {"ok": result is not None, "result": result}
