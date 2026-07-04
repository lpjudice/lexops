"""
Gmail sync service — fetches emails related to a client from a Gmail account
and upserts them into emails_cliente with deduplication.

Supports two account types:
  - "master": tokens stored in the persistent uploads volume
  - "<usuario_id>": tokens stored in usuarios.google_tokens JSONB
"""

import base64
import os
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

import httpx
from app.services.google_master_tokens import load_master_google_tokens, save_master_google_tokens

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


# ── Token helpers ──────────────────────────────────────────────────────────────

def _get_client_config() -> dict:
    return {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
    }


def _refresh(tokens: dict) -> dict:
    cfg = _get_client_config()
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": tokens["refresh_token"],
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    return {**tokens, **resp.json()}


def load_tokens_master() -> dict | None:
    return load_master_google_tokens()


def save_tokens_master(tokens: dict) -> None:
    save_master_google_tokens(tokens)


def _split_conta(conta_google: str) -> tuple[str, bool]:
    """Separa o id do usuário do sufixo ':extra'. Retorna (usuario_id, is_extra)."""
    if conta_google.endswith(":extra"):
        return conta_google[: -len(":extra")], True
    return conta_google, False


def load_tokens_user(usuario_id: str, db_session: Any, extra: bool = False) -> dict | None:
    from app.models.usuario import Usuario
    u = db_session.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
    if not u:
        return None
    tk = u.google_tokens_extra if extra else u.google_tokens
    return tk or None


def save_tokens_user(usuario_id: str, tokens: dict, db_session: Any, extra: bool = False) -> None:
    from app.models.usuario import Usuario
    u = db_session.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
    if u:
        if extra:
            u.google_tokens_extra = tokens
        else:
            u.google_tokens = tokens
        db_session.commit()


def get_valid_tokens(conta_google: str, db_session: Any) -> dict | None:
    """Load tokens for a given account, refreshing if needed.
    conta_google: 'master' | '<usuario_id>' | '<usuario_id>:extra'."""
    if conta_google == "master":
        tokens = load_tokens_master()
        uid, is_extra = None, False
    else:
        uid, is_extra = _split_conta(conta_google)
        tokens = load_tokens_user(uid, db_session, extra=is_extra)

    if not tokens:
        return None

    # Quick test — if access_token works, return as-is
    r = httpx.get(
        f"{GMAIL_API}/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5,
    )
    if r.status_code == 200:
        return tokens

    if r.status_code == 401 and tokens.get("refresh_token"):
        try:
            new_tokens = _refresh(tokens)
            if conta_google == "master":
                save_tokens_master(new_tokens)
            else:
                save_tokens_user(uid, new_tokens, db_session, extra=is_extra)
            return new_tokens
        except Exception as e:
            print(f"[gmail_sync] refresh failed for {conta_google}: {e}", flush=True)

    return None


def get_account_email(tokens: dict) -> str | None:
    r = httpx.get(
        f"{GMAIL_API}/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5,
    )
    if r.is_success:
        return r.json().get("emailAddress")
    return None


# ── Email parsing ──────────────────────────────────────────────────────────────

def _header(headers: list[dict], name: str) -> str | None:
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value")
    return None


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        return None


# ── Search & fetch ─────────────────────────────────────────────────────────────

def _search_messages(tokens: dict, query: str, max_results: int = 50) -> list[str]:
    """Return list of message IDs matching the query."""
    message_ids = []
    params = {"q": query, "maxResults": min(max_results, 500)}
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    while True:
        r = httpx.get(f"{GMAIL_API}/messages", headers=headers, params=params, timeout=15)
        if not r.is_success:
            break
        data = r.json()
        for m in data.get("messages", []):
            message_ids.append(m["id"])
        page_token = data.get("nextPageToken")
        if not page_token or len(message_ids) >= max_results:
            break
        params["pageToken"] = page_token

    return message_ids[:max_results]


def _fetch_message(tokens: dict, message_id: str) -> dict | None:
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    # Pass metadataHeaders as repeated params — comma-separated string is NOT supported by the API
    r = httpx.get(
        f"{GMAIL_API}/messages/{message_id}",
        headers=headers,
        params=[
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "To"),
            ("metadataHeaders", "Cc"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "Date"),
        ],
        timeout=10,
    )
    if not r.is_success:
        return None
    return r.json()


# ── Main sync function ─────────────────────────────────────────────────────────

def sync_emails_for_client(
    cliente_id: str,
    conta_google: str,
    db_session: Any,
    emails_cliente: list[str],
    max_results: int = 50,
) -> dict:
    """
    Search Gmail for emails involving any of the client's email addresses,
    then upsert new records into emails_cliente (deduplication by gmail_message_id).

    Returns: {"synced": int, "new": int, "error": str | None}
    """
    from app.models.email_cliente import EmailCliente

    tokens = get_valid_tokens(conta_google, db_session)
    if not tokens:
        return {"synced": 0, "new": 0, "error": "Conta Google não conectada."}

    conta_email = get_account_email(tokens)

    if not emails_cliente:
        return {"synced": 0, "new": 0, "error": "Cliente sem endereços de email cadastrados."}

    # Build Gmail search query: from or to any of the client emails
    parts = [f"(from:{e} OR to:{e})" for e in emails_cliente]
    query = " OR ".join(parts)

    message_ids = _search_messages(tokens, query, max_results)
    if not message_ids:
        return {"synced": 0, "new": 0, "error": None}

    new_count = 0
    novos_records: list = []
    for msg_id in message_ids:
        # Skip if already in DB
        existing = db_session.query(EmailCliente).filter(
            EmailCliente.gmail_message_id == msg_id
        ).first()
        if existing:
            continue

        raw = _fetch_message(tokens, msg_id)
        if not raw:
            continue

        hdrs = raw.get("payload", {}).get("headers", [])
        from_raw = _header(hdrs, "From") or ""
        to_raw = _header(hdrs, "To") or ""
        cc_raw = _header(hdrs, "Cc") or ""
        subject = _header(hdrs, "Subject")
        date_str = _header(hdrs, "Date")

        # internalDate is epoch-ms (string) — more reliable than the Date header
        internal_ms = int(raw.get("internalDate") or 0)
        if internal_ms:
            data = datetime.fromtimestamp(internal_ms / 1000, tz=timezone.utc)
        else:
            data = _parse_date(date_str)

        destinatarios = ", ".join(filter(None, [to_raw, cc_raw]))

        email_record = EmailCliente(
            cliente_id=uuid.UUID(cliente_id),
            gmail_message_id=msg_id,
            conta_google=conta_google,
            conta_email=conta_email,
            remetente=from_raw or None,
            destinatarios=destinatarios or None,
            assunto=subject,
            snippet=raw.get("snippet"),
            thread_id=raw.get("threadId"),
            data=data,
            lido=True,
        )
        db_session.add(email_record)
        novos_records.append(email_record)
        new_count += 1

    if novos_records:
        from app.services.ia_email_classificacao import classificar_lote
        categorias = classificar_lote([
            {"remetente": r.remetente, "assunto": r.assunto, "snippet": r.snippet}
            for r in novos_records
        ])
        for record, categoria in zip(novos_records, categorias):
            record.categoria = categoria

    try:
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        return {"synced": len(message_ids), "new": 0, "error": str(e)}

    return {"synced": len(message_ids), "new": new_count, "error": None}
