"""BrowserManager for jus.br/gov.br authentication on Fly.io.

PKCE OAuth2 flow — bypasses the portal homepage (blocked by AWS WAF):
  1. Build authorization URL directly against the SSO server (not blocked)
  2. Navigate Playwright to the SSO login page
  3. User completes gov.br login in the screenshot viewer
  4. Intercept the OAuth redirect via context.route() before it hits the portal
  5. Exchange code → access_token via httpx (works fine from Fly.io)
  6. Save to JusbrSession Postgres table via existing jusbr_session.py logic

The portal homepage is never loaded by Playwright.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx
from patchright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    Route,
    Request,
    async_playwright,
)

logger = logging.getLogger(__name__)

_SSO_AUTH = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth"
_SSO_TOKEN = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
_CLIENT_ID = "portalexterno-frontend"
_REDIRECT_URI = "https://portaldeservicos.pdpj.jus.br/home"
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
        self._code_verifier: Optional[str] = None
        self._last_screenshot: Optional[bytes] = None

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
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            logger.info("Patchright context started (profile: %s)", _PROFILE_DIR)

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
        # Always prefer the most recent live page in the context. gov.br login
        # (captcha / 2FA) can open popups or replace the page; a stale ref breaks.
        if self._context:
            live = [p for p in self._context.pages if not p.is_closed()]
            if live:
                self._page = live[-1]
        assert self._page is not None
        return self._page

    async def navigate_to_sso(self) -> None:
        """Navigate Playwright to the gov.br SSO login page via PKCE."""
        page = await self._ensure_page()

        # Generate PKCE pair
        raw = secrets.token_bytes(32)
        code_verifier = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        self._code_verifier = code_verifier

        params = {
            "client_id": _CLIENT_ID,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": "openid profile",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": secrets.token_hex(16),
        }
        auth_url = f"{_SSO_AUTH}?{urllib.parse.urlencode(params)}"

        # Intercept the OAuth redirect back to the portal before it loads
        await self._context.route(
            f"{_REDIRECT_URI}*",
            self._intercept_redirect,
        )

        await page.goto(auth_url, wait_until="domcontentloaded", timeout=30_000)
        logger.info("Navigated to SSO: %s", _SSO_AUTH)

    async def _intercept_redirect(self, route: Route, request: Request) -> None:
        """Catch the OAuth redirect, exchange code for token via httpx."""
        url = request.url
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        code = params.get("code")

        if not code:
            await route.continue_()
            return

        logger.info("OAuth code interceptado — trocando por token...")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _SSO_TOKEN,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": _REDIRECT_URI,
                        "client_id": _CLIENT_ID,
                        "code_verifier": self._code_verifier or "",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=20,
                )

            if resp.status_code == 200 and resp.json().get("access_token"):
                from app.services.consulta_processual.jusbr_session import save_session_from_capture
                save_session_from_capture(resp.text)
                self.captured_token = resp.json()["access_token"]
                self.auth_event.set()
                logger.info("Token obtido via PKCE ✓")

                await route.fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=(
                        "<html><body style='font-family:sans-serif;text-align:center;"
                        "padding:60px;background:#0d0d0d;color:#e0e0e0'>"
                        "<h2>✅ Login concluído!</h2>"
                        "<p>Pode fechar esta janela. O bot está buscando os andamentos...</p>"
                        "</body></html>"
                    ),
                )
                return
            else:
                logger.warning("Token exchange falhou: %d %s", resp.status_code, resp.text[:200])
        except Exception:
            logger.exception("Erro na troca de código OAuth")

        await route.continue_()

    # ── Keep navigate_to_portal as alias for backwards compat ────────────────
    async def navigate_to_portal(self) -> None:
        await self.navigate_to_sso()

    async def screenshot_png(self) -> bytes:
        # Resilient: a transient navigation (captcha/2FA) can make a single shot
        # fail. Return the last good frame instead of erroring the viewer, so the
        # connection never appears to drop.
        try:
            page = await self._ensure_page()
            png = await page.screenshot(type="png", full_page=False, timeout=8000)
            self._last_screenshot = png
            return png
        except Exception as exc:
            logger.warning("screenshot falhou (%s); servindo último frame", str(exc)[:120])
            if self._last_screenshot:
                return self._last_screenshot
            raise

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
                await self._context.unroute(f"{_REDIRECT_URI}*")
            except Exception:
                pass
        try:
            await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        except Exception:
            pass
        await page.goto("about:blank")
        self.captured_token = None
        self.auth_event.clear()
        self._code_verifier = None

    def create_viewer_token(self) -> tuple[str, int]:
        return _sign(self._secret, "viewer", self._link_ttl)

    def verify_token(self, token: str) -> bool:
        return verify_viewer_token(self._secret, token)

    def reset_auth_event(self) -> None:
        self.captured_token = None
        self.auth_event.clear()
        self._code_verifier = None

    async def wait_for_auth(self, timeout_seconds: int = 600) -> str:
        try:
            await asyncio.wait_for(self.auth_event.wait(), timeout=float(timeout_seconds))
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Timeout aguardando autenticação gov.br.") from exc
        assert self.captured_token is not None
        return self.captured_token
