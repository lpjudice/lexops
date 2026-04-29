import json
from pathlib import Path

MASTER_TOKENS_FILE = Path("/app/backend/uploads/google_tokens.json")
LEGACY_MASTER_TOKENS_FILE = Path("/app/uploads/google_tokens.json")


def _migrate_legacy_tokens_if_needed() -> None:
    if MASTER_TOKENS_FILE.exists() or not LEGACY_MASTER_TOKENS_FILE.exists():
        return
    MASTER_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MASTER_TOKENS_FILE.write_text(LEGACY_MASTER_TOKENS_FILE.read_text())


def load_master_google_tokens() -> dict | None:
    _migrate_legacy_tokens_if_needed()
    if not MASTER_TOKENS_FILE.exists():
        return None
    return json.loads(MASTER_TOKENS_FILE.read_text())


def save_master_google_tokens(tokens: dict) -> None:
    MASTER_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MASTER_TOKENS_FILE.write_text(json.dumps(tokens))
