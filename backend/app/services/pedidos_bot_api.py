"""Wrapper fino da Telegram Bot API para o bot de Pedidos (voz → aprovação).

Token próprio (TELEGRAM_PEDIDOS_BOT_TOKEN), separado dos outros bots do
projeto. Mesmo espírito do telegram_api.py: via httpx, engole erro de rede.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

API_BASE = "https://api.telegram.org"


def _url(method: str) -> str:
    return f"{API_BASE}/bot{settings.telegram_pedidos_bot_token}/{method}"


def _post(method: str, payload: dict) -> dict | None:
    if not settings.telegram_pedidos_bot_token:
        return None
    try:
        resp = httpx.post(_url(method), json=payload, timeout=20.0)
        data = resp.json()
        return data.get("result") if data.get("ok") else None
    except Exception:
        return None


def send_message(
    chat_id: str | int,
    text: str,
    buttons: list[list[tuple[str, str]]] | None = None,
) -> dict | None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": label, "callback_data": data} for (label, data) in row]
                for row in buttons
            ]
        }
    result = _post("sendMessage", payload)
    if result is None:
        payload.pop("parse_mode", None)
        result = _post("sendMessage", payload)
    return result


def edit_message_text(chat_id: str | int, message_id: str | int, text: str) -> dict | None:
    return _post("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    })


def answer_callback_query(callback_query_id: str, text: str = "") -> dict | None:
    return _post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})


def register_webhook(base_url: str) -> dict | None:
    webhook_url = f"{base_url.rstrip('/')}/telegram-pedidos/webhook"
    payload: dict[str, Any] = {"url": webhook_url}
    if settings.telegram_pedidos_webhook_secret:
        payload["secret_token"] = settings.telegram_pedidos_webhook_secret
    return _post("setWebhook", payload)


def get_webhook_info() -> dict | None:
    return _post("getWebhookInfo", {})
