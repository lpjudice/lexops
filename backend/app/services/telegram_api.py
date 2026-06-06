"""Wrapper fino da Telegram Bot API (envio de mensagens, botões, download).

Tudo via httpx, sem dependências extras. As funções engolem erros de rede
e retornam None/{} em falha, para nunca derrubar o webhook.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

API_BASE = "https://api.telegram.org"


def _url(method: str) -> str:
    return f"{API_BASE}/bot{settings.telegram_bot_token}/{method}"


def _post(method: str, payload: dict) -> dict | None:
    if not settings.telegram_bot_token:
        return None
    try:
        resp = httpx.post(_url(method), json=payload, timeout=20.0)
        data = resp.json()
        return data.get("result") if data.get("ok") else None
    except Exception:
        return None


def send_message(
    chat_id: int,
    text: str,
    buttons: list[list[tuple[str, str]]] | None = None,
    reply_to: int | None = None,
) -> dict | None:
    """Envia texto. `buttons` é uma matriz de (label, callback_data)."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": label, "callback_data": data} for (label, data) in row]
                for row in buttons
            ]
        }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    result = _post("sendMessage", payload)
    if result is None:
        # Markdown pode falhar com nomes que tenham *, _, etc. — reenvia em texto puro.
        payload.pop("parse_mode", None)
        result = _post("sendMessage", payload)
    return result


def edit_message_text(
    chat_id: int,
    message_id: int,
    text: str,
    buttons: list[list[tuple[str, str]]] | None = None,
) -> dict | None:
    """Edita uma mensagem (usado para remover/atualizar botões após o clique)."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    payload["reply_markup"] = {
        "inline_keyboard": [
            [{"text": label, "callback_data": data} for (label, data) in row]
            for row in (buttons or [])
        ]
    }
    return _post("editMessageText", payload)


def answer_callback(callback_query_id: str, text: str | None = None) -> dict | None:
    """Fecha o 'loading' do botão clicado."""
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return _post("answerCallbackQuery", payload)


def get_file_path(file_id: str) -> str | None:
    result = _post("getFile", {"file_id": file_id})
    if result:
        return result.get("file_path")
    return None


def download_file(file_id: str) -> bytes | None:
    """Baixa o conteúdo de um arquivo enviado ao bot."""
    path = get_file_path(file_id)
    if not path:
        return None
    try:
        url = f"{API_BASE}/file/bot{settings.telegram_bot_token}/{path}"
        resp = httpx.get(url, timeout=60.0)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        return None
    return None


def set_my_commands(commands: list[tuple[str, str]]) -> dict | None:
    """Registra os comandos no menu sanduíche do Telegram.
    commands: lista de (comando_sem_barra, descrição)
    """
    payload = {
        "commands": [
            {"command": cmd, "description": desc}
            for cmd, desc in commands
        ]
    }
    return _post("setMyCommands", payload)


def set_webhook(url: str) -> dict | None:
    payload: dict[str, Any] = {"url": url, "allowed_updates": ["message", "callback_query"]}
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret
    return _post("setWebhook", payload)
