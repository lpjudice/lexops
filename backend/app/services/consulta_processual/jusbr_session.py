from __future__ import annotations

import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import httpx


SESSION_FILE = Path("/app/backend/uploads/jusbr_session.json")


def _ensure_parent() -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)


def _token_from_text(raw: str) -> str:
    patterns = [
        r"authorization:\s*bearer\s+([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+)",
        r'"access_token"\s*:\s*"([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+)"',
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


def _jwt_exp_iso(token: str | None) -> str | None:
    import base64

    if not token:
        return None
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


def _jwt_issuer(token: str | None) -> str | None:
    import base64

    if not token:
        return None
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        issuer = data.get("iss")
        return str(issuer) if issuer else None
    except Exception:
        return None


def _json_from_capture(raw_capture: str) -> dict | None:
    text = raw_capture.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _token_endpoint_from_issuer(issuer: str | None) -> str | None:
    if not issuer:
        return None
    issuer = issuer.rstrip("/")
    if "/auth/realms/" in issuer:
        return f"{issuer}/protocol/openid-connect/token"
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


def _iso_from_offset(seconds: int | float | None, now: datetime) -> str | None:
    if not isinstance(seconds, (int, float)):
        return None
    return datetime.fromtimestamp(now.timestamp() + float(seconds), tz=timezone.utc).isoformat()


def _captured_form_data(parts: list[str]) -> str:
    for i, part in enumerate(parts):
        lower = part.lower()
        if lower in {"--data", "--data-raw", "--data-binary", "-d"} and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _exchange_sso_code_for_tokens(
    detected_url: str,
    headers: dict[str, str],
    body: str,
    cookie: str | None,
) -> dict:
    if not detected_url or "/protocol/openid-connect/token" not in detected_url:
        raise ValueError("Nao foi possivel localizar o endpoint de token do jus.br no cURL informado.")
    if not body:
        raise ValueError("Nao foi possivel localizar o corpo da requisicao no cURL informado.")

    form = dict(parse_qsl(body, keep_blank_values=True))
    if form.get("grant_type") != "authorization_code" or not form.get("code"):
        raise ValueError("O cURL colado nao contem um authorization_code valido do login do jus.br.")

    req_headers = {
        "Content-Type": headers.get("content-type") or "application/x-www-form-urlencoded",
        "Origin": headers.get("origin") or "https://portaldeservicos.pdpj.jus.br",
        "Referer": headers.get("referer") or "https://portaldeservicos.pdpj.jus.br/",
        "Accept": headers.get("accept") or "*/*",
    }
    if cookie:
        req_headers["Cookie"] = cookie

    response = httpx.post(
        detected_url,
        data=form,
        headers=req_headers,
        timeout=20,
    )
    if response.status_code != 200:
        raise ValueError(
            "Esse cURL e da etapa de login do jus.br, e o codigo dessa etapa e descartavel. "
            "Depois de entrar no portal, copie o cURL ou os headers de uma requisicao autenticada "
            "com URL portaldeservicos.pdpj.jus.br/api/..., nao da requisicao "
            "/protocol/openid-connect/token."
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise ValueError("O endpoint de token do jus.br respondeu em formato inesperado.") from exc

    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise ValueError("O cURL colado nao retornou um access_token valido do jus.br.")
    return payload


def _parse_capture(raw_capture: str) -> dict:
    json_payload = _json_from_capture(raw_capture)
    if json_payload and json_payload.get("access_token"):
        token = str(json_payload.get("access_token") or "").strip()
        if not token:
            raise ValueError("Nao foi possivel extrair access_token valido do JSON do jus.br.")

        refresh_token = str(json_payload.get("refresh_token") or "").strip() or None
        now = datetime.now(timezone.utc)
        issuer = _jwt_issuer(token)
        return {
            "token": token,
            "refresh_token": refresh_token,
            "token_type": str(json_payload.get("token_type") or "Bearer").strip() or "Bearer",
            "cookies": None,
            "referer": "https://portaldeservicos.pdpj.jus.br/home",
            "detected_url": "https://portaldeservicos.pdpj.jus.br/api/v2/processos",
            "api_bases": ["https://portaldeservicos.pdpj.jus.br/api/v2"],
            "extra_headers": {},
            "token_endpoint": _token_endpoint_from_issuer(issuer),
            "captured_at": now.isoformat(),
            "expires_at": _jwt_exp_iso(token) or _iso_from_offset(json_payload.get("expires_in"), now),
            "refresh_expires_at": _jwt_exp_iso(refresh_token) or _iso_from_offset(json_payload.get("refresh_expires_in"), now),
            "capture_kind": "token_json",
        }

    normalized = raw_capture.replace("\\r\\n", " ").replace("\\n", " ").strip()
    parts = shlex.split(normalized)

    detected_url = ""
    headers: dict[str, str] = {}
    cookie = ""
    body = ""

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

    body = _captured_form_data(parts)

    token = headers.get("authorization", "")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        token = _token_from_text(raw_capture)

    if not cookie and "cookie" in headers:
        cookie = headers["cookie"]

    extra_headers = {
        key: value
        for key, value in headers.items()
        if key not in {"authorization", "cookie", "content-length", "host"}
    }

    if not token and detected_url and "/protocol/openid-connect/token" in detected_url:
        raise ValueError(
            "Esse cURL e da etapa de login do jus.br, e nao serve para salvar a sessao de documentos. "
            "Entre no portal, abra a aba Network/Rede e copie o cURL ou os headers de uma requisicao "
            "autenticada cuja URL comece com portaldeservicos.pdpj.jus.br/api/...."
        )

    if not token:
        raise ValueError("Nao foi possivel extrair um token valido da captura do jus.br.")

    return {
        "token": token,
        "refresh_token": None,
        "token_type": "Bearer",
        "cookies": cookie or None,
        "referer": headers.get("referer") or "https://portaldeservicos.pdpj.jus.br/home",
        "detected_url": detected_url or None,
        "api_bases": _derive_api_bases(detected_url),
        "extra_headers": extra_headers,
        "token_endpoint": None,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": _jwt_exp_iso(token),
        "refresh_expires_at": None,
        "capture_kind": "curl_or_headers",
    }


def save_session_from_capture(raw_capture: str) -> dict:
    data = _parse_capture(raw_capture)
    _ensure_parent()
    SESSION_FILE.write_text(json.dumps(data, ensure_ascii=False))
    return data


def _is_expired(iso_value: str | None) -> bool:
    if not iso_value:
        return False
    try:
        return datetime.fromisoformat(iso_value) <= datetime.now(timezone.utc)
    except Exception:
        return False


def _refresh_session(data: dict) -> dict | None:
    refresh_token = data.get("refresh_token")
    token_endpoint = data.get("token_endpoint")
    if not refresh_token or not token_endpoint or _is_expired(data.get("refresh_expires_at")):
        return None

    try:
        response = httpx.post(
            token_endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": "portalexterno-frontend",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except Exception:
        return None

    if response.status_code != 200:
        return None

    try:
        refreshed = response.json()
    except Exception:
        return None

    if not isinstance(refreshed, dict) or not refreshed.get("access_token"):
        return None

    now = datetime.now(timezone.utc)
    merged = dict(data)
    merged["token"] = str(refreshed.get("access_token"))
    merged["refresh_token"] = str(refreshed.get("refresh_token") or refresh_token)
    merged["token_type"] = str(refreshed.get("token_type") or data.get("token_type") or "Bearer")
    merged["expires_at"] = _jwt_exp_iso(merged["token"]) or _iso_from_offset(refreshed.get("expires_in"), now)
    merged["refresh_expires_at"] = _jwt_exp_iso(merged["refresh_token"]) or _iso_from_offset(refreshed.get("refresh_expires_in"), now)
    merged["captured_at"] = now.isoformat()
    _ensure_parent()
    SESSION_FILE.write_text(json.dumps(merged, ensure_ascii=False))
    return merged


def refresh_session_if_needed(buffer_minutes: int = 60) -> dict | None:
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text())
        if not isinstance(data, dict) or not data.get("token"):
            return None
        expires_at = data.get("expires_at")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                now = datetime.now(timezone.utc)
                if exp_dt <= now:
                    return _refresh_session(data) or None
                if (exp_dt - now).total_seconds() <= buffer_minutes * 60:
                    refreshed = _refresh_session(data)
                    if refreshed:
                        return refreshed
            except Exception:
                pass
        return data
    except Exception:
        return None


def load_session() -> dict | None:
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text())
        if not isinstance(data, dict) or not data.get("token"):
            return None
        if _is_expired(data.get("expires_at")):
            refreshed = _refresh_session(data)
            if refreshed:
                return refreshed
            return None
        return data
    except Exception:
        return None


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def session_status() -> dict:
    data = load_session()
    if not data:
        return {
            "active": False,
            "expires_at": None,
            "detected_url": None,
            "capture_kind": None,
            "has_refresh_token": False,
            "has_cookies": False,
        }
    return {
        "active": True,
        "expires_at": data.get("expires_at"),
        "detected_url": data.get("detected_url"),
        "capture_kind": data.get("capture_kind"),
        "has_refresh_token": bool(data.get("refresh_token")),
        "has_cookies": bool(data.get("cookies")),
    }
