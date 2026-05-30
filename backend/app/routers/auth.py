import os
import uuid

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.google_master_tokens import save_master_google_tokens
from app.services.google_calendar import exchange_code, get_auth_url, google_conectado

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
    try:
        exchange_code(code)
    except Exception:
        return RedirectResponse(f"{_frontend_url()}/configuracoes?google=erro")
    return RedirectResponse(f"{_frontend_url()}/configuracoes?google=conectado")


@router.get("/google/status")
def google_status():
    from app.services.google_calendar import _load_tokens, _refresh_token
    email = None
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
                        save_master_google_tokens(tokens)
    except Exception:
        pass
    return {"conectado": google_conectado(), "email": email}


# ── Per-user personal Google account (gmail.readonly) ─────────────────────────

def _user_redirect_uri() -> str:
    # Derive from GOOGLE_REDIRECT_URI (already registered + correct domain/path prefix)
    master = os.getenv("GOOGLE_REDIRECT_URI", "")
    if master and "/auth/google/callback" in master:
        return master.replace("/auth/google/callback", "/auth/google/user/callback")
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    return f"{backend_url}/auth/google/user/callback"


def _user_consent_redirect(state: str) -> RedirectResponse:
    cfg = _get_client_config()
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": _user_redirect_uri(),
        "response_type": "code",
        "scope": USER_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,  # passed back in callback
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{qs}")


@router.get("/google/user")
def google_user_login(usuario_id: str):
    """Redirect the user to Google consent screen for their personal Gmail."""
    return _user_consent_redirect(usuario_id)


@router.get("/google/user/extra")
def google_user_extra_login(usuario_id: str):
    """Conecta uma 2ª caixa de Gmail (extra) do usuário, em slot próprio."""
    return _user_consent_redirect(f"{usuario_id}:extra")


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

    # state pode ser "<usuario_id>" (conta principal) ou "<usuario_id>:extra" (extra)
    is_extra = state.endswith(":extra")
    usuario_id = state[: -len(":extra")] if is_extra else state
    feedback = "google_user_extra" if is_extra else "google_user"

    if not resp.is_success:
        return RedirectResponse(f"{_frontend_url()}/configuracoes?{feedback}=erro")

    tokens = resp.json()

    # Fetch the user's Gmail address and cache it in tokens
    r = httpx.get(
        "https://www.googleapis.com/gmail/v1/users/me/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5,
    )
    if r.is_success:
        tokens["email"] = r.json().get("emailAddress", "")

    # Store in DB — slot principal ou extra, sem um sobrescrever o outro
    try:
        u = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
        if u:
            if is_extra:
                u.google_tokens_extra = tokens
            else:
                u.google_tokens = tokens
            db.commit()
    except Exception as e:
        print(f"[auth] failed to save user tokens: {e}", flush=True)
        return RedirectResponse(f"{_frontend_url()}/configuracoes?{feedback}=erro")

    return RedirectResponse(f"{_frontend_url()}/configuracoes?{feedback}=conectado")


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


@router.get("/google/user/extra/status")
def google_user_extra_status(usuario_id: str, db: Session = Depends(get_db)):
    """Whether the user has an EXTRA Google account connected."""
    from app.models.usuario import Usuario
    u = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
    if not u or not u.google_tokens_extra:
        return {"conectado": False, "email": None}
    email = u.google_tokens_extra.get("email") if isinstance(u.google_tokens_extra, dict) else None
    return {"conectado": True, "email": email}


@router.delete("/google/user/extra")
def google_user_extra_disconnect(usuario_id: str, db: Session = Depends(get_db)):
    """Remove the EXTRA Google tokens for this user."""
    from app.models.usuario import Usuario
    u = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
    if u:
        u.google_tokens_extra = None
        db.commit()
    return {"ok": True}
