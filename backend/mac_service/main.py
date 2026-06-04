"""FastAPI app for the Mac auth service.

Serves:
  - Screenshot API (Playwright current page)
  - Click / type / key endpoints
  - /viewer/{token} — mobile login UI
  - /health

Also starts:
  - Playwright browser manager
  - Telegram bot (long polling)
  - cloudflared tunnel (on demand, started when first auth needed)
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from .bot import create_dispatcher, run_polling, set_viewer_base_url
from .browser import BrowserManager
from .config import get_settings
from . import session as session_store

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

_cloudflared_proc: Optional[subprocess.Popen] = None
_cloudflared_url: str = ""


async def _start_cloudflared() -> str:
    """Start cloudflared quick tunnel and return the public URL."""
    global _cloudflared_proc, _cloudflared_url
    if _cloudflared_url:
        return _cloudflared_url

    loop = asyncio.get_event_loop()
    proc = await loop.run_in_executor(
        None,
        lambda: subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{settings.port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ),
    )
    _cloudflared_proc = proc

    url = ""
    for _ in range(60):  # wait up to 30s
        if proc.stdout is None:
            break
        line = await loop.run_in_executor(None, proc.stdout.readline)
        if not line:
            break
        logger.debug("cloudflared: %s", line.rstrip())
        m = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
        if m:
            url = m.group(0)
            break

    if not url:
        logger.warning("cloudflared não forneceu URL no tempo esperado.")
    else:
        logger.info("cloudflared URL: %s", url)
        _cloudflared_url = url
        set_viewer_base_url(url)

    return url


def _stop_cloudflared() -> None:
    global _cloudflared_proc, _cloudflared_url
    if _cloudflared_proc:
        _cloudflared_proc.terminate()
        _cloudflared_proc = None
    _cloudflared_url = ""
    set_viewer_base_url("")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await browser_mgr.start()
    dispatcher = create_dispatcher(settings.telegram_allowed_user_ids, browser_mgr)
    polling_task = asyncio.create_task(run_polling(settings.telegram_bot_token, dispatcher))
    # Pre-start cloudflared so the URL is ready when needed
    cf_task = asyncio.create_task(_start_cloudflared())
    logger.info("Mac auth service started on port %d", settings.port)
    try:
        yield
    finally:
        polling_task.cancel()
        cf_task.cancel()
        _stop_cloudflared()
        await browser_mgr.stop()


app = FastAPI(title="LexOps Auth Service", lifespan=lifespan)

_VIEWER_HTML = (Path(__file__).parent / "static" / "viewer.html").read_text()


@app.get("/health")
async def health():
    return {"ok": True, "cloudflared": bool(_cloudflared_url), "tunnel_url": _cloudflared_url or None}


@app.get("/viewer/{token}", response_class=HTMLResponse)
async def viewer(token: str):
    if not browser_mgr.verify_viewer_token(token):
        raise HTTPException(status_code=403, detail="Link expirado ou inválido.")
    html = _VIEWER_HTML.replace("__VIEWER_TOKEN__", token)
    return HTMLResponse(content=html)


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
