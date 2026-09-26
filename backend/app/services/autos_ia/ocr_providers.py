"""OCR de página escaneada em rodízio entre provedores — pedido do Lucas pra
diluir o custo entre APIs em vez de ficar só na mais cara. Cada página que
chega aqui já passou por pypdf/pdfminer sem achar texto nativo (ver
pdf_extract.py); tenta o próximo provedor da rodada e, se falhar, cai pro
próximo na mesma chamada — só desiste da página se todos falharem.

GPT (OpenAI) fica de fora por enquanto: a versão do SDK já fixada no
projeto (openai==1.30.1) é anterior à API de Responses/PDF, e testar às
cegas um provedor de OCR arriscava trocar "custo alto" por "silenciosamente
sem OCR nenhum". Ver conversa com o Lucas antes de adicionar.
"""
import base64
import itertools
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Preços por MTok conferidos nas páginas oficiais de cada provedor.
PRECO_CLAUDE_INPUT = 1.0
PRECO_CLAUDE_OUTPUT = 5.0
PRECO_GEMINI_INPUT = 0.10
PRECO_GEMINI_OUTPUT = 0.40

_PROMPT_OCR = (
    "Extraia TODO o texto desta página exatamente como está, preservando "
    "parágrafos, numerações e formatação. Retorne APENAS o texto extraído, "
    "sem comentários adicionais."
)


def _ocr_claude(pagina_bytes: bytes) -> tuple[str, float]:
    import anthropic

    client = anthropic.Anthropic(timeout=90.0, max_retries=1)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64", "media_type": "application/pdf",
                        "data": base64.b64encode(pagina_bytes).decode(),
                    },
                },
                {"type": "text", "text": _PROMPT_OCR},
            ],
        }],
    )
    texto = resp.content[0].text if resp.content else ""
    custo = (
        resp.usage.input_tokens / 1_000_000 * PRECO_CLAUDE_INPUT
        + resp.usage.output_tokens / 1_000_000 * PRECO_CLAUDE_OUTPUT
    )
    return texto, custo


def _ocr_gemini(pagina_bytes: bytes) -> tuple[str, float]:
    import httpx

    if not settings.google_ai_api_key:
        raise RuntimeError("GOOGLE_AI_API_KEY não configurada")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash-lite:generateContent?key={settings.google_ai_api_key}"
    )
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": base64.b64encode(pagina_bytes).decode(),
                    },
                },
                {"text": _PROMPT_OCR},
            ],
        }],
    }
    resp = httpx.post(url, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    texto = data["candidates"][0]["content"]["parts"][0]["text"]
    uso = data.get("usageMetadata", {})
    custo = (
        uso.get("promptTokenCount", 0) / 1_000_000 * PRECO_GEMINI_INPUT
        + uso.get("candidatesTokenCount", 0) / 1_000_000 * PRECO_GEMINI_OUTPUT
    )
    return texto, custo


_PROVEDORES = [
    ("claude", _ocr_claude),
    ("gemini", _ocr_gemini),
]
_contador = itertools.count()


def ocr_pagina_rotativo(pagina_bytes: bytes, on_custo=None) -> str:
    """Alterna o provedor a cada chamada (rodízio simples, não por custo) —
    se o da vez falhar, tenta o outro antes de desistir da página."""
    indice_inicial = next(_contador) % len(_PROVEDORES)
    ultimo_erro: Exception | None = None
    for offset in range(len(_PROVEDORES)):
        nome, fn = _PROVEDORES[(indice_inicial + offset) % len(_PROVEDORES)]
        try:
            texto, custo = fn(pagina_bytes)
        except Exception as exc:
            ultimo_erro = exc
            logger.warning("OCR via %s falhou, tentando próximo provedor: %s", nome, exc)
            continue
        if on_custo and custo:
            on_custo(custo)
        return texto
    logger.warning("OCR falhou em todos os provedores: %s", ultimo_erro)
    return ""
