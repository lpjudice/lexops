"""Wrapper fino da WhatsApp Cloud API (Meta) — envio de template/texto,
verificação de assinatura do webhook.

Mesmo espírito do telegram_api.py: tudo via httpx, sem dependências extras,
engole erro de rede e retorna None em falha para nunca derrubar o webhook.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

import httpx

from app.config import settings

GRAPH_BASE = "https://graph.facebook.com"


def _messages_url() -> str:
    return f"{GRAPH_BASE}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"


def normalizar_telefone(numero: str) -> str | None:
    """Só dígitos, com DDI 55 se vier sem. Meta espera o "to" em E.164 sem o '+'."""
    digits = re.sub(r"\D", "", numero or "")
    if not digits:
        return None
    if digits.startswith("55"):
        return digits
    if len(digits) in (10, 11):  # DDD + número, sem DDI
        return f"55{digits}"
    return digits


def _post(payload: dict) -> dict | None:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return None
    try:
        resp = httpx.post(
            _messages_url(),
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            json=payload,
            timeout=20.0,
        )
        data = resp.json()
        if resp.status_code >= 400:
            return {"erro": data}
        return data
    except Exception:
        return None


def send_template_message(
    to: str,
    template_name: str,
    language_code: str = "pt_BR",
    parametros: list[str] | None = None,
) -> dict | None:
    """Envia mensagem de template aprovado (categoria Utility/Marketing/Auth).
    `parametros` preenche {{1}}, {{2}}... do corpo, na ordem."""
    numero = normalizar_telefone(to)
    if not numero:
        return None
    components: list[dict[str, Any]] = []
    if parametros:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in parametros],
        })
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            **({"components": components} if components else {}),
        },
    }
    return _post(payload)


def send_text_message(to: str, texto: str) -> dict | None:
    """Texto livre — só entrega se houver janela de serviço aberta (cliente
    mandou mensagem nas últimas 24h) OU o número estiver na lista de testes."""
    numero = normalizar_telefone(to)
    if not numero:
        return None
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto[:4096]},
    }
    return _post(payload)


def mark_as_read(message_id: str) -> dict | None:
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    return _post(payload)


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Valida X-Hub-Signature-256 do webhook contra o App Secret.
    Sem app_secret configurado, não há como validar — deixa passar (dev/teste)."""
    if not settings.whatsapp_app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.whatsapp_app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    recebido = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, recebido)
