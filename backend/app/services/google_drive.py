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
import threading

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


# ── Anti-duplicação de pastas ─────────────────────────────────────────────
# A busca do Drive tem consistência eventual: logo após criar uma pasta, uma
# nova busca pode não enxergá-la ainda. Em uploads em sequência rápida (sync em
# lote) ou em paralelo (dois menus no mesmo cliente novo), isso fazia o código
# criar uma 2ª pasta com o mesmo nome. Combatemos com:
#   1. cache em memória por (pai, nome) → id  (resolve o mesmo-processo);
#   2. trava por (pai, nome) ao criar         (serializa criações concorrentes);
#   3. reconciliação pós-criação              (mantém a mais antiga e descarta
#      extras VAZIAS — nunca apaga pasta com conteúdo).
_folder_cache: dict[tuple[str, str], str] = {}
_folder_cache_guard = threading.Lock()
_folder_locks: dict[tuple[str, str], threading.Lock] = {}
_folder_locks_guard = threading.Lock()


def _cache_get(parent_id: str, name: str) -> str | None:
    with _folder_cache_guard:
        return _folder_cache.get((parent_id, name))


def _cache_set(parent_id: str, name: str, folder_id: str) -> None:
    with _folder_cache_guard:
        _folder_cache[(parent_id, name)] = folder_id


def _cache_evict(parent_id: str, name: str) -> None:
    with _folder_cache_guard:
        _folder_cache.pop((parent_id, name), None)


def _lock_for(parent_id: str, name: str) -> threading.Lock:
    key = (parent_id, name)
    with _folder_locks_guard:
        lk = _folder_locks.get(key)
        if lk is None:
            lk = threading.Lock()
            _folder_locks[key] = lk
        return lk


def _listar_pastas(name: str, parent_id: str, headers: dict) -> list[dict]:
    """Lista pastas-irmãs com este nome (ordenadas da mais antiga p/ a mais nova)."""
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
            "fields": "files(id,name,createdTime)",
            "orderBy": "createdTime",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        },
        timeout=30,
    )
    if r.is_success:
        return r.json().get("files", [])
    return []


def _pasta_vazia(folder_id: str, headers: dict) -> bool:
    """True somente se a pasta não contém nenhum item não-lixeira."""
    r = httpx.get(
        f"{DRIVE_META}/files",
        headers=headers,
        params={
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "files(id)",
            "pageSize": 1,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        },
        timeout=30,
    )
    if not r.is_success:
        return False  # em dúvida, nunca remove
    return len(r.json().get("files", [])) == 0


def _trash_folder(folder_id: str, headers: dict) -> None:
    httpx.patch(
        f"{DRIVE_META}/files/{folder_id}",
        headers={**headers, "Content-Type": "application/json"},
        params={"supportsAllDrives": True},
        content=json.dumps({"trashed": True}),
        timeout=30,
    )


def _consolidar_pastas(folders: list[dict], headers: dict) -> str:
    """Recebe pastas-irmãs de mesmo nome; mantém a MAIS ANTIGA e descarta as
    extras apenas se estiverem VAZIAS (nunca apaga pasta com conteúdo).
    Retorna o id da pasta principal."""
    ordenadas = sorted(folders, key=lambda f: f.get("createdTime") or "")
    principal = ordenadas[0]["id"]
    for extra in ordenadas[1:]:
        try:
            if _pasta_vazia(extra["id"], headers):
                _trash_folder(extra["id"], headers)
            else:
                logger.warning(
                    "Pasta duplicada NAO-vazia mantida no Drive (id=%s) — limpar manualmente",
                    extra["id"],
                )
        except Exception:
            pass
    return principal


def _get_or_create_subfolder(name: str, parent_id: str, headers: dict) -> str:
    """
    Retorna o id da subpasta `name` dentro de `parent_id`, criando se necessário.
    Idempotente e à prova de corrida (cache em memória + trava por (pai, nome) +
    reconciliação de duplicatas geradas por consistência eventual do Drive).
    """
    name = (name or "").strip()

    cached = _cache_get(parent_id, name)
    if cached:
        return cached

    existentes = _listar_pastas(name, parent_id, headers)
    if existentes:
        fid = _consolidar_pastas(existentes, headers) if len(existentes) > 1 else existentes[0]["id"]
        _cache_set(parent_id, name, fid)
        return fid

    # Serializa a criação no processo para o caso mais comum (sync em lote):
    # várias criações em sequência rápida da mesma pasta nova.
    with _lock_for(parent_id, name):
        cached = _cache_get(parent_id, name)
        if cached:
            return cached
        existentes = _listar_pastas(name, parent_id, headers)
        if existentes:
            fid = _consolidar_pastas(existentes, headers) if len(existentes) > 1 else existentes[0]["id"]
            _cache_set(parent_id, name, fid)
            return fid

        r = httpx.post(
            f"{DRIVE_META}/files",
            headers={**headers, "Content-Type": "application/json"},
            params={"supportsAllDrives": True},
            content=json.dumps({
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }),
            timeout=30,
        )
        r.raise_for_status()
        novo_id = r.json()["id"]

        # Reconciliação: se outro processo criou em paralelo e o índice já
        # reflete ambas, mantém a mais antiga e descarta extras vazias.
        todas = _listar_pastas(name, parent_id, headers)
        if len(todas) > 1:
            novo_id = _consolidar_pastas(todas, headers)
        _cache_set(parent_id, name, novo_id)
        return novo_id


def _find_subfolder(name: str, parent_id: str, headers: dict) -> str | None:
    """Returns the Drive ID of an existing subfolder, without creating it."""
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
        timeout=30,
    )
    r.raise_for_status()
    files = r.json().get("files", [])
    return files[0]["id"] if files else None


def _is_unauthorized(exc: Exception) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response is not None
        and exc.response.status_code == 401
    )


# ── Vínculo estável cliente → pasta do Drive ──────────────────────────────────
# A pasta-raiz de cada cliente era endereçada pela STRING do nome. Quando o nome
# do cliente mudava (ou variava por acento/espaço), a busca não achava a pasta
# antiga e o app criava uma nova — origem das "duplicatas". Agora gravamos o id
# da pasta em `clientes.drive_folder_id`: o upload usa o id (imune a renome) e só
# cai na busca por nome na 1ª vez, gravando o id em seguida (backfill).
def _cliente_folder_id_armazenado(nome_cliente: str) -> str | None:
    try:
        from sqlalchemy import select
        from app.database import SessionLocal
        from app.models.cliente import Cliente
        with SessionLocal() as db:
            row = db.execute(
                select(Cliente.drive_folder_id)
                .where(Cliente.nome == nome_cliente)
                .order_by(Cliente.drive_folder_id.isnot(None).desc())
                .limit(1)
            ).first()
            return row[0] if row and row[0] else None
    except Exception as exc:
        logger.warning("Falha ao ler drive_folder_id do cliente: %s", exc)
        return None


def _persistir_folder_id_cliente(nome_cliente: str, folder_id: str) -> None:
    """Grava o id da pasta no cliente apenas se ainda estiver vazio (não sobrescreve)."""
    if not folder_id:
        return
    try:
        from sqlalchemy import update
        from app.database import SessionLocal
        from app.models.cliente import Cliente
        with SessionLocal() as db:
            db.execute(
                update(Cliente)
                .where(Cliente.nome == nome_cliente, Cliente.drive_folder_id.is_(None))
                .values(drive_folder_id=folder_id)
            )
            db.commit()
    except Exception as exc:
        logger.warning("Falha ao gravar drive_folder_id do cliente: %s", exc)


def _resolver_pasta_cliente(nome_cliente: str, headers: dict) -> str:
    """Pasta-raiz do cliente (cria se faltar). Usa o id gravado quando houver;
    senão resolve por nome e faz backfill do id. Imune a renome do cliente."""
    nome = (nome_cliente or "").strip()
    cached = _cache_get(DRIVE_FOLDER_ID, nome)
    if cached:
        return cached
    stored = _cliente_folder_id_armazenado(nome)
    if stored:
        _cache_set(DRIVE_FOLDER_ID, nome, stored)
        return stored
    fid = _get_or_create_subfolder(nome, DRIVE_FOLDER_ID, headers)
    _persistir_folder_id_cliente(nome, fid)
    return fid


def _resolver_pasta_cliente_existente(nome_cliente: str, headers: dict) -> str | None:
    """Pasta-raiz do cliente SEM criar. Prefere o id gravado; senão busca por nome."""
    nome = (nome_cliente or "").strip()
    stored = _cliente_folder_id_armazenado(nome)
    if stored:
        return stored
    fid = _find_subfolder(nome, DRIVE_FOLDER_ID, headers)
    if fid:
        _persistir_folder_id_cliente(nome, fid)
    return fid


def renomear_pasta_cliente(
    novo_nome: str, folder_id: str | None = None, nome_antigo: str | None = None
) -> str | None:
    """Renomeia a pasta-raiz do cliente no Drive para `novo_nome`.
    Usa `folder_id` quando fornecido; senão localiza pela string `nome_antigo`.
    Retorna o id da pasta renomeada (para persistir no cliente) ou None."""
    tokens = _load_tokens()
    if not tokens:
        return None
    alvo = (novo_nome or "").strip()
    antigo = (nome_antigo or "").strip()

    def _do(tkns: dict) -> str | None:
        h = _auth_headers(tkns)
        fid = folder_id or (_find_subfolder(antigo, DRIVE_FOLDER_ID, h) if antigo else None)
        if not fid:
            return None
        r = httpx.patch(
            f"{DRIVE_META}/files/{fid}",
            headers={**h, "Content-Type": "application/json"},
            params={"supportsAllDrives": True},
            content=json.dumps({"name": alvo}),
            timeout=30,
        )
        r.raise_for_status()
        if antigo:
            _cache_evict(DRIVE_FOLDER_ID, antigo)
        _cache_set(DRIVE_FOLDER_ID, alvo, fid)
        return fid

    try:
        return _do(tokens)
    except Exception as exc:
        if not _is_unauthorized(exc):
            logger.warning("Falha ao renomear pasta do cliente no Drive: %s", exc)
            return None
        try:
            return _do(_refresh(tokens))
        except Exception as exc2:
            logger.warning("Falha ao renomear pasta do cliente apos refresh: %s", exc2)
            return None


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
        cliente_folder_id = _resolver_pasta_cliente(nome_cliente, h)
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
        folder_id = _resolver_pasta_cliente(nome_cliente, h)
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
        cliente_folder_id = _resolver_pasta_cliente(nome_cliente, h)
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
        cliente_folder_id = _resolver_pasta_cliente(nome_cliente, h)
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
        cliente_folder_id = _resolver_pasta_cliente(nome_cliente, h)
        folder_id = _get_or_create_subfolder(subfolder, cliente_folder_id, h)
        if sub_subfolder:
            folder_id = _get_or_create_subfolder(sub_subfolder, folder_id, h)
        return f"https://drive.google.com/drive/folders/{folder_id}"

    try:
        return _do(tokens)
    except Exception:
        tokens2 = _refresh(tokens)
        return _do(tokens2)


def find_folder_link(nome_cliente: str, subfolder: str, sub_subfolder: str | None = None) -> str | None:
    """Returns the folder link only if the folder already exists."""
    tokens = _load_tokens()
    if not tokens:
        return None

    def _do(tkns: dict) -> str | None:
        h = _auth_headers(tkns)
        cliente_folder_id = _resolver_pasta_cliente_existente(nome_cliente, h)
        if not cliente_folder_id:
            return None
        folder_id = _find_subfolder(subfolder, cliente_folder_id, h)
        if not folder_id:
            return None
        if sub_subfolder:
            folder_id = _find_subfolder(sub_subfolder, folder_id, h)
        if not folder_id:
            return None
        return f"https://drive.google.com/drive/folders/{folder_id}"

    try:
        return _do(tokens)
    except Exception:
        tokens2 = _refresh(tokens)
        try:
            return _do(tokens2)
        except Exception:
            return None


def deletar_pasta(nome_cliente: str, subfolder: str, sub_subfolder: str) -> bool:
    """Moves the matching Drive subfolder to trash, if it exists."""
    tokens = _load_tokens()
    if not tokens:
        return False

    def _do(tkns: dict) -> bool:
        h = _auth_headers(tkns)
        cliente_folder_id = _resolver_pasta_cliente_existente(nome_cliente, h)
        if not cliente_folder_id:
            return False
        folder_id = _find_subfolder(subfolder, cliente_folder_id, h)
        if not folder_id:
            return False
        target_id = _find_subfolder(sub_subfolder, folder_id, h)
        if not target_id:
            return False
        resp = httpx.patch(
            f"{DRIVE_META}/files/{target_id}",
            headers={**h, "Content-Type": "application/json"},
            params={"supportsAllDrives": True},
            content=json.dumps({"trashed": True}),
            timeout=30,
        )
        resp.raise_for_status()
        _cache_evict(folder_id, sub_subfolder)
        return True

    try:
        return _do(tokens)
    except Exception as exc:
        if not _is_unauthorized(exc):
            logger.warning("Falha ao deletar pasta do Drive: %s", exc)
            return False
        tokens2 = _refresh(tokens)
        try:
            return _do(tokens2)
        except Exception as exc2:
            logger.warning("Falha ao deletar pasta do Drive apos refresh: %s", exc2)
            return False


def drive_disponivel() -> bool:
    return _load_tokens() is not None
