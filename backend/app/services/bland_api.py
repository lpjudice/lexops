"""Wrapper fino da API da Bland.ai — disparo de chamadas de voz via IA.

Mesmo espírito do whatsapp_api.py: tudo via httpx, engole erro de rede e
retorna None em falha para nunca derrubar quem chamou.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import settings

API_BASE = "https://api.bland.ai"


def normalizar_telefone(numero: str) -> str | None:
    """Formato E.164 com '+'. Assume DDI 1 (EUA/Canadá) se vier sem DDI —
    a Bland.ai só opera números americanos (+1) nesta conta."""
    digits = re.sub(r"\D", "", numero or "")
    if not digits:
        return None
    if len(digits) == 10:  # número americano sem DDI
        return f"+1{digits}"
    return f"+{digits}"


def disparar_chamada(
    telefone: str,
    tarefa: str,
    voice: str | None = None,
    webhook_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict | None:
    """Dispara uma chamada via Bland.ai. `tarefa` é a instrução em linguagem
    natural que a IA vai seguir durante a ligação (o parâmetro `task` da API).
    """
    if not settings.bland_api_key:
        return None
    destino = normalizar_telefone(telefone)
    if not destino:
        return None
    payload: dict[str, Any] = {
        "phone_number": destino,
        "task": tarefa,
    }
    if voice:
        payload["voice"] = voice
    if webhook_url:
        payload["webhook"] = webhook_url
    if metadata:
        payload["metadata"] = metadata
    try:
        resp = httpx.post(
            f"{API_BASE}/v1/calls",
            headers={
                "Authorization": settings.bland_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20.0,
        )
        data = resp.json()
        if resp.status_code >= 400:
            return {"erro": data}
        return data
    except Exception:
        return None


def consultar_chamada(call_id: str) -> dict | None:
    if not settings.bland_api_key:
        return None
    try:
        resp = httpx.get(
            f"{API_BASE}/v1/calls/{call_id}",
            headers={"Authorization": settings.bland_api_key},
            timeout=20.0,
        )
        data = resp.json()
        if resp.status_code >= 400:
            return {"erro": data}
        return data
    except Exception:
        return None
