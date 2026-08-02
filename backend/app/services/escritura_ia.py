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

Analise o documento e extraia EXATAMENTE os campos abaixo. Para CADA campo, retorne:
- "valor": a informação extraída;
- "trecho": a passagem LITERAL do documento (máx. ~200 caracteres, copie ipsis litteris);
- "referencia": onde no documento está — a PÁGINA e o número do ATO registral (Av-N para \
averbação, R-N para registro, ou o nº da matrícula) e, quando fizer sentido, a DATA do ato. \
Ex.: "pág. 2 · R-3 · 12/05/2010". Se não identificar, use "".

Se não encontrar um campo, use null/"" no valor e "" no trecho/referencia.

Responda SOMENTE com JSON válido (sem markdown), neste formato exato:
{
  "descricao_imovel": {"valor": "descrição detalhada (tipo, localização, área, confrontações, benfeitorias)", "trecho": "", "referencia": ""},
  "proprietario_atual": {"valor": "nome do(s) proprietário(s) atual(is)/último(s) adquirente(s)", "data_aquisicao": "data em que passaram a ser proprietários (AAAA-MM-DD) ou null", "trecho": "", "referencia": ""},
  "valor_compra": {"valor": <número da compra EFETIVA, só dígitos e ponto decimal, ou null>, "moeda": "moeda em que o valor está no documento: R$ (real), Cr$ (cruzeiro), Cz$ (cruzado), NCz$ (cruzado novo), CR$ (cruzeiro real) etc.", "trecho": "", "referencia": ""},
  "proprietarios_anteriores": {"valor": "proprietários/transmitentes anteriores, em texto corrido", "trecho": "", "referencia": ""},
  "data_transacao": {"valor": "data da última venda/compra no formato AAAA-MM-DD, ou null", "trecho": "", "referencia": ""},
  "numero_matricula": {"valor": "número da matrícula do imóvel", "trecho": "", "referencia": ""},
  "cartorio": {"valor": "nome/identificação do Cartório de Registro de Imóveis", "trecho": "", "referencia": ""},
  "gravames": {"existe": <true|false>, "itens": [{"tipo": "hipoteca|penhora|indisponibilidade|alienacao_fiduciaria|usufruto|servidao|arresto|penhora_fiscal|outro", "descricao": "detalhes (credor/exequente, valor, vencimento, processo)", "vencida": <true|false|null>, "trecho": "", "referencia": ""}]}
}

Regras importantes:
- "valor_compra": o valor REAL da transação (o preço pago), NÃO o valor venal nem o estimado para tributo. \
Em "moeda", identifique a moeda da época (escrituras antigas costumam estar em cruzeiro/cruzado). Se for real, use "R$".
- "gravames": liste TODOS os ônus/gravames ATIVOS na matrícula — hipoteca, penhora, indisponibilidade de bens, \
alienação fiduciária, usufruto, servidão, arresto etc. Para cada um, se aplicável, diga se está "vencida" \
(true/false) comparando o vencimento com a data atual; se não der para saber, use null. Se não houver gravame, use existe=false e itens=[].
- Não invente dados. Extraia apenas o que está no documento."""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if m:
        raw = m.group(1).strip()
    return json.loads(raw)


def extrair_escritura(file_bytes: bytes, mime: str) -> dict:
    """Extrai os campos da escritura. Retorna {"erro": ...} detalhado em caso de falha."""
    if not settings.google_ai_api_key:
        return {"erro": "GOOGLE_AI_API_KEY não configurada no servidor."}
    if mime not in _MIMES_OK:
        return {"erro": f"Formato não suportado ({mime}). Envie PDF, PNG, JPG ou WEBP."}
    tamanho_mb = len(file_bytes) / (1024 * 1024)
    if tamanho_mb > 20:
        return {"erro": f"Arquivo muito grande ({tamanho_mb:.1f} MB). O limite é ~20 MB; "
                        f"reduza a resolução do PDF/imagem e tente de novo."}

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

    try:
        resp = httpx.post(url, json=payload, timeout=180)
    except httpx.TimeoutException:
        return {"erro": "A leitura demorou demais (timeout). O documento pode ser grande ou ter muitas "
                        "páginas — tente enviar só a matrícula/escritura, com menos páginas."}
    except httpx.RequestError as e:
        return {"erro": f"Falha de conexão com a IA: {e}"}

    if resp.status_code != 200:
        # Extrai a mensagem de erro da API do Gemini quando houver.
        detalhe = ""
        try:
            detalhe = resp.json().get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            detalhe = resp.text[:300]
        if resp.status_code == 400:
            return {"erro": f"A IA rejeitou o documento (400): {detalhe or 'formato/tamanho inválido'}."}
        if resp.status_code in (401, 403):
            return {"erro": "Chave da IA inválida ou sem permissão para o Gemini (verifique a GOOGLE_AI_API_KEY)."}
        if resp.status_code == 429:
            return {"erro": "Limite de uso da IA atingido (429). Aguarde um instante e tente de novo."}
        return {"erro": f"A IA retornou erro {resp.status_code}: {detalhe or resp.text[:200]}"}

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return {"erro": "A IA respondeu num formato inesperado (não-JSON)."}

    candidates = data.get("candidates") or []
    if not candidates:
        fb = data.get("promptFeedback", {})
        motivo = fb.get("blockReason") or "sem motivo informado"
        return {"erro": f"A IA não retornou resultado (possível bloqueio de conteúdo: {motivo})."}

    cand = candidates[0]
    parts = cand.get("content", {}).get("parts", [])
    if not parts:
        fr = cand.get("finishReason", "desconhecido")
        return {"erro": f"A IA não gerou conteúdo (finishReason: {fr}). "
                        f"Se o documento for uma imagem de baixa qualidade, tente uma foto mais nítida."}

    raw = parts[0].get("text", "")
    try:
        return _parse_json(raw)
    except Exception:  # noqa: BLE001
        return {"erro": "A IA respondeu, mas não consegui interpretar os campos (JSON inválido). "
                        "Tente novamente; se persistir, o documento pode estar ilegível."}
