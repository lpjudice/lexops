"""Webhook do bot de Pedidos via Telegram — trigger de ligação (Bland.ai) e
aprovação do pedido capturado na chamada.

Fluxo:
  1. Lucas manda "/ligar" (ou "/ligar +1...") pro bot, de qualquer lugar.
  2. Backend dispara a chamada via Bland.ai (telefonia.py já faz isso) e
     guarda um PedidoVoz com status em_chamada.
  3. Bland.ai liga, ouve o pedido, confirma, encerra — e chama o webhook de
     fim de chamada (telefonia.py: /telefonia/webhook-bland), que atualiza
     o PedidoVoz e manda a transcrição pro Telegram com botões Aprovar/Rejeitar.
  4. Lucas aprova ou rejeita pelo botão — callback tratado aqui.

Endpoints:
  POST /telegram-pedidos/webhook           — recebe updates do Telegram
  POST /telegram-pedidos/webhook/registrar — registra o webhook no Telegram
  GET  /telegram-pedidos/webhook/status    — info do webhook atual
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.pedido_voz import PedidoVoz
from app.services import bland_api, pedidos_bot_api as tg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram-pedidos", tags=["telegram-pedidos"])

TAREFA_BLAND = (
    "Você está atendendo uma ligação do Lucas Judice, advogado, sobre o sistema "
    "interno dele chamado Sui (LexOps). Lucas vai descrever uma mudança ou "
    "funcionalidade que ele quer no sistema. Ouça com atenção, faça perguntas "
    "de esclarecimento se o pedido estiver vago, e ao final REPITA o pedido "
    "em voz alta pra confirmar que você entendeu corretamente antes de "
    "encerrar. Depois da confirmação, agradeça e diga que ele vai receber a "
    "confirmação por Telegram para aprovar, e encerre a ligação educadamente."
)


class _TelegramUpdate(BaseModel):
    update_id: int | None = None
    message: dict | None = None
    callback_query: dict | None = None


def _validate_secret(secret: str | None) -> None:
    expected = settings.telegram_pedidos_webhook_secret.strip()
    if expected and secret != expected:
        raise HTTPException(status_code=403, detail="Secret inválido")


def _autorizado(user_id: int | None) -> bool:
    allowed = settings.telegram_pedidos_allowed_ids
    return bool(user_id) and (not allowed or user_id in allowed)


def _handle_message(db: Session, message: dict) -> None:
    chat_id = str(message["chat"]["id"])
    user_id = (message.get("from") or {}).get("id")
    text = (message.get("text") or "").strip()

    if not _autorizado(user_id):
        tg.send_message(chat_id, "Você não está autorizado a usar este bot.")
        return

    if text in {"/start", "/ajuda", "/help"}:
        tg.send_message(
            chat_id,
            "Olá! Mande `/ligar` para eu te ligar e ouvir seu pedido de mudança no "
            "sistema. Ou `/ligar +1XXXXXXXXXX` para ligar pra outro número.",
        )
        return

    if text.startswith("/ligar"):
        partes = text.split(maxsplit=1)
        telefone = partes[1].strip() if len(partes) > 1 else settings.telefonia_numero_lucas
        if not telefone:
            tg.send_message(chat_id, "Nenhum número configurado. Use `/ligar +1XXXXXXXXXX`.")
            return

        pedido = PedidoVoz(chat_id=chat_id, telefone=telefone, status="em_chamada")
        db.add(pedido)
        db.commit()

        base_url = os.getenv("WEBHOOK_BASE_URL", "https://lexops.fly.dev")
        webhook_url = f"{base_url.rstrip('/')}/api/telefonia/webhook-bland"
        if settings.bland_webhook_secret:
            webhook_url += f"?secret={settings.bland_webhook_secret}"

        resultado = bland_api.disparar_chamada(
            telefone=telefone,
            tarefa=TAREFA_BLAND,
            webhook_url=webhook_url,
            metadata={"pedido_id": str(pedido.id)},
        )
        if resultado is None or "erro" in (resultado or {}):
            pedido.status = "falhou"
            db.commit()
            tg.send_message(chat_id, "Não consegui disparar a ligação (Bland.ai não configurado ou erro na chamada).")
            return

        pedido.call_id = resultado.get("call_id") or resultado.get("id")
        db.commit()
        tg.send_message(chat_id, f"📞 Ligando para {telefone}... vou te mandar o pedido aqui assim que a chamada terminar.")
        return

    tg.send_message(chat_id, "Comando não reconhecido. Use `/ligar`.")


def _handle_callback(db: Session, callback: dict) -> None:
    callback_id = callback["id"]
    user_id = (callback.get("from") or {}).get("id")
    data = callback.get("data") or ""
    message = callback.get("message") or {}
    chat_id = str(message.get("chat", {}).get("id"))
    message_id = message.get("message_id")

    if not _autorizado(user_id):
        tg.answer_callback_query(callback_id, "Não autorizado.")
        return

    if not data.startswith("pedido:"):
        tg.answer_callback_query(callback_id)
        return

    _, acao, pedido_hex = data.split(":", 2)
    import uuid
    pedido = db.query(PedidoVoz).filter(PedidoVoz.id == uuid.UUID(hex=pedido_hex)).first()
    if not pedido:
        tg.answer_callback_query(callback_id, "Pedido não encontrado.")
        return

    if acao == "aprovar":
        pedido.status = "aprovado"
        pedido.resolved_at = datetime.now(timezone.utc)
        db.commit()
        tg.edit_message_text(chat_id, message_id, f"✅ *Aprovado.*\n\n{pedido.resumo_pedido or pedido.transcricao or ''}\n\nSerá implementado em breve.")
        tg.answer_callback_query(callback_id, "Aprovado!")
    elif acao == "rejeitar":
        pedido.status = "rejeitado"
        pedido.resolved_at = datetime.now(timezone.utc)
        db.commit()
        tg.edit_message_text(chat_id, message_id, f"❌ *Rejeitado.*\n\n{pedido.resumo_pedido or pedido.transcricao or ''}")
        tg.answer_callback_query(callback_id, "Rejeitado.")
    else:
        tg.answer_callback_query(callback_id)


def _process_update(update: _TelegramUpdate) -> None:
    db: Session = SessionLocal()
    try:
        if update.message:
            _handle_message(db, update.message)
        elif update.callback_query:
            _handle_callback(db, update.callback_query)
    except Exception:
        logger.exception("Erro no webhook de pedidos")
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
    await asyncio.to_thread(_process_update, update)
    return {"ok": True}


@router.post("/webhook/registrar")
def registrar_webhook(base_url: str) -> dict:
    result = tg.register_webhook(base_url)
    return {"ok": True, "resultado": result}


@router.get("/webhook/status")
def status_webhook() -> dict:
    return tg.get_webhook_info() or {}
