"""
Leitura de diários via Gmail — serviço Recorte Digital OAB/ES.

Os emails chegam de oabes@recortedigital.adv.br com assunto:
  "Public. 0. DJSP 17/04/26 (42.8934403)"  ← 0 = sem publicação
  "Public. 1. DJES 15/04/26 (...)"          ← 1+ = com publicação

A lógica:
  - Public. 0. → cria entrada de confirmação "Sem publicações nesta edição"
  - Public. N. → extrai CNJs, tipo de ato, link PJe, datas
"""

import base64
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

TOKENS_FILE = Path("/app/uploads/google_tokens.json")
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"

# Regex CNJ padrão
CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
# Link PJe nos textos de publicação
PJE_RE = re.compile(r"https?://pje\.[a-z]+\.jus\.br/\S+")
# Número de publicações no assunto ("Public. 3.")
PUB_COUNT_RE = re.compile(r"Public\.\s*(\d+)\.")

# Código do diário → tribunal
TRIBUNAL_MAP = {
    "DJSP": "TJSP",
    "DJES": "TJES",
    "DJRJ": "TJRJ",
    "DJAM": "TJAM",
    "DJU":  "STJ",
}

TIPO_ATO_KEYWORDS: dict[str, list[str]] = {
    "sentenca":  ["sentença", "sentenca", "procedente", "improcedente", "extingo"],
    "acordao":   ["acórdão", "acordao", "provimento", "câmara", "turma"],
    "decisao":   ["decisão", "decisao", "indefiro", "defiro", "concedo"],
    "intimacao": ["intimado", "intimação", "intime-se", "intimacao", "intimação"],
    "citacao":   ["citado", "citação", "cite-se"],
    "despacho":  ["despacho", "vista", "manifeste-se"],
}


# ── Helpers OAuth ──────────────────────────────────────────────────────────────

def _load_tokens() -> dict | None:
    if not TOKENS_FILE.exists():
        return None
    return json.loads(TOKENS_FILE.read_text())


def _refresh_if_needed(tokens: dict) -> dict:
    import os
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": tokens.get("refresh_token", ""),
            "client_id":     os.getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "grant_type":    "refresh_token",
        },
    )
    if resp.is_success:
        new = {**tokens, **resp.json()}
        TOKENS_FILE.write_text(json.dumps(new))
        return new
    return tokens


# ── Decodificação do corpo ─────────────────────────────────────────────────────

def _b64_to_text(data: str) -> str:
    """Decodifica base64url → bytes → str (tenta UTF-8, depois latin-1)."""
    raw = base64.urlsafe_b64decode(data + "==")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _flatten_parts(payload: dict) -> list[dict]:
    """Recursivamente retorna todas as partes folha (sem sub-partes) do payload."""
    parts = payload.get("parts", [])
    if not parts:
        return [payload]
    result = []
    for part in parts:
        result.extend(_flatten_parts(part))
    return result


def _decode_body(payload: dict) -> str:
    """Retorna texto limpo (sem HTML) do payload de uma mensagem Gmail."""
    all_parts = _flatten_parts(payload)

    # Preferência: text/plain → text/html → primeiro part com data
    for mime_pref in ("text/plain", "text/html"):
        for part in all_parts:
            if part.get("mimeType") == mime_pref:
                data = part.get("body", {}).get("data", "")
                if data:
                    text = _b64_to_text(data)
                    if mime_pref == "text/html" or "<html" in text.lower():
                        return _html_to_text(text)
                    return text

    # Fallback: primeiro part com data
    for part in all_parts:
        data = part.get("body", {}).get("data", "")
        if data:
            text = _b64_to_text(data)
            if "<html" in text.lower():
                return _html_to_text(text)
            return text

    return ""


# ── Extração ───────────────────────────────────────────────────────────────────

def _pub_count(subject: str) -> int:
    """Retorna o número de publicações indicado no assunto (0 = sem publicação)."""
    m = PUB_COUNT_RE.search(subject)
    return int(m.group(1)) if m else 0


def _tribunais_do_assunto(subject: str) -> list[str]:
    found = []
    for code, tribunal in TRIBUNAL_MAP.items():
        if code in subject.upper():
            found.append(tribunal)
    return found or ["desconhecido"]


def _inferir_tipo_ato(texto: str) -> str:
    t = texto.lower()
    for tipo, kws in TIPO_ATO_KEYWORDS.items():
        if any(k in t for k in kws):
            return tipo
    return "outro"


def _extrair_data(texto: str, rotulo: str) -> str | None:
    """Tenta extrair 'DD/MM/YYYY' após um rótulo como 'Data de Disponibilização'."""
    m = re.search(rotulo + r"[:\s]+(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    if m:
        try:
            d, mo, y = m.group(1).split("/")
            return f"{y}-{mo}-{d}"
        except Exception:
            pass
    return None


# ── Sincronização principal ───────────────────────────────────────────────────

def sincronizar_gmail(days_back: int = 3) -> list[dict]:
    """
    Busca emails do Recorte Digital dos últimos N dias.
    Retorna lista de dicts compatíveis com o model Publicacao.
    """
    tokens = _load_tokens()
    if not tokens:
        return []

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    after_date = date.today() - timedelta(days=days_back)
    after_ts = int(datetime.combine(after_date, datetime.min.time()).timestamp())

    query = f'from:oabes@recortedigital.adv.br subject:"Public." after:{after_ts}'

    resp = httpx.get(
        f"{GMAIL_API}/users/me/messages",
        headers=headers,
        params={"q": query, "maxResults": 100},
    )

    if resp.status_code == 401:
        tokens = _refresh_if_needed(tokens)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        resp = httpx.get(
            f"{GMAIL_API}/users/me/messages",
            headers=headers,
            params={"q": query, "maxResults": 100},
        )

    if not resp.is_success:
        return []

    publicacoes: list[dict] = []
    raw_messages = resp.json().get("messages", [])

    # Deduplicar por threadId — mantém apenas a mensagem mais recente por thread.
    # O Gmail API retorna múltiplas mensagens do mesmo thread quando há respostas/reencaminhamentos.
    seen_threads: dict[str, dict] = {}
    for msg_ref in raw_messages:
        tid = msg_ref.get("threadId", msg_ref["id"])
        if tid not in seen_threads:
            seen_threads[tid] = msg_ref
    messages = list(seen_threads.values())

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        msg_resp = httpx.get(
            f"{GMAIL_API}/users/me/messages/{msg_id}",
            headers=headers,
            params={"format": "full"},
        )
        if not msg_resp.is_success:
            continue

        msg = msg_resp.json()
        payload = msg.get("payload", {})
        hdr = payload.get("headers", [])

        subject = next((h["value"] for h in hdr if h["name"] == "Subject"), "")
        thread_id = msg.get("threadId", msg_id)
        gmail_url = f"https://mail.google.com/mail/u/0/#all/{thread_id}"

        internal_date = int(msg.get("internalDate", 0)) // 1000
        data_pub = datetime.fromtimestamp(internal_date).date() if internal_date else date.today()

        texto = _decode_body(payload)
        tribunais = _tribunais_do_assunto(subject)
        count = _pub_count(subject)

        if count == 0:
            # ── Confirmação "sem publicações" ──────────────────────────────
            for tribunal in tribunais:
                publicacoes.append({
                    "fonte": "gmail",
                    "data_publicacao": data_pub,
                    "numero_cnj": None,
                    "tipo_ato": "outro",
                    "tribunal": tribunal,
                    "texto_resumo": "Sem publicações nesta edição.",
                    "texto_completo": texto[:3000],
                    "email_message_id": f"{msg_id}_sem_{tribunal}",
                    "url_fonte": gmail_url,
                })

        else:
            # ── Email com publicações reais ────────────────────────────────
            cnjs = list(set(CNJ_RE.findall(texto)))
            tipo_ato = _inferir_tipo_ato(texto)

            # Link PJe é mais preciso que o link do Gmail
            pje_links = PJE_RE.findall(texto)
            url_fonte = pje_links[0] if pje_links else gmail_url

            resumo = texto[:600].strip()

            if cnjs:
                for cnj in cnjs:
                    publicacoes.append({
                        "fonte": "gmail",
                        "data_publicacao": data_pub,
                        "numero_cnj": cnj,
                        "tipo_ato": tipo_ato,
                        "tribunal": tribunais[0] if tribunais else None,
                        "texto_resumo": resumo,
                        "texto_completo": texto[:10000],
                        "email_message_id": f"{msg_id}_{cnj}",
                        "url_fonte": url_fonte,
                    })
            else:
                # Publicação mencionada no assunto mas CNJ não encontrado no texto
                for tribunal in tribunais:
                    publicacoes.append({
                        "fonte": "gmail",
                        "data_publicacao": data_pub,
                        "numero_cnj": None,
                        "tipo_ato": tipo_ato,
                        "tribunal": tribunal,
                        "texto_resumo": resumo,
                        "texto_completo": texto[:10000],
                        "email_message_id": f"{msg_id}_pub_{tribunal}",
                        "url_fonte": url_fonte,
                    })

    return publicacoes
