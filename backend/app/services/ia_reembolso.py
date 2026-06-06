"""IA do bot de Reembolsos: lê comprovantes (imagem) e limpa descrições.

- extrair_dados: roda Claude vision sobre o print do pagamento e tenta
  identificar valor, data, natureza e nome do cliente.
- limpar_descricao: reescreve o texto livre do Lucas de forma mais limpa
  e resumida, mantendo o sentido.

Só processa imagens (PNG/JPG). PDFs não são enviados ao modelo nesta versão
(o SDK anthropic==0.28.0 não suporta blocos de documento); nesses casos a
extração volta vazia e o bot pergunta o valor manualmente.
"""
from __future__ import annotations

import base64
import json
import re

from app.config import settings

# Haiku 4.5: leitura de comprovante é tarefa simples e precisa ser rápida.
MODEL = "claude-haiku-4-5-20251001"

NATUREZAS = [
    "Custas processuais",
    "Certidão",
    "Diligência",
    "Cópias/Autenticação",
    "Correios",
    "Outros",
]

_SYSTEM = """Você analisa comprovantes de pagamento/compra de um advogado (custas \
processuais, certidões, diligências etc.) que serão repassados como reembolso ao cliente.
Retorne SOMENTE um JSON válido com este esquema exato:
{
  "valor": número decimal (ex: 150.00) ou null,
  "data": "YYYY-MM-DD" ou null,
  "natureza": uma de ["Custas processuais","Certidão","Diligência","Cópias/Autenticação","Correios","Outros"] ou null,
  "descricao": "frase curta descrevendo a despesa" ou null,
  "cliente_nome": "nome de pessoa/empresa que apareça como parte/sacado/favorecido" ou null
}
Se houver vários valores, retorne o valor TOTAL pago. Sem markdown, sem explicações."""


def _parse_json(raw: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        raw = match.group(1).strip()
    return json.loads(raw)


def extrair_dados(image_bytes: bytes, mime: str, caption: str | None = None) -> dict:
    """Extrai dados do comprovante. Retorna {} em qualquer falha."""
    if not settings.anthropic_api_key:
        return {}
    if mime not in ("image/png", "image/jpeg"):
        return {}
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        content: list = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            }
        ]
        if caption:
            content.append({"type": "text", "text": f"Observação do advogado: {caption[:500]}"})
        msg = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        data = _parse_json(msg.content[0].text.strip())
        # Normaliza valor
        if data.get("valor") is not None:
            try:
                data["valor"] = round(float(data["valor"]), 2)
            except (TypeError, ValueError):
                data["valor"] = None
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def comparar_comprovantes(img_nova: bytes, mime_nova: str, img_existente: bytes, mime_existente: str) -> dict:
    """Compara dois comprovantes via Claude vision.
    Retorna {duplicado: bool, confianca: 'alta'|'media'|'baixa', razao: str}
    """
    if not settings.anthropic_api_key:
        return {"duplicado": False, "confianca": "baixa", "razao": "API não configurada"}
    mimes_ok = ("image/png", "image/jpeg")
    if mime_nova not in mimes_ok or mime_existente not in mimes_ok:
        return {"duplicado": False, "confianca": "baixa", "razao": "Formato não suportado para comparação"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        b64_nova = base64.standard_b64encode(img_nova).decode("ascii")
        b64_exist = base64.standard_b64encode(img_existente).decode("ascii")
        msg = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=(
                "Você compara dois comprovantes de pagamento para detectar duplicatas. "
                "Analise: data da transação, ID/código da transação, valor, destinatário/beneficiário. "
                "Retorne SOMENTE JSON: "
                '{"duplicado": true/false, "confianca": "alta"|"media"|"baixa", "razao": "explicação curta"}'
            ),
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Comprovante NOVO (sendo cadastrado):"},
                {"type": "image", "source": {"type": "base64", "media_type": mime_nova, "data": b64_nova}},
                {"type": "text", "text": "Comprovante EXISTENTE (já catalogado):"},
                {"type": "image", "source": {"type": "base64", "media_type": mime_existente, "data": b64_exist}},
                {"type": "text", "text": "Esses dois comprovantes registram a MESMA transação?"},
            ]}],
        )
        return _parse_json(msg.content[0].text.strip())
    except Exception as e:
        return {"duplicado": False, "confianca": "baixa", "razao": str(e)}


def limpar_descricao(texto: str) -> str:
    """Reescreve a descrição de forma limpa e curta. Em falha, devolve o texto original."""
    texto = (texto or "").strip()
    if not texto or not settings.anthropic_api_key:
        return texto
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=120,
            system=(
                "Reescreva a descrição de uma despesa jurídica de forma limpa, "
                "profissional e curta (máximo 12 palavras). Responda APENAS com a "
                "descrição, sem aspas, sem pontuação final."
            ),
            messages=[{"role": "user", "content": texto[:500]}],
        )
        out = msg.content[0].text.strip().strip('"').rstrip(".")
        return out or texto
    except Exception:
        return texto
