"""
Busca emails trocados com um cliente específico via Gmail API.
Usa o email do cliente como filtro (from: ou to:).
"""

import base64
import json
from datetime import datetime
from pathlib import Path

import httpx

TOKENS_FILE = Path("/app/uploads/google_tokens.json")
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


def _load_tokens() -> dict | None:
    if not TOKENS_FILE.exists():
        return None
    return json.loads(TOKENS_FILE.read_text())


def _refresh(tokens: dict) -> dict:
    import os
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": tokens.get("refresh_token", ""),
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "grant_type": "refresh_token",
        },
    )
    if resp.is_success:
        new = {**tokens, **resp.json()}
        TOKENS_FILE.write_text(json.dumps(new))
        return new
    return tokens


def _decode_body(payload: dict) -> str:
    parts = payload.get("parts", [])
    if not parts:
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore") if data else ""
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    data = parts[0].get("body", {}).get("data", "")
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore") if data else ""


def _header(payload: dict, name: str) -> str:
    for h in payload.get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def buscar_emails_cliente(email_cliente: str, max_results: int = 50) -> list[dict]:
    """
    Retorna lista de emails trocados com o cliente ordenados por data desc.
    Cada item: {id, assunto, de, para, data, snippet, corpo}
    """
    tokens = _load_tokens()
    if not tokens:
        return []

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    query = f"from:{email_cliente} OR to:{email_cliente}"

    resp = httpx.get(
        f"{GMAIL_API}/users/me/messages",
        headers=headers,
        params={"q": query, "maxResults": max_results},
    )

    if resp.status_code == 401:
        tokens = _refresh(tokens)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        resp = httpx.get(
            f"{GMAIL_API}/users/me/messages",
            headers=headers,
            params={"q": query, "maxResults": max_results},
        )

    if not resp.is_success:
        return []

    messages = resp.json().get("messages", [])
    emails: list[dict] = []

    for msg_ref in messages:
        msg_resp = httpx.get(
            f"{GMAIL_API}/users/me/messages/{msg_ref['id']}",
            headers=headers,
            params={"format": "full"},
        )
        if not msg_resp.is_success:
            continue

        msg = msg_resp.json()
        payload = msg.get("payload", {})
        internal_date = int(msg.get("internalDate", 0)) // 1000
        data = datetime.fromtimestamp(internal_date).isoformat() if internal_date else None

        emails.append({
            "id": msg_ref["id"],
            "assunto": _header(payload, "Subject"),
            "de": _header(payload, "From"),
            "para": _header(payload, "To"),
            "data": data,
            "snippet": msg.get("snippet", ""),
            "corpo": _decode_body(payload)[:2000],
        })

    return sorted(emails, key=lambda e: e["data"] or "", reverse=True)
