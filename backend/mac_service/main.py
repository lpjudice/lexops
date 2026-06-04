"""FastAPI app for the Mac auth service."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure mac_service/ is on sys.path for absolute sibling imports (bot, browser, etc.)
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

import tunnel
from bot import create_dispatcher, run_polling
from browser import BrowserManager
from config import get_settings
import session as session_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()
session_store.init(settings.session_file)

browser_mgr = BrowserManager(
    profile_dir=settings.playwright_profile_dir,
    portal_url=settings.portal_url,
    auth_secret=settings.auth_secret,
    link_ttl=settings.auth_link_ttl_seconds,
)

_VIEWER_HTML = (_HERE / "static" / "viewer.html").read_text()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await browser_mgr.start()
    dispatcher = create_dispatcher(settings.telegram_allowed_user_ids, browser_mgr)
    polling_task = asyncio.create_task(run_polling(settings.telegram_bot_token, dispatcher))
    cf_task = asyncio.create_task(tunnel.start(settings.port))
    logger.info("Mac auth service started on port %d", settings.port)
    try:
        yield
    finally:
        polling_task.cancel()
        cf_task.cancel()
        tunnel.stop()
        await browser_mgr.stop()


app = FastAPI(title="LexOps Auth Service", lifespan=lifespan)


@app.get("/health")
async def health():
    url = tunnel._url
    return {"ok": True, "cloudflared": bool(url), "tunnel_url": url or None}


@app.get("/viewer/{token}", response_class=HTMLResponse)
async def viewer(token: str):
    if not browser_mgr.verify_viewer_token(token):
        raise HTTPException(status_code=403, detail="Link expirado ou inválido.")
    return HTMLResponse(_VIEWER_HTML.replace("__VIEWER_TOKEN__", token))


@app.get("/screenshot.png")
async def screenshot(token: str = Query(...)):
    if not browser_mgr.verify_viewer_token(token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    try:
        png = await browser_mgr.screenshot_png()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return Response(content=png, media_type="image/png")


class ClickPayload(BaseModel):
    x: int
    y: int
    token: str


class TypePayload(BaseModel):
    text: str
    token: str


class KeyPayload(BaseModel):
    key: str
    token: str


@app.post("/click")
async def click(payload: ClickPayload):
    if not browser_mgr.verify_viewer_token(payload.token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    await browser_mgr.click(payload.x, payload.y)
    return {"ok": True}


@app.post("/type")
async def type_text(payload: TypePayload):
    if not browser_mgr.verify_viewer_token(payload.token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    await browser_mgr.type_text(payload.text)
    return {"ok": True}


@app.post("/key")
async def press_key(payload: KeyPayload):
    if not browser_mgr.verify_viewer_token(payload.token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    await browser_mgr.press_key(payload.key)
    return {"ok": True}
