import json
from pathlib import Path

import httpx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.services.google_calendar import exchange_code, get_auth_url, google_conectado

TOKENS_FILE = Path("/app/uploads/google_tokens.json")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google")
def google_login():
    return RedirectResponse(get_auth_url())


@router.get("/google/callback")
def google_callback(code: str):
    exchange_code(code)
    return RedirectResponse("http://localhost:5174/?google=conectado")


@router.get("/google/status")
def google_status():
    from app.services.google_calendar import _load_tokens, _refresh_token
    email = None
    if TOKENS_FILE.exists():
        try:
            tokens = _load_tokens()
            if tokens:
                # Use cached email if already stored
                if tokens.get("email"):
                    email = tokens["email"]
                else:
                    # Gmail profile endpoint works with gmail scope (no openid needed)
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
