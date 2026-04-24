import json
import os
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.google_calendar import exchange_code, get_auth_url, google_conectado

TOKENS_FILE = Path("/app/uploads/google_tokens.json")

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = " ".join([
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
])

# Scopes for per-user personal Gmail (read only — no calendar/drive)
USER_SCOPES = " ".join([
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
])


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5174")


def _get_client_config() -> dict:
    return {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
    }


# ── Master account OAuth (calendar + gmail send + drive) ──────────────────────

@router.get("/google")
def google_login():
    return RedirectResponse(get_auth_url())


@router.get("/google/callback")
def google_callback(code: str):
    exchange_code(code)
    return RedirectResponse(f"{_frontend_url()}/?google=conectado")


@router.get("/google/status")
def google_status():
    from app.services.google_calendar import _load_tokens, _refresh_token
    email = None
    if TOKENS_FILE.exists():
        try:
            tokens = _load_tokens()
            if tokens:
                if tokens.get("email"):
                    email = tokens["email"]
                else:
                    r = httpx.get(
                        "https://www.googleapis.com/gmail/v1/users/me/profile",
                        headers={"Authorization": f"Bearer {tokens['access_token']}"},
                        timeout=5,
                    )
                    if r.status_code == 401 and tokens.get("refresh_token"):
                        tokens = _refresh_token(tokens)
                        r = httpx.get(
                            "https://www.googleapis.com/gmail/v1/users/me/profile",
                            headers={"Authorization": f"Bearer {tokens['access_token']}"},
                            timeout=5,
                        )
                    if r.status_code == 200:
                        email = r.json().get("emailAddress")
                        if email:
                            tokens["email"] = email
                            TOKENS_FILE.write_text(json.dumps(tokens))
        except Exception:
            pass
    return {"conectado": google_conectado(), "email": email}


# ── Per-user personal Google account (gmail.readonly) ─────────────────────────

def _user_redirect_uri() -> str:
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    return f"{backend_url}/auth/google/user/callback"


@router.get("/google/user")
def google_user_login(usuario_id: str):
    """Redirect the user to Google consent screen for their personal Gmail."""
    cfg = _get_client_config()
    redirect_uri = _user_redirect_uri()
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": USER_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": usuario_id,  # passed back in callback
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{qs}"
    return RedirectResponse(url)


@router.get("/google/user/callback")
def google_user_callback(code: str, state: str, db: Session = Depends(get_db)):
    """Exchange code, store tokens in usuarios.google_tokens, redirect to frontend."""
    from app.models.usuario import Usuario

    cfg = _get_client_config()
    redirect_uri = _user_redirect_uri()

    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    if not resp.is_success:
        return RedirectResponse(f"{_frontend_url()}/configuracoes?google_user=erro")

    tokens = resp.json()

    # Fetch the user's Gmail address and cache it in tokens
    r = httpx.get(
        "https://www.googleapis.com/gmail/v1/users/me/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5,
    )
    if r.is_success:
        tokens["email"] = r.json().get("emailAddress", "")

    # Store in DB
    try:
        u = db.query(Usuario).filter(Usuario.id == uuid.UUID(state)).first()
        if u:
            u.google_tokens = tokens
            db.commit()
    except Exception as e:
        print(f"[auth] failed to save user tokens: {e}", flush=True)
        return RedirectResponse(f"{_frontend_url()}/configuracoes?google_user=erro")

    return RedirectResponse(f"{_frontend_url()}/configuracoes?google_user=conectado")


@router.get("/google/user/status")
def google_user_status(usuario_id: str, db: Session = Depends(get_db)):
    """Return whether the user has a personal Google account connected."""
    from app.models.usuario import Usuario
    u = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
    if not u or not u.google_tokens:
        return {"conectado": False, "email": None}
    email = u.google_tokens.get("email") if isinstance(u.google_tokens, dict) else None
    return {"conectado": True, "email": email}


@router.delete("/google/user")
def google_user_disconnect(usuario_id: str, db: Session = Depends(get_db)):
    """Remove personal Google tokens for this user."""
    from app.models.usuario import Usuario
    u = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
    if u:
        u.google_tokens = None
        db.commit()
    return {"ok": True}
