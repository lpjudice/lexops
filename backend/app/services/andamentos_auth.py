"""Auth for the andamentos bot — PKCE login in the USER's real browser.

The headless server browser hits gov.br's anti-automation (captcha / QR that
needs real interaction). Instead, the gov.br login happens in the user's REAL
browser: we hand them a PKCE authorize URL (with offline_access), they log in
normally, and paste back the redirect URL containing the authorization code.
We exchange it for a token using our PKCE verifier.

Independent of lexops: stores the session in jusbr_sessions row id=2 (lexops
uses id=1, untouched). buscar_via_pdpj just takes a session_data dict.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import urllib.parse
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_SSO_AUTH = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth"
_SSO_TOKEN = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
_CLIENT_ID = "portalexterno-frontend"
_REDIRECT_URI = "https://portaldeservicos.pdpj.jus.br/home"
_SESSION_ROW_ID = 2  # lexops uses id=1; we stay independent on id=2

# In-memory PKCE state, keyed by chat_id (login is short-lived)
_pending: dict[int, str] = {}


# ── PKCE login URL ─────────────────────────────────────────────────────────────

def build_login_url(chat_id: int) -> str:
    raw = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    _pending[chat_id] = verifier

    params = {
        "client_id": _CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile offline_access",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_hex(8),
    }
    return f"{_SSO_AUTH}?{urllib.parse.urlencode(params)}"


def has_pending(chat_id: int) -> bool:
    return chat_id in _pending


_CODE_RE = re.compile(r"[?&]code=([^&\s]+)")


def extract_code(text: str) -> str | None:
    """Accept either the full redirect URL or a bare code."""
    m = _CODE_RE.search(text)
    if m:
        return urllib.parse.unquote(m.group(1))
    text = text.strip()
    # Bare code: keycloak codes look like UUID.UUID.UUID or long token
    if len(text) > 20 and " " not in text and "\n" not in text:
        return text
    return None


def exchange_code(chat_id: int, pasted: str) -> dict:
    """Exchange the pasted code for tokens. Returns the token payload dict.

    Raises ValueError with a user-facing message on failure.
    """
    verifier = _pending.get(chat_id)
    if not verifier:
        raise ValueError("Nenhum login em andamento. Envie um CNJ para iniciar.")

    code = extract_code(pasted)
    if not code:
        raise ValueError("Não encontrei o código na URL colada. Cole a URL inteira que apareceu após o login.")

    resp = httpx.post(
        _SSO_TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT_URI,
            "client_id": _CLIENT_ID,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    if resp.status_code != 200:
        logger.warning("Token exchange falhou: %d %s", resp.status_code, resp.text[:200])
        raise ValueError(
            "A troca do código falhou (pode ter expirado ou já ter sido usado). "
            "Envie o CNJ de novo para gerar um link novo."
        )
    payload = resp.json()
    if not payload.get("access_token"):
        raise ValueError("A resposta não trouxe access_token.")

    _pending.pop(chat_id, None)
    _save_session(payload)
    return payload


# ── Token introspection (premise test) ─────────────────────────────────────────

def describe_refresh(payload: dict) -> dict:
    rt = payload.get("refresh_token")
    if not rt:
        return {"has_refresh": False}
    try:
        p = rt.split(".")[1]
        p += "=" * (-len(p) % 4)
        claims = json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {"has_refresh": True, "typ": "?", "exp": None, "scope": None}
    exp = claims.get("exp")
    return {
        "has_refresh": True,
        "typ": claims.get("typ"),  # "Offline" = nunca expira por inatividade
        "scope": claims.get("scope"),
        "exp": datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else None,
    }


# ── Session storage (jusbr_sessions row id=2) ──────────────────────────────────

def _jwt_exp_iso(token: str | None) -> str | None:
    if not token:
        return None
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        exp = json.loads(base64.urlsafe_b64decode(p)).get("exp")
        return datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else None
    except Exception:
        return None


def _session_from_payload(payload: dict) -> dict:
    token = payload["access_token"]
    rt = payload.get("refresh_token")
    return {
        "token": token,
        "refresh_token": rt,
        "token_type": payload.get("token_type", "Bearer"),
        "token_endpoint": _SSO_TOKEN,
        "expires_at": _jwt_exp_iso(token),
        "refresh_expires_at": _jwt_exp_iso(rt),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "api_bases": ["https://portaldeservicos.pdpj.jus.br/api/v2"],
        "detected_url": "https://portaldeservicos.pdpj.jus.br/api/v2/processos",
        "referer": "https://portaldeservicos.pdpj.jus.br/home",
        "cookies": None,
        "extra_headers": {},
        "capture_kind": "andamentos_pkce",
    }


def _save_session(payload: dict) -> None:
    from app.database import SessionLocal
    from app.models.jusbr_session import JusbrSession

    data = _session_from_payload(payload)
    db = SessionLocal()
    try:
        row = db.query(JusbrSession).filter(JusbrSession.id == _SESSION_ROW_ID).first()
        if row:
            row.data = data
        else:
            db.add(JusbrSession(id=_SESSION_ROW_ID, data=data))
        db.commit()
        logger.info("Sessão andamentos (id=2) salva.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _is_expired(iso: str | None) -> bool:
    if not iso:
        return False
    try:
        return datetime.fromisoformat(iso) <= datetime.now(timezone.utc)
    except Exception:
        return False


def _refresh(data: dict) -> dict | None:
    rt = data.get("refresh_token")
    if not rt:
        return None
    try:
        resp = httpx.post(
            _SSO_TOKEN,
            data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": _CLIENT_ID},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except Exception:
        return None
    if resp.status_code != 200 or not resp.json().get("access_token"):
        logger.info("Refresh andamentos falhou: %d", resp.status_code)
        return None
    merged = _session_from_payload(resp.json())
    _save_session(resp.json())
    logger.info("Sessão andamentos renovada.")
    return merged


def load_session() -> dict | None:
    from app.database import SessionLocal
    from app.models.jusbr_session import JusbrSession

    db = SessionLocal()
    try:
        row = db.query(JusbrSession).filter(JusbrSession.id == _SESSION_ROW_ID).first()
        data = dict(row.data) if row and isinstance(row.data, dict) else None
    finally:
        db.close()

    if not data or not data.get("token"):
        return None
    if _is_expired(data.get("expires_at")):
        return _refresh(data)
    return data


def refresh_proactively() -> bool:
    """Called by a periodic job to keep the offline session alive."""
    data = load_session()
    if not data:
        return False
    # Always refresh to keep the session warm well within the window
    return bool(_refresh(data))
