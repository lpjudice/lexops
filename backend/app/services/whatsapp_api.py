"""Wrapper fino da WhatsApp Cloud API (Meta) — envio de template/texto,
verificação de assinatura do webhook.

Mesmo espírito do telegram_api.py: tudo via httpx, sem dependências extras,
engole erro de rede e retorna None em falha para nunca derrubar o webhook.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Any

import httpx

from app.config import settings

GRAPH_BASE = "https://graph.facebook.com"

_cache_status_template: dict[str, tuple[float, str | None]] = {}


def status_template(nome: str, idioma: str = "pt_BR") -> str | None:
    """Status do template na Meta: APPROVED, PENDING, REJECTED, PAUSED... ou
    "INEXISTENTE". None = não deu pra consultar (sem config/erro de rede) — quem
    chama deve seguir em frente e deixar a própria Meta responder. Cache de 60s."""
    waba = settings.whatsapp_business_account_id
    if not (waba and settings.whatsapp_access_token):
        return None
    chave, agora = f"{nome}:{idioma}", time.time()
    em_cache = _cache_status_template.get(chave)
    if em_cache and agora - em_cache[0] < 60:
        return em_cache[1]
    try:
        r = httpx.get(
            f"{GRAPH_BASE}/{settings.whatsapp_api_version}/{waba}/message_templates",
            params={"name": nome, "fields": "name,status,language", "limit": 20},
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            timeout=15.0,
        )
        itens = [t for t in r.json().get("data", []) if t.get("language") == idioma]
        status = itens[0].get("status") if itens else "INEXISTENTE"
    except Exception:
        status = None
    _cache_status_template[chave] = (agora, status)
    return status


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
    parametros: dict[str, str] | None = None,
    botao_url_param: str | None = None,
    botoes_resposta_payload: list[str] | None = None,
) -> dict | None:
    """Envia mensagem de template aprovado (categoria Utility/Marketing/Auth).
    `parametros` preenche as variáveis nomeadas do corpo (ex.: {{cliente_nome}}) —
    esta conta usa a experiência de templates com parâmetros nomeados da Meta,
    não a posicional ({{1}}, {{2}}).
    `botao_url_param` preenche o sufixo {{1}} do botão de link (único botão do
    template): a Meta sempre usa posicional pra botão, mesmo em template nomeado.
    `botoes_resposta_payload`: um payload por botão de resposta rápida, na ordem em que
    foram criados no template — voltam no webhook (type="button") quando a pessoa toca."""
    numero = normalizar_telefone(to)
    if not numero:
        return None
    components: list[dict[str, Any]] = []
    if parametros:
        components.append({
            "type": "body",
            "parameters": [
                {"type": "text", "parameter_name": nome, "text": valor}
                for nome, valor in parametros.items()
            ],
        })
    if botao_url_param:
        components.append({
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": botao_url_param}],
        })
    for i, payload_botao in enumerate(botoes_resposta_payload or []):
        components.append({
            "type": "button",
            "sub_type": "quick_reply",
            "index": str(i),
            "parameters": [{"type": "payload", "payload": payload_botao}],
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


def id_da_mensagem(resultado: dict | None) -> str | None:
    """wamid da mensagem aceita pela Meta (resposta de /messages), ou None."""
    try:
        return (resultado or {}).get("messages", [{}])[0].get("id")
    except (AttributeError, IndexError, TypeError):
        return None
