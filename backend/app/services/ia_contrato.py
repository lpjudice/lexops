"""
Extração dos CONTRATANTES de um contrato (PDF/imagem) via Gemini 2.5 Flash.

Lê o documento (não persiste) e retorna a lista de contratantes — o lado do
cliente que contrata os serviços — com os campos que espelham o cadastro de
Cliente, para popular/atualizar o cadastro após validação humana. Exclui o
CONTRATADO (o escritório/advogado). Molde e tratamento de erro seguem
`escritura_ia.py`; Gemini Flash lê PDF nativamente e é barato para OCR.
"""
import base64
import json
import re

from app.config import settings

_MODEL = "gemini-2.5-flash"
_MIMES_OK = ("application/pdf", "image/png", "image/jpeg", "image/webp")

_PROMPT = """Você é um assistente jurídico. Analise o CONTRATO em anexo e identifique \
os CONTRATANTES — ou seja, a parte que CONTRATA os serviços (o cliente). NÃO inclua o \
CONTRATADO/prestador (o escritório de advocacia ou advogado, tipicamente "Pimenta Júdice" \
ou "Lucas Pimenta Júdice"). Pode haver um ou vários contratantes (ex.: marido e esposa, \
sócios, uma empresa e seu representante).

Para CADA contratante, extraia os campos abaixo. Não invente nada: se um campo não estiver \
no documento, use "" (string vazia). CPF/CNPJ e telefone: mantenha só os dígitos e a \
pontuação como aparecem no documento.

Extraia também os dados FINANCEIROS do contrato (honorários), se constarem.

Responda SOMENTE com JSON válido (sem markdown), neste formato exato:
{
  "contratantes": [
    {
      "nome": "nome completo da pessoa física OU razão social da pessoa jurídica",
      "tipo": "PF ou PJ",
      "cpf_cnpj": "CPF (PF) ou CNPJ (PJ), como aparece no documento",
      "email": "e-mail, se houver",
      "telefone": "telefone, se houver",
      "endereco": "endereço completo em uma linha, se houver",
      "estado_civil": "somente para PF, se constar",
      "profissao": "somente para PF, se constar"
    }
  ],
  "financeiro": {
    "valor_honorarios": <número dos honorários FIXOS em reais, só dígitos e ponto decimal, ou null>,
    "tem_exito": <true|false — se há honorários de êxito/sucumbência>,
    "percentual_exito": <percentual de êxito como número (ex.: 15 para 15%), ou null>,
    "valor_causa": <valor da causa em reais, só dígitos e ponto decimal, ou null>,
    "data_vencimento": "data de vencimento/pagamento no formato AAAA-MM-DD, ou \\"\\"",
    "condicao_pagamento": "condição de pagamento em texto (ex.: parcela única, 3x), ou \\"\\"",
    "data_contrato": "data de assinatura/celebração do contrato em AAAA-MM-DD, ou \\"\\""
  }
}

Regras:
- Um item por contratante. Se houver representante de uma PJ, o item é a PJ (tipo PJ) e, se \
quiser, coloque o representante em "observacao" — mas NÃO crie um campo novo; apenas os \
campos listados são aceitos.
- "tipo": use "PJ" quando houver CNPJ/razão social; senão "PF".
- Não inclua o contratado/escritório na lista.
- Financeiro: extraia só o que está no documento; se não houver, use null/false/"". \
"valor_honorarios" é o valor FIXO; se o contrato for só de êxito, use null e tem_exito=true."""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if m:
        raw = m.group(1).strip()
    return json.loads(raw)


def extrair_contratantes(file_bytes: bytes, mime: str) -> dict:
    """
    Extrai a lista de contratantes do contrato. Retorna
    {"contratantes": [...]} em caso de sucesso, ou {"erro": ...} detalhado.
    """
    if not settings.google_ai_api_key:
        return {"erro": "GOOGLE_AI_API_KEY não configurada no servidor."}
    if mime not in _MIMES_OK:
        return {"erro": f"Formato não suportado ({mime}). Envie PDF, PNG, JPG ou WEBP."}
    tamanho_mb = len(file_bytes) / (1024 * 1024)
    if tamanho_mb > 20:
        return {"erro": f"Arquivo muito grande ({tamanho_mb:.1f} MB). O limite é ~20 MB; "
                        f"reduza a resolução do PDF e tente de novo."}

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
        return {"erro": "A leitura demorou demais (timeout). O contrato pode ser grande — "
                        "tente enviar só as páginas de qualificação das partes."}
    except httpx.RequestError as e:
        return {"erro": f"Falha de conexão com a IA: {e}"}

    if resp.status_code != 200:
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
        return {"erro": f"A IA não gerou conteúdo (finishReason: {fr})."}

    raw = parts[0].get("text", "")
    try:
        parsed = _parse_json(raw)
    except Exception:  # noqa: BLE001
        return {"erro": "A IA respondeu, mas não consegui interpretar os campos (JSON inválido). "
                        "Tente novamente; se persistir, o documento pode estar ilegível."}

    contratantes = parsed.get("contratantes")
    if not isinstance(contratantes, list):
        # Tolera a IA devolver um único objeto sem o wrapper.
        if isinstance(parsed, dict) and parsed.get("nome"):
            contratantes = [parsed]
        else:
            return {"erro": "A IA não encontrou contratantes no documento."}

    # Normaliza cada item: só as chaves conhecidas, strings limpas, tipo padrão PF.
    campos = ("nome", "tipo", "cpf_cnpj", "email", "telefone", "endereco", "estado_civil", "profissao")
    limpos = []
    for item in contratantes:
        if not isinstance(item, dict):
            continue
        reg = {k: (str(item.get(k) or "").strip()) for k in campos}
        if not reg["nome"]:
            continue
        reg["tipo"] = "PJ" if reg["tipo"].upper() == "PJ" else "PF"
        limpos.append(reg)

    if not limpos:
        return {"erro": "A IA não encontrou contratantes com nome no documento."}

    return {"contratantes": limpos, "financeiro": _normalizar_financeiro(parsed.get("financeiro"))}


def _num(v) -> float | None:
    """Coage número da IA (aceita int/float ou string '1.234,56' / '1234.56') para float."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    # remove tudo que não é dígito, vírgula, ponto ou sinal
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    # se tem vírgula e ponto, assume ponto=milhar e vírgula=decimal (padrão BR)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _normalizar_financeiro(fin) -> dict:
    if not isinstance(fin, dict):
        fin = {}
    return {
        "valor_honorarios": _num(fin.get("valor_honorarios")),
        "tem_exito": bool(fin.get("tem_exito")),
        "percentual_exito": _num(fin.get("percentual_exito")),
        "valor_causa": _num(fin.get("valor_causa")),
        "data_vencimento": str(fin.get("data_vencimento") or "").strip(),
        "condicao_pagamento": str(fin.get("condicao_pagamento") or "").strip(),
        "data_contrato": str(fin.get("data_contrato") or "").strip(),
    }
