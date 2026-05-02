"""
Google Drive Push Notifications — registra e renova watch channels.

O Gemini salva transcrições em 'Meet Recordings' no Drive da conta master.
Quando um arquivo novo cai lá, o Drive chama POST /webhooks/drive e o app
importa automaticamente sem polling.

Channels expiram em até 7 dias — renovados via APScheduler (semanalmente).
"""
import json
import logging
import os
import uuid
from pathlib import Path

import httpx

from app.services.google_master_tokens import load_master_google_tokens, save_master_google_tokens
from app.services.meet_sync import MEET_FOLDERS, _auth_headers, _refresh

logger = logging.getLogger(__name__)

DRIVE_META = "https://www.googleapis.com/drive/v3"
CHANNEL_FILE = Path(os.getenv("UPLOADS_DIR", "/app/backend/uploads")) / "drive_watch_channel.json"
WEBHOOK_URL_ENV = "WEBHOOK_BASE_URL"  # ex: https://lexops.fly.dev


def _load_channel() -> dict | None:
    try:
        if CHANNEL_FILE.exists():
            return json.loads(CHANNEL_FILE.read_text())
    except Exception:
        pass
    return None


def _save_channel(data: dict) -> None:
    CHANNEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHANNEL_FILE.write_text(json.dumps(data, indent=2))


def _find_meet_folder(h: dict) -> str | None:
    for name in MEET_FOLDERS:
        r = httpx.get(
            f"{DRIVE_META}/files",
            headers=h,
            params={
                "q": f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                "fields": "files(id)",
                "pageSize": 3,
            },
            timeout=15,
        )
        if r.is_success and r.json().get("files"):
            return r.json()["files"][0]["id"]
    return None


def registrar_watch(base_url: str | None = None) -> dict:
    """
    Registra (ou renova) um watch channel no folder Meet Recordings.
    Retorna o channel dict salvo.
    """
    tokens = load_master_google_tokens()
    if not tokens:
        return {"erro": "tokens Google não encontrados"}

    h = _auth_headers(tokens)
    folder_id = _find_meet_folder(h)
    if not folder_id:
        tokens = _refresh(tokens)
        h = _auth_headers(tokens)
        folder_id = _find_meet_folder(h)

    if not folder_id:
        return {"erro": "pasta 'Meet Recordings' não encontrada no Drive"}

    url = base_url or os.getenv(WEBHOOK_URL_ENV, "")
    if not url:
        return {"erro": f"env {WEBHOOK_URL_ENV} não configurado (ex: https://lexops.fly.dev)"}

    webhook_url = url.rstrip("/") + "/webhooks/drive"
    channel_id = str(uuid.uuid4())

    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": webhook_url,
        "token": os.getenv("DRIVE_WEBHOOK_TOKEN", channel_id),
    }

    r = httpx.post(
        f"{DRIVE_META}/files/{folder_id}/watch",
        headers={**h, "Content-Type": "application/json"},
        params={"supportsAllDrives": True},
        content=json.dumps(body),
        timeout=20,
    )

    if r.status_code == 401:
        tokens = _refresh(tokens)
        h = _auth_headers(tokens)
        r = httpx.post(
            f"{DRIVE_META}/files/{folder_id}/watch",
            headers={**h, "Content-Type": "application/json"},
            params={"supportsAllDrives": True},
            content=json.dumps(body),
            timeout=20,
        )

    if not r.is_success:
        return {"erro": f"Drive API: {r.status_code} {r.text}"}

    data = r.json()
    channel = {
        "channel_id": data.get("id"),
        "resource_id": data.get("resourceId"),
        "expiration_ms": data.get("expiration"),
        "folder_id": folder_id,
        "webhook_url": webhook_url,
    }
    _save_channel(channel)
    logger.info("Drive watch registrado: channel=%s expira=%s", channel["channel_id"], channel["expiration_ms"])
    return channel


def parar_watch() -> bool:
    """Para o watch channel ativo."""
    channel = _load_channel()
    if not channel:
        return False

    tokens = load_master_google_tokens()
    if not tokens:
        return False

    h = _auth_headers(tokens)
    body = {
        "id": channel["channel_id"],
        "resourceId": channel["resource_id"],
    }
    r = httpx.post(
        f"{DRIVE_META}/channels/stop",
        headers={**h, "Content-Type": "application/json"},
        content=json.dumps(body),
        timeout=15,
    )
    if r.is_success or r.status_code == 204:
        CHANNEL_FILE.unlink(missing_ok=True)
        return True
    return False


def channel_ativo() -> dict | None:
    return _load_channel()


def renovar_se_necessario() -> None:
    """Chamado pelo scheduler — renova channel se expirar em menos de 1 dia."""
    import time
    channel = _load_channel()
    if not channel:
        return

    exp_ms = channel.get("expiration_ms")
    if not exp_ms:
        return

    restante_ms = int(exp_ms) - int(time.time() * 1000)
    um_dia_ms = 24 * 60 * 60 * 1000
    if restante_ms < um_dia_ms:
        logger.info("Renovando Drive watch channel (expira em %dh)", restante_ms // 3_600_000)
        base_url = channel.get("webhook_url", "").replace("/webhooks/drive", "")
        registrar_watch(base_url or None)
