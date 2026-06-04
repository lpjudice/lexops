"""Playwright browser manager for gov.br authentication.

Runs headless — no display needed. The user interacts via the screenshot viewer
served at /viewer/{token}. Token capture happens via network response interception.
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
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

import session as session_store

logger = logging.getLogger(__name__)

# SSO token endpoint pattern — same as the lexops jusbr_session.py reference
_SSO_TOKEN_PATTERN = "openid-connect/token"


def _sign(secret: str, subject: str, ttl: int) -> tuple[str, int]:
    exp = int(time.time()) + ttl
    msg = f"{subject}:{exp}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    payload = base64.urlsafe_b64encode(f"{subject}:{exp}:{sig}".encode()).decode().rstrip("=")
    return payload, exp


def verify_token(secret: str, token: str) -> bool:
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
    def __init__(self, profile_dir: Path, portal_url: str, auth_secret: str, link_ttl: int) -> None:
        self._profile_dir = profile_dir
        self._portal_url = portal_url
        self._auth_secret = auth_secret
        self._link_ttl = link_ttl

        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()

        self.auth_event = asyncio.Event()
        self.captured_session: Optional[dict] = None

    async def start(self) -> None:
        async with self._lock:
            if self._context:
                return
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._profile_dir),
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
                viewport={"width": 1440, "height": 900},
            )
            self._context.on("response", self._on_response)
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            logger.info("Playwright context ready (profile: %s)", self._profile_dir)

    async def stop(self) -> None:
        async with self._lock:
            if self._context:
                await self._context.close()
            if self._playwright:
                await self._playwright.stop()
            self._context = None
            self._page = None
            self._playwright = None

    async def _page_ref(self) -> Page:
        await self.start()
        assert self._page is not None
        return self._page

    async def navigate_to_portal(self) -> None:
        page = await self._page_ref()
        await page.goto(self._portal_url, wait_until="domcontentloaded", timeout=30_000)
        logger.info("Navigated to portal: %s", self._portal_url)

    async def screenshot_png(self) -> bytes:
        page = await self._page_ref()
        return await page.screenshot(type="png", full_page=False)

    async def click(self, x: int, y: int) -> None:
        page = await self._page_ref()
        await page.mouse.click(x, y)

    async def type_text(self, text: str) -> None:
        page = await self._page_ref()
        await page.keyboard.type(text, delay=40)

    async def press_key(self, key: str) -> None:
        page = await self._page_ref()
        await page.keyboard.press(key)

    async def reset_session(self) -> None:
        page = await self._page_ref()
        await self._context.clear_cookies()
        try:
            await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        except Exception:
            pass
        await page.goto("about:blank")
        self.captured_session = None
        self.auth_event.clear()
        logger.info("Browser session cleared.")

    def create_viewer_token(self) -> tuple[str, int]:
        return _sign(self._auth_secret, "viewer", self._link_ttl)

    def verify_viewer_token(self, token: str) -> bool:
        return verify_token(self._auth_secret, token)

    def reset_auth_event(self) -> None:
        self.captured_session = None
        self.auth_event.clear()

    async def wait_for_auth(self, timeout_seconds: int = 600) -> dict:
        try:
            await asyncio.wait_for(self.auth_event.wait(), timeout=float(timeout_seconds))
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Timeout aguardando autenticação gov.br.") from exc
        assert self.captured_session is not None
        return self.captured_session

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

        token = str(data["access_token"])
        refresh_token = data.get("refresh_token")
        now_iso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

        from session import _jwt_exp

        exp_dt = _jwt_exp(token)
        ref_dt = _jwt_exp(refresh_token) if refresh_token else None

        # Derive token_endpoint from issuer claim
        try:
            parts = token.split(".")
            payload_raw = parts[1] + "=" * (-len(parts[1]) % 4)
            jwt_data = json.loads(base64.urlsafe_b64decode(payload_raw).decode())
            issuer = jwt_data.get("iss", "").rstrip("/")
            token_endpoint = f"{issuer}/protocol/openid-connect/token" if "/auth/realms/" in issuer else None
        except Exception:
            token_endpoint = None

        sess = {
            "token": token,
            "refresh_token": str(refresh_token) if refresh_token else None,
            "token_type": str(data.get("token_type", "Bearer")),
            "token_endpoint": token_endpoint,
            "expires_at": exp_dt.isoformat() if exp_dt else None,
            "refresh_expires_at": ref_dt.isoformat() if ref_dt else None,
            "captured_at": now_iso,
            "api_bases": ["https://portaldeservicos.pdpj.jus.br/api/v2"],
            "detected_url": "https://portaldeservicos.pdpj.jus.br/api/v2/processos",
            "referer": "https://portaldeservicos.pdpj.jus.br/home",
            "cookies": None,
            "extra_headers": {},
            "capture_kind": "playwright_intercept",
        }
        session_store.save_session(sess)
        self.captured_session = sess
        self.auth_event.set()
        logger.info("access_token interceptado e sessão salva (exp=%s).", sess.get("expires_at"))
