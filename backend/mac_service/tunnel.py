"""Cloudflare quick-tunnel manager.

Starts `cloudflared tunnel --url <local>` and exposes the public URL.
Uses an asyncio.Event so callers can await the URL instead of polling.
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Homebrew puts cloudflared here; not in launchd PATH by default.
_CLOUDFLARED_CANDIDATES = [
    "/opt/homebrew/bin/cloudflared",
    "/usr/local/bin/cloudflared",
    "cloudflared",  # fallback if it's in PATH
]

_proc: Optional[subprocess.Popen] = None
_url: str = ""
_ready = asyncio.Event()


def _find_cloudflared() -> str:
    import shutil
    for candidate in _CLOUDFLARED_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    return _CLOUDFLARED_CANDIDATES[-1]  # let it fail with a clear error


async def start(local_port: int) -> str:
    """Start the tunnel (idempotent) and return the public URL."""
    global _proc, _url

    if _url:
        return _url

    binary = _find_cloudflared()
    logger.info("Iniciando cloudflared (%s) → localhost:%d", binary, local_port)

    loop = asyncio.get_event_loop()
    try:
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.Popen(
                [binary, "tunnel", "--url", f"http://localhost:{local_port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            ),
        )
    except FileNotFoundError:
        logger.error("cloudflared não encontrado. Instale com: brew install cloudflared")
        return ""

    _proc = proc

    url = ""
    for _ in range(120):  # read up to 120 lines (≈ 60 s of output)
        if proc.stdout is None:
            break
        line = await loop.run_in_executor(None, proc.stdout.readline)
        if not line:
            break
        logger.debug("cloudflared: %s", line.rstrip())
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            url = m.group(0)
            break

    if url:
        _url = url
        _ready.set()
        logger.info("Cloudflare Tunnel ativo: %s", url)
    else:
        logger.warning("cloudflared não retornou URL. Verifique os logs.")

    return url


async def get_url(timeout: float = 45.0) -> str:
    """Return the tunnel URL, waiting up to `timeout` seconds for it to be ready."""
    if _url:
        return _url
    try:
        await asyncio.wait_for(_ready.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return _url


def stop() -> None:
    global _proc, _url
    if _proc:
        _proc.terminate()
        _proc = None
    _url = ""
    _ready.clear()
