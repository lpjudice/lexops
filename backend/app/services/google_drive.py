"""
Google Drive integration — uploads files to a shared folder.

Target folder: https://drive.google.com/drive/u/1/folders/0AFWG-csptyxuUk9PVA
Folder ID: 0AFWG-csptyxuUk9PVA  (Shared Drive owned by pj@pimentajudice.com.br)

The authenticated user needs "Contributor" access (or higher) to this folder.
When a new LexOps user authenticates, you must share the folder with their Google account.

Scopes required: https://www.googleapis.com/auth/drive.file
"""
import json
import logging
import os

import httpx
from app.services.google_master_tokens import load_master_google_tokens, save_master_google_tokens

DRIVE_API = "https://www.googleapis.com/upload/drive/v3"
DRIVE_META = "https://www.googleapis.com/drive/v3"
logger = logging.getLogger(__name__)

# The shared folder that holds all LexOps uploads
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "0AFWG-csptyxuUk9PVA")


def _load_tokens() -> dict | None:
    return load_master_google_tokens()


def _refresh(tokens: dict) -> dict:
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": tokens.get("refresh_token", ""),
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "grant_type": "refresh_token",
        },
    )
    if resp.is_success:
        new = {**tokens, **resp.json()}
        save_master_google_tokens(new)
        return new
    return tokens


def _auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _escape_drive_query(s: str) -> str:
    """Escapes single quotes in Drive API query strings."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _get_or_create_subfolder(name: str, parent_id: str, headers: dict) -> str:
    """
    Returns the Drive ID of a subfolder named `name` inside `parent_id`.
    Creates it if it doesn't exist. Returns the first match if multiple exist
    (avoids creating duplicates in concurrent calls).
    """
    query = (
        f"name='{_escape_drive_query(name)}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents and trashed=false"
    )
    r = httpx.get(
        f"{DRIVE_META}/files",
        headers=headers,
        params={
            "q": query,
            "fields": "files(id,name)",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        },
    )
    if r.is_success:
        files = r.json().get("files", [])
        if files:
            return files[0]["id"]  # usa o primeiro; ignora duplicatas pré-existentes

    # Create it
    r = httpx.post(
        f"{DRIVE_META}/files",
        headers={**headers, "Content-Type": "application/json"},
        params={"supportsAllDrives": True},
        content=json.dumps({
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }),
    )
    r.raise_for_status()
    return r.json()["id"]


def _is_unauthorized(exc: Exception) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response is not None
        and exc.response.status_code == 401
    )


def upload_arquivo(
    conteudo: bytes,
    nome_arquivo: str,
    nome_cliente: str,
    subfolder: str,
    mimetype: str = "application/pdf",
    sub_subfolder: str | None = None,
    converter_html_para_google_docs: bool = False,
) -> str | None:
    """
    Generic file upload to Drive under:
      LexOps root/{nome_cliente}/{subfolder}/{nome_arquivo}
    or, when sub_subfolder is set:
      LexOps root/{nome_cliente}/{subfolder}/{sub_subfolder}/{nome_arquivo}
    Returns shareable link or None if not authenticated.
    """
    tokens = _load_tokens()
    if not tokens:
        return None

    nome_lower = (nome_arquivo or "").lower()
    if not mimetype and nome_lower.endswith((".html", ".htm")):
        mimetype = "text/html"
    elif not mimetype and nome_lower.endswith(".pdf"):
        mimetype = "application/pdf"

    media_mimetype = mimetype or "application/octet-stream"
    target_mimetype = media_mimetype
    content_preview = conteudo[:512].lstrip().lower()
    looks_like_html = content_preview.startswith((b"<!doctype", b"<html")) or b"<body" in content_preview
    is_html = (
        media_mimetype.lower() in {"text/html", "application/xhtml+xml"}
        or nome_lower.endswith((".html", ".htm"))
        or (converter_html_para_google_docs and media_mimetype.lower() == "text/plain" and looks_like_html)
    )
    if converter_html_para_google_docs and is_html:
        media_mimetype = "text/html"
        target_mimetype = "application/vnd.google-apps.document"

    def _do(tkns: dict) -> str | None:
        h = _auth_headers(tkns)
        cliente_folder_id = _get_or_create_subfolder(nome_cliente, DRIVE_FOLDER_ID, h)
        tipo_folder_id = _get_or_create_subfolder(subfolder, cliente_folder_id, h)
        parent_id = tipo_folder_id
        if sub_subfolder:
            parent_id = _get_or_create_subfolder(sub_subfolder, tipo_folder_id, h)

        metadata = json.dumps({
            "name": nome_arquivo,
            "parents": [parent_id],
            "mimeType": target_mimetype,
        }).encode()

        boundary = "boundary_lexops_upload"
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        ).encode() + metadata + (
            f"\r\n--{boundary}\r\nContent-Type: {media_mimetype}\r\n\r\n"
        ).encode() + conteudo + f"\r\n--{boundary}--".encode()

        r = httpx.post(
            f"{DRIVE_API}/files",
            headers={**h, "Content-Type": f"multipart/related; boundary={boundary}"},
            params={"uploadType": "multipart", "supportsAllDrives": True, "fields": "id,webViewLink"},
            content=body,
            timeout=60,
        )
        if r.status_code == 401:
            return None
        r.raise_for_status()
        fid = r.json().get("id")
        return r.json().get("webViewLink", f"https://drive.google.com/file/d/{fid}/view")

    try:
        link = _do(tokens)
    except Exception as exc:
        if not _is_unauthorized(exc):
            logger.warning("Falha ao enviar arquivo ao Drive: %s", exc)
            return None
        tokens = _refresh(tokens)
        try:
            return _do(tokens)
        except Exception as exc2:
            logger.warning("Falha ao enviar arquivo ao Drive apos refresh: %s", exc2)
            return None

    if link is not None:
        return link
    tokens = _refresh(tokens)
    try:
        return _do(tokens)
    except Exception as exc:
        logger.warning("Falha ao enviar arquivo ao Drive apos refresh: %s", exc)
        return None


def ensure_cliente_folder(nome_cliente: str) -> str | None:
    """Creates or reuses the root Drive folder for a client."""
    tokens = _load_tokens()
    if not tokens:
        return None

    def _do(tkns: dict) -> str:
        h = _auth_headers(tkns)
        folder_id = _get_or_create_subfolder(nome_cliente, DRIVE_FOLDER_ID, h)
        return f"https://drive.google.com/drive/folders/{folder_id}"

    try:
        return _do(tokens)
    except Exception as exc:
        logger.warning("Falha ao garantir pasta do cliente no Drive: %s", exc)
        tokens2 = _refresh(tokens)
        try:
            return _do(tokens2)
        except Exception as exc2:
            logger.warning("Falha ao garantir pasta do cliente no Drive apos refresh: %s", exc2)
            return None


def upload_pdf(
    pdf_bytes: bytes,
    nome_arquivo: str,
    nome_cliente: str,
    subfolder: str = "Reembolsos",
    sub_subfolder: str | None = None,
) -> str | None:
    """Convenience wrapper for PDF uploads."""
    return upload_arquivo(pdf_bytes, nome_arquivo, nome_cliente, subfolder, "application/pdf", sub_subfolder)


def listar_arquivos(nome_cliente: str, subfolder: str, sub_subfolder: str | None = None) -> list[dict]:
    """Lists files from {nome_cliente}/{subfolder}[/{sub_subfolder}] in Drive."""
    tokens = _load_tokens()
    if not tokens:
        return []

    def _do(tkns: dict) -> list[dict]:
        h = _auth_headers(tkns)
        cliente_folder_id = _get_or_create_subfolder(nome_cliente, DRIVE_FOLDER_ID, h)
        folder_id = _get_or_create_subfolder(subfolder, cliente_folder_id, h)
        if sub_subfolder:
            folder_id = _get_or_create_subfolder(sub_subfolder, folder_id, h)
        query = f"'{folder_id}' in parents and trashed=false"
        r = httpx.get(
            f"{DRIVE_META}/files",
            headers=h,
            params={
                "q": query,
                "fields": "files(id,name,size,mimeType,modifiedTime,webViewLink)",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
                "orderBy": "modifiedTime desc",
            },
            timeout=30,
        )
        r.raise_for_status()
        return [
            {
                "filename": item.get("name") or "",
                "size": int(item.get("size") or 0),
                "drive_link": item.get("webViewLink") or f"https://drive.google.com/file/d/{item.get('id')}/view",
                "mime_type": item.get("mimeType"),
                "modified_time": item.get("modifiedTime"),
                "source": "drive",
            }
            for item in r.json().get("files", [])
            if item.get("name")
        ]

    try:
        return _do(tokens)
    except Exception as exc:
        if not _is_unauthorized(exc):
            logger.warning("Falha ao listar arquivos do Drive: %s", exc)
            return []
        tokens2 = _refresh(tokens)
        try:
            return _do(tokens2)
        except Exception as exc2:
            logger.warning("Falha ao listar arquivos do Drive apos refresh: %s", exc2)
            return []


def deletar_arquivo(nome_cliente: str, subfolder: str, nome_arquivo: str, sub_subfolder: str | None = None) -> bool:
    """Moves matching Drive file(s) in {nome_cliente}/{subfolder}[/{sub_subfolder}] to trash."""
    tokens = _load_tokens()
    if not tokens:
        return False

    def _do(tkns: dict) -> bool:
        h = _auth_headers(tkns)
        cliente_folder_id = _get_or_create_subfolder(nome_cliente, DRIVE_FOLDER_ID, h)
        folder_id = _get_or_create_subfolder(subfolder, cliente_folder_id, h)
        if sub_subfolder:
            folder_id = _get_or_create_subfolder(sub_subfolder, folder_id, h)
        query = (
            f"name='{_escape_drive_query(nome_arquivo)}' "
            f"and '{folder_id}' in parents and trashed=false"
        )
        r = httpx.get(
            f"{DRIVE_META}/files",
            headers=h,
            params={
                "q": query,
                "fields": "files(id,name)",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            },
            timeout=30,
        )
        r.raise_for_status()
        deleted = False
        for item in r.json().get("files", []):
            file_id = item.get("id")
            if not file_id:
                continue
            resp = httpx.patch(
                f"{DRIVE_META}/files/{file_id}",
                headers={**h, "Content-Type": "application/json"},
                params={"supportsAllDrives": True},
                content=json.dumps({"trashed": True}),
                timeout=30,
            )
            resp.raise_for_status()
            deleted = True
        return deleted

    try:
        return _do(tokens)
    except Exception as exc:
        if not _is_unauthorized(exc):
            logger.warning("Falha ao deletar arquivo do Drive: %s", exc)
            return False
        tokens2 = _refresh(tokens)
        try:
            return _do(tokens2)
        except Exception as exc2:
            logger.warning("Falha ao deletar arquivo do Drive apos refresh: %s", exc2)
            return False


def get_folder_link(nome_cliente: str, subfolder: str, sub_subfolder: str | None = None) -> str | None:
    """
    Returns the webViewLink of {nome_cliente}/{subfolder}[/{sub_subfolder}] in Drive.
    Creates folders if they don't exist. Returns None if not authenticated.
    """
    tokens = _load_tokens()
    if not tokens:
        return None

    def _do(tkns: dict) -> str:
        h = _auth_headers(tkns)
        cliente_folder_id = _get_or_create_subfolder(nome_cliente, DRIVE_FOLDER_ID, h)
        folder_id = _get_or_create_subfolder(subfolder, cliente_folder_id, h)
        if sub_subfolder:
            folder_id = _get_or_create_subfolder(sub_subfolder, folder_id, h)
        return f"https://drive.google.com/drive/folders/{folder_id}"

    try:
        return _do(tokens)
    except Exception:
        tokens2 = _refresh(tokens)
        return _do(tokens2)


def drive_disponivel() -> bool:
    return _load_tokens() is not None
