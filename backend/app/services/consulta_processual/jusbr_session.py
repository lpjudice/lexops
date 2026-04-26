from __future__ import annotations

import json
import shlex
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


SESSION_FILE = Path("/app/backend/uploads/jusbr_session.json")


def _ensure_parent() -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)


def _token_from_text(raw: str) -> str:
    import re

    patterns = [
        r"authorization:\s*bearer\s+([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+)",
        r"Bearer\s+([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    text = raw.strip().removeprefix("Bearer ").strip()
    if text.count(".") == 2:
        return text
    return ""


def _jwt_exp_iso(token: str) -> str | None:
    import base64

    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        exp = data.get("exp")
        if isinstance(exp, (int, float)):
            return datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
    except Exception:
        return None
    return None


def _derive_api_bases(url: str | None) -> list[str]:
    if not url:
        return []

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return []

    root = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or ""
    candidates: list[str] = []

    for marker in ("/api/v2", "/api/v1", "/api"):
        idx = path.find(marker)
        if idx >= 0:
            base = root + path[: idx + len(marker)]
            if base not in candidates:
                candidates.append(base)

    if "portaldeservicos.pdpj.jus.br" in parsed.netloc and f"{root}/api/v2" not in candidates:
        candidates.append(f"{root}/api/v2")

    return candidates


def _parse_capture(raw_capture: str) -> dict:
    normalized = raw_capture.replace("\\\r\n", " ").replace("\\\n", " ").strip()
    parts = shlex.split(normalized)

    detected_url = ""
    headers: dict[str, str] = {}
    cookie = ""

    i = 0
    while i < len(parts):
        part = parts[i]
        lower = part.lower()

        if part.startswith("http://") or part.startswith("https://"):
            detected_url = part
        elif lower == "--url" and i + 1 < len(parts):
            detected_url = parts[i + 1]
            i += 1
        elif lower in {"-h", "--header"} and i + 1 < len(parts):
            header = parts[i + 1]
            if ":" in header:
                name, value = header.split(":", 1)
                headers[name.strip().lower()] = value.strip()
            i += 1
        elif lower in {"-b", "--cookie"} and i + 1 < len(parts):
            cookie = parts[i + 1].strip()
            i += 1
        i += 1

    token = headers.get("authorization", "")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        token = _token_from_text(raw_capture)
    if not token:
        raise ValueError("Nao foi possivel extrair um Bearer token valido da captura do jus.br.")

    if not cookie and "cookie" in headers:
        cookie = headers["cookie"]

    extra_headers = {
        key: value
        for key, value in headers.items()
        if key not in {"authorization", "cookie", "content-length", "host"}
    }

    return {
        "token": token,
        "cookies": cookie or None,
        "referer": headers.get("referer") or "https://portaldeservicos.pdpj.jus.br/home",
        "detected_url": detected_url or None,
        "api_bases": _derive_api_bases(detected_url),
        "extra_headers": extra_headers,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": _jwt_exp_iso(token),
    }


def save_session_from_capture(raw_capture: str) -> dict:
    data = _parse_capture(raw_capture)
    _ensure_parent()
    SESSION_FILE.write_text(json.dumps(data, ensure_ascii=False))
    return data


def load_session() -> dict | None:
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text())
        if not isinstance(data, dict) or not data.get("token"):
            return None
        expires_at = data.get("expires_at")
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc):
                    return None
            except Exception:
                pass
        return data
    except Exception:
        return None


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def session_status() -> dict:
    data = load_session()
    if not data:
        return {"active": False, "expires_at": None, "detected_url": None}
    expires_at = data.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc):
                return {"active": False, "expires_at": expires_at, "detected_url": data.get("detected_url")}
        except Exception:
            pass
    return {
        "active": True,
        "expires_at": expires_at,
        "detected_url": data.get("detected_url"),
    }
