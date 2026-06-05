"""PKCE com offline_access para a sessão jus.br do LEXOPS (linha id=1).

Equivalente ao `andamentos_auth` (que serve o bot do Telegram em id=2), mas
opera sobre a sessão usada pelo lexops/processos. Independente de
`consulta_processual/jusbr_session.py` (travado): grava direto via SQLAlchemy
mantendo o MESMO formato do dado, para que o `load_session()` travado leia
exatamente como sempre leu.

Fluxo:
  1) POST /jusbr/pkce/start         → backend gera URL de autorização (gov.br),
                                       guarda o code_verifier em memória sob
                                       um state_id curto.
  2) usuário loga no gov.br no SEU navegador (sem captcha pra humano)
  3) gov.br redireciona para portaldeservicos.pdpj.jus.br/home?code=XXX
  4) usuário copia a URL e cola na UI do lexops
  5) POST /jusbr/pkce/finish        → backend troca code por tokens (PKCE) e
                                       grava na sessão id=1. O refresh token é
                                       Offline (não expira), e o cron já existente
                                       (_refresh_jusbr_session) renova periodicamente.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import time
import urllib.parse
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_SSO_AUTH = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth"
_SSO_TOKEN = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
_CLIENT_ID = "portalexterno-frontend"
_REDIRECT_URI = "https://portaldeservicos.pdpj.jus.br/home"
_SESSION_ROW_ID = 1  # lexops sempre lê desta linha; o bot usa id=2 e fica isolado
_PENDING_TTL = 600  # 10 minutos

# state_id → (code_verifier, criado_at)
_pending: dict[str, tuple[str, float]] = {}


def _gc_expired() -> None:
    cutoff = time.time() - _PENDING_TTL
    expirados = [k for k, (_, t) in _pending.items() if t < cutoff]
    for k in expirados:
        _pending.pop(k, None)


def build_login_url() -> dict[str, str]:
    """Gera URL PKCE + state_id. Retorna {url, state_id, expires_in}."""
    _gc_expired()
    raw = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_hex(8)
    state_id = secrets.token_urlsafe(16)
    _pending[state_id] = (verifier, time.time())

    params = {
        "client_id": _CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile offline_access",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return {
        "url": f"{_SSO_AUTH}?{urllib.parse.urlencode(params)}",
        "state_id": state_id,
        "expires_in": _PENDING_TTL,
    }


_CODE_RE = re.compile(r"[?&]code=([^&\s]+)")


def _extract_code(text: str) -> str | None:
    m = _CODE_RE.search(text or "")
    if m:
        return urllib.parse.unquote(m.group(1))
    t = (text or "").strip()
    if len(t) > 20 and " " not in t and "\n" not in t:
        return t
    return None


def exchange_code(state_id: str, pasted: str) -> dict:
    """Troca code por tokens e salva na sessão id=1. Retorna dict de status."""
    _gc_expired()
    entry = _pending.pop(state_id, None)
    if not entry:
        raise ValueError("Sessão de login expirada ou inválida. Gere um link novo.")
    verifier, _ = entry

    code = _extract_code(pasted)
    if not code:
        raise ValueError("Não encontrei o `code=` na URL colada. Cole a URL inteira que o gov.br devolveu.")

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
        logger.warning("lexops_pkce exchange falhou: %d %s", resp.status_code, resp.text[:200])
        raise ValueError(
            "A troca do código falhou (pode ter expirado ou já ter sido usado). "
            "Gere um novo link e tente de novo."
        )
    payload = resp.json()
    if not payload.get("access_token"):
        raise ValueError("Resposta sem access_token.")

    _save_session(payload)
    info = _describe_refresh(payload)
    return {
        "ok": True,
        "expires_at": _jwt_exp_iso(payload["access_token"]),
        "refresh_type": info.get("typ"),
        "refresh_scope": info.get("scope"),
        "refresh_expires_at": info.get("exp"),
    }


# ── Introspecção / helpers ────────────────────────────────────────────────────

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


def _describe_refresh(payload: dict) -> dict:
    rt = payload.get("refresh_token")
    if not rt:
        return {}
    try:
        p = rt.split(".")[1]
        p += "=" * (-len(p) % 4)
        claims = json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}
    exp = claims.get("exp")
    return {
        "typ": claims.get("typ"),  # "Offline" = nunca expira por inatividade
        "scope": claims.get("scope"),
        "exp": datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else None,
    }


def _session_from_payload(payload: dict) -> dict:
    """Espelha o formato que `jusbr_session.py` (travado) lê."""
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
        "capture_kind": "lexops_pkce_offline",
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
        logger.info("Sessão lexops (id=1) salva via PKCE [%s].", data.get("capture_kind"))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
