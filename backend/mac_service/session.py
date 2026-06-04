"""Local JSON session store for jus.br token.

Completely independent of lexops' jusbr_session.py (which writes to Postgres).
Same token structure, same refresh logic — just persisted in ~/.lexops/jusbr_session.json.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_session_file: Path | None = None


def init(session_file: Path) -> None:
    global _session_file
    _session_file = session_file
    session_file.parent.mkdir(parents=True, exist_ok=True)


def _load_raw() -> dict | None:
    if not _session_file or not _session_file.exists():
        return None
    try:
        data = json.loads(_session_file.read_text())
        return data if isinstance(data, dict) and data.get("token") else None
    except Exception:
        return None


def _save_raw(data: dict) -> None:
    if not _session_file:
        return
    _session_file.parent.mkdir(parents=True, exist_ok=True)
    _session_file.write_text(json.dumps(data, indent=2, default=str))


def _jwt_exp(token: str | None) -> datetime | None:
    if not token:
        return None
    try:
        payload = token.split(".")[1] + "=="
        data = json.loads(base64.urlsafe_b64decode(payload).decode())
        exp = data.get("exp")
        if isinstance(exp, (int, float)):
            return datetime.fromtimestamp(float(exp), tz=timezone.utc)
    except Exception:
        pass
    return None


def _is_expired(iso: str | None) -> bool:
    if not iso:
        return False
    try:
        return datetime.fromisoformat(iso) <= datetime.now(timezone.utc)
    except Exception:
        return False


def _refresh(data: dict) -> dict | None:
    rt = data.get("refresh_token")
    endpoint = data.get("token_endpoint")
    if not rt or not endpoint or _is_expired(data.get("refresh_expires_at")):
        return None
    try:
        resp = httpx.post(
            endpoint,
            data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": "portalexterno-frontend"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        payload = resp.json()
    except Exception:
        return None
    if not isinstance(payload, dict) or not payload.get("access_token"):
        return None

    now = datetime.now(timezone.utc)
    merged = dict(data)
    merged["token"] = str(payload["access_token"])
    merged["refresh_token"] = str(payload.get("refresh_token") or rt)
    exp_dt = _jwt_exp(merged["token"])
    merged["expires_at"] = exp_dt.isoformat() if exp_dt else None
    ref_dt = _jwt_exp(merged["refresh_token"])
    merged["refresh_expires_at"] = ref_dt.isoformat() if ref_dt else None
    merged["captured_at"] = now.isoformat()
    _save_raw(merged)
    logger.info("jus.br session refreshed automatically.")
    return merged


def load_session() -> dict | None:
    data = _load_raw()
    if not data:
        return None
    if _is_expired(data.get("expires_at")):
        refreshed = _refresh(data)
        if refreshed:
            return refreshed
        logger.info("jus.br session expired and refresh failed.")
        return None
    return data


def save_session(data: dict) -> None:
    _save_raw(data)
    logger.info("jus.br session saved (expires_at=%s).", data.get("expires_at"))


def clear_session() -> None:
    if _session_file and _session_file.exists():
        _session_file.unlink()
    logger.info("jus.br session cleared.")


def session_summary() -> str:
    data = _load_raw()
    if not data:
        return "Sem sessão salva."
    exp = data.get("expires_at") or "desconhecida"
    expired = _is_expired(data.get("expires_at"))
    has_refresh = bool(data.get("refresh_token"))
    status = "⚠️ expirada" if expired else "✅ ativa"
    return f"Sessão jus.br: {status}\nExpira: {exp}\nRefresh token: {'sim' if has_refresh else 'não'}"
