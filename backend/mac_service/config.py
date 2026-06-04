from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=False)


class Settings:
    telegram_bot_token: str
    telegram_allowed_user_ids: list[int]
    auth_secret: str
    auth_link_ttl_seconds: int
    port: int
    session_file: Path
    playwright_profile_dir: Path
    portal_url: str
    viewer_base_url: str  # set at runtime after cloudflared starts

    def __init__(self) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado.")
        self.telegram_bot_token = token

        raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "5152275140")
        self.telegram_allowed_user_ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]

        self.auth_secret = os.getenv("AUTH_SECRET") or secrets.token_hex(32)
        self.auth_link_ttl_seconds = int(os.getenv("AUTH_LINK_TTL_SECONDS", "600"))
        self.port = int(os.getenv("PORT", "8765"))

        home = Path.home()
        self.session_file = Path(os.getenv("SESSION_FILE", str(home / ".lexops" / "jusbr_session.json")))
        self.playwright_profile_dir = Path(
            os.getenv("PLAYWRIGHT_PROFILE_DIR", str(home / ".lexops" / "playwright-profile"))
        )
        self.portal_url = os.getenv("PORTAL_URL", "https://portaldeservicos.pdpj.jus.br/home")
        self.viewer_base_url = ""  # filled in by cloudflared at runtime


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
