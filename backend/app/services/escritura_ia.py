"""
Extração de dados de escritura/matrícula de imóvel via Gemini 2.5 Flash (visão).

Lê PDF ou imagem (não persiste) e retorna os campos estruturados + o "trecho"
literal do documento de onde cada campo foi extraído, para validação humana.
Gemini Flash foi escolhido por custo (menor que Claude/GPT-4o para OCR) e por
ler PDF nativamente.
"""
import base64
import json
import re

from app.config import settings

_MODEL = "gemini-2.5-flash"
_MIMES_OK = ("application/pdf", "image/png", "image/jpeg", "image/webp")

_PROMPT = """Você é um assistente jurídico especializado em análise de escrituras públicas, \
matrículas e contratos de compra e venda de imóveis no Brasil.

Analise o documento e extraia EXATAMENTE os campos abaixo. Para CADA campo, retorne o \
"valor" e o "trecho" — a passagem LITERAL do documento de onde você tirou a informação \
(máx. ~200 caracteres, copie ipsis litteris). Se não encontrar, use null/"" no valor e "" no trecho.

Responda SOMENTE com JSON válido (sem markdown), neste formato exato:
{
  "descricao_imovel": {"valor": "descrição detalhada (tipo, localização, área, confrontações, benfeitorias)", "trecho": ""},
  "proprietario_atual": {"valor": "nome do(s) proprietário(s) atual(is)/último(s) adquirente(s)", "trecho": ""},
  "valor_compra": {"valor": <número em reais da compra EFETIVA, só dígitos e ponto decimal, ou null>, "trecho": ""},
  "proprietarios_anteriores": {"valor": "proprietários/transmitentes anteriores, em texto corrido", "trecho": ""},
  "data_transacao": {"valor": "data da última venda/compra no formato AAAA-MM-DD, ou null", "trecho": ""},
  "numero_matricula": {"valor": "número da matrícula do imóvel", "trecho": ""},
  "cartorio": {"valor": "nome/identificação do Cartório de Registro de Imóveis", "trecho": ""},
  "hipoteca": {"existe": <true|false>, "vencida": <true|false|null>, "descricao": "detalhes do gravame/hipoteca/ônus (credor, valor, vencimento)", "trecho": ""}
}

Regras importantes:
- "valor_compra" é o valor REAL da transação (o preço pago), NÃO o valor venal nem o estimado para fins de tributo.
- Em "hipoteca": se houver ônus/gravame, determine se está vencida comparando a data de vencimento com a data atual. Se não for possível saber, use vencida=null.
- Não invente dados. Extraia apenas o que está no documento."""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if m:
        raw = m.group(1).strip()
    return json.loads(raw)


def extrair_escritura(file_bytes: bytes, mime: str) -> dict:
    """Extrai os campos da escritura. Retorna {"erro": ...} em caso de falha."""
    if not settings.google_ai_api_key:
        return {"erro": "GOOGLE_AI_API_KEY não configurada."}
    if mime not in _MIMES_OK:
        return {"erro": f"Formato não suportado ({mime}). Envie PDF, PNG, JPG ou WEBP."}
    try:
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{_MODEL}:generateContent?key={settings.google_ai_api_key}"
        )
        b64 = base64.b64encode(file_bytes).decode()
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": mime, "data": b64}},
                    {"text": _PROMPT},
                ],
            }],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        resp = httpx.post(url, json=payload, timeout=180)
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_json(raw)
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Erro ao ler o documento: {e}"}
