"""Playwright BrowserManager for jus.br/gov.br authentication on Fly.io.

Fly.io's IP is accepted by the PDPJ portal (unlike residential IPs).
Runs headless — the user interacts via the screenshot viewer at
/api/andamentos/viewer/{token}.

Token capture: intercepts the SSO openid-connect/token response and saves
it to the existing JusbrSession Postgres table via jusbr_session.py.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

logger = logging.getLogger(__name__)

_SSO_TOKEN_PATTERN = "openid-connect/token"
_PROFILE_DIR = Path("/app/backend/uploads/.playwright-profile")


def _sign(secret: str, subject: str, ttl: int) -> tuple[str, int]:
    exp = int(time.time()) + ttl
    msg = f"{subject}:{exp}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    payload = base64.urlsafe_b64encode(f"{subject}:{exp}:{sig}".encode()).decode().rstrip("=")
    return payload, exp


def verify_viewer_token(secret: str, token: str) -> bool:
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        subject, exp_str, sig = decoded.rsplit(":", 2)
        if int(exp_str) < int(time.time()):
            return False
        msg = f"{subject}:{exp_str}".encode()
        expected = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


class BrowserManager:
    def __init__(self, viewer_secret: str, link_ttl: int = 600) -> None:
        self._secret = viewer_secret
        self._link_ttl = link_ttl

        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()

        self.auth_event = asyncio.Event()
        self.captured_token: Optional[str] = None

    async def start(self) -> None:
        async with self._lock:
            if self._context:
                return
            _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(_PROFILE_DIR),
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
                viewport={"width": 1440, "height": 900},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            self._context.on("response", self._on_response)
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            logger.info("Playwright context started (profile: %s)", _PROFILE_DIR)

    async def stop(self) -> None:
        async with self._lock:
            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass
            if self._playwright:
                await self._playwright.stop()
            self._context = None
            self._page = None
            self._playwright = None

    async def _ensure_page(self) -> Page:
        await self.start()
        assert self._page is not None
        return self._page

    async def navigate_to_portal(self) -> None:
        page = await self._ensure_page()
        url = "https://portaldeservicos.pdpj.jus.br/home"
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        logger.info("Navigated to %s → %s", url, page.url)

    async def screenshot_png(self) -> bytes:
        page = await self._ensure_page()
        return await page.screenshot(type="png", full_page=False)

    async def click(self, x: int, y: int) -> None:
        page = await self._ensure_page()
        await page.mouse.click(x, y)

    async def type_text(self, text: str) -> None:
        page = await self._ensure_page()
        await page.keyboard.type(text, delay=40)

    async def press_key(self, key: str) -> None:
        page = await self._ensure_page()
        await page.keyboard.press(key)

    async def reset_session(self) -> None:
        page = await self._ensure_page()
        if self._context:
            await self._context.clear_cookies()
        try:
            await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        except Exception:
            pass
        await page.goto("about:blank")
        self.captured_token = None
        self.auth_event.clear()

    def create_viewer_token(self) -> tuple[str, int]:
        return _sign(self._secret, "viewer", self._link_ttl)

    def verify_token(self, token: str) -> bool:
        return verify_viewer_token(self._secret, token)

    def reset_auth_event(self) -> None:
        self.captured_token = None
        self.auth_event.clear()

    async def wait_for_auth(self, timeout_seconds: int = 600) -> str:
        try:
            await asyncio.wait_for(self.auth_event.wait(), timeout=float(timeout_seconds))
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Timeout aguardando autenticação gov.br.") from exc
        assert self.captured_token is not None
        return self.captured_token

    async def _on_response(self, response: Response) -> None:
        if _SSO_TOKEN_PATTERN not in response.url:
            return
        try:
            body = await response.text()
            data = json.loads(body)
        except Exception:
            return
        if not isinstance(data, dict) or not data.get("access_token"):
            return

        # Reuse existing session save logic (saves to Postgres JusbrSession table)
        try:
            from app.services.consulta_processual.jusbr_session import save_session_from_capture
            save_session_from_capture(body)
            self.captured_token = str(data["access_token"])
            self.auth_event.set()
            logger.info("access_token interceptado e salvo na sessão jus.br.")
        except Exception:
            logger.exception("Erro ao salvar token interceptado.")
