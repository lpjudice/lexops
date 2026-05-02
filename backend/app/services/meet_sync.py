"""
Scans Google Drive for new Meet transcriptions/notes saved by Gemini.
Gemini saves to 'Meet Recordings' folder in the master account's personal Drive.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.services.google_master_tokens import load_master_google_tokens, save_master_google_tokens

DRIVE_META = "https://www.googleapis.com/drive/v3"
logger = logging.getLogger(__name__)

# Nomes possíveis da pasta onde o Gemini salva transcrições/notas
MEET_FOLDERS = ["Meet Recordings", "Gravações do Meet"]

# Tipos MIME de transcrição/notas salvas pelo Gemini
TRANSCRIPT_MIME_TYPES = {
    "application/vnd.google-apps.document",  # Google Doc (notas Gemini)
    "text/plain",
    "text/vtt",
}


def _load_tokens() -> dict | None:
    return load_master_google_tokens()


def _refresh(tokens: dict) -> dict:
    return _refresh_tokens(tokens, save=True)


def _auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _find_meet_folder_id(h: dict) -> str | None:
    """Localiza a pasta 'Meet Recordings' (ou equivalente) no Drive pessoal."""
    for folder_name in MEET_FOLDERS:
        r = httpx.get(
            f"{DRIVE_META}/files",
            headers=h,
            params={
                "q": f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                "fields": "files(id,name)",
                "pageSize": 5,
            },
            timeout=15,
        )
        if r.is_success and r.json().get("files"):
            return r.json()["files"][0]["id"]
    return None


def _list_files_in_folder(folder_id: str, h: dict, created_after: str | None = None) -> list[dict]:
    """Lista arquivos na pasta de gravações do Meet."""
    q = f"'{folder_id}' in parents and trashed=false"
    if created_after:
        q += f" and createdTime > '{created_after}'"

    r = httpx.get(
        f"{DRIVE_META}/files",
        headers=h,
        params={
            "q": q,
            "fields": "files(id,name,mimeType,createdTime,webViewLink,size)",
            "orderBy": "createdTime desc",
            "pageSize": 50,
        },
        timeout=15,
    )
    if not r.is_success:
        return []
    return r.json().get("files", [])


def _export_google_doc(file_id: str, h: dict) -> str | None:
    """Exporta Google Doc como texto plain."""
    r = httpx.get(
        f"{DRIVE_META}/files/{file_id}/export",
        headers=h,
        params={"mimeType": "text/plain"},
        timeout=30,
    )
    if r.is_success:
        return r.text
    return None


def _download_file(file_id: str, h: dict) -> str | None:
    """Baixa arquivo de texto simples do Drive."""
    r = httpx.get(
        f"{DRIVE_META}/files/{file_id}",
        headers=h,
        params={"alt": "media"},
        timeout=30,
    )
    if r.is_success:
        return r.text
    return None


def _refresh_tokens(tokens: dict, save: bool = False) -> dict:
    """Refresh using any token dict (not just master account)."""
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": tokens.get("refresh_token", ""),
            "client_id": __import__("os").getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": __import__("os").getenv("GOOGLE_CLIENT_SECRET", ""),
            "grant_type": "refresh_token",
        },
    )
    if resp.is_success:
        new = {**tokens, **resp.json()}
        if save:
            save_master_google_tokens(new)
        return new
    return tokens


def baixar_conteudo_arquivo(file_id: str, mime_type: str, tokens: dict | None = None) -> str | None:
    """Baixa o conteúdo de um arquivo do Drive. tokens: usa master se None."""
    if tokens is None:
        tokens = _load_tokens()
    if not tokens:
        return None

    h = _auth_headers(tokens)
    try:
        if mime_type == "application/vnd.google-apps.document":
            content = _export_google_doc(file_id, h)
        else:
            content = _download_file(file_id, h)

        if content is None:
            tokens = _refresh_tokens(tokens)
            h = _auth_headers(tokens)
            if mime_type == "application/vnd.google-apps.document":
                content = _export_google_doc(file_id, h)
            else:
                content = _download_file(file_id, h)

        return content
    except Exception as exc:
        logger.warning("Erro ao baixar arquivo do Drive %s: %s", file_id, exc)
        return None


def listar_novas_transcricoes(ultimo_sync: str | None = None, tokens: dict | None = None) -> list[dict]:
    """
    Lista arquivos novos na pasta Meet Recordings do Drive.
    tokens: usa master se None. Permite varredura por conta de usuário específico.
    """
    if tokens is None:
        tokens = _load_tokens()
    if not tokens:
        logger.warning("meet_sync: tokens do Google não encontrados")
        return []

    h = _auth_headers(tokens)
    try:
        folder_id = _find_meet_folder_id(h)
        if not folder_id:
            tokens = _refresh_tokens(tokens)
            h = _auth_headers(tokens)
            folder_id = _find_meet_folder_id(h)

        if not folder_id:
            logger.info("meet_sync: pasta 'Meet Recordings' não encontrada")
            return []

        arquivos = _list_files_in_folder(folder_id, h, created_after=ultimo_sync)
        resultado = []
        for arq in arquivos:
            if arq.get("mimeType") not in TRANSCRIPT_MIME_TYPES:
                continue
            resultado.append({
                "file_id": arq["id"],
                "nome": arq["name"],
                "mime_type": arq["mimeType"],
                "criado_em": arq.get("createdTime"),
                "drive_link": arq.get("webViewLink", f"https://drive.google.com/file/d/{arq['id']}/view"),
            })
        return resultado

    except Exception as exc:
        logger.warning("meet_sync: erro ao listar transcrições: %s", exc)
        return []


def _get_file_id_from_link(link: str) -> str | None:
    """Extrai file_id de um webViewLink do Drive."""
    import re
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
    return m.group(1) if m else None


def salvar_tldr_drive(
    conteudo: str,
    nome_arquivo: str,
    nome_cliente: str,
) -> str | None:
    """Salva o TLDR da reunião na pasta {cliente}/Reunioes/ do Drive compartilhado."""
    from app.services.google_drive import upload_arquivo

    return upload_arquivo(
        conteudo=conteudo.encode("utf-8"),
        nome_arquivo=nome_arquivo,
        nome_cliente=nome_cliente,
        subfolder="Reunioes",
        mimetype="text/plain",
    )


def _parse_data_reuniao(nome_arquivo: str, criado_em: str | None) -> datetime | None:
    """Tenta extrair a data da reunião do nome do arquivo ou da data de criação."""
    import re

    # Tenta extrair data do nome: "2026-05-02" ou "2026_05_02" ou "02/05/2026"
    patterns = [
        r"(\d{4})[-_](\d{2})[-_](\d{2})",
        r"(\d{2})[/.](\d{2})[/.](\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, nome_arquivo)
        if m:
            g = m.groups()
            try:
                if len(g[0]) == 4:  # YYYY-MM-DD
                    return datetime(int(g[0]), int(g[1]), int(g[2]), tzinfo=timezone.utc)
                else:  # DD/MM/YYYY
                    return datetime(int(g[2]), int(g[1]), int(g[0]), tzinfo=timezone.utc)
            except ValueError:
                pass

    # Fallback: usa data de criação do arquivo
    if criado_em:
        try:
            return datetime.fromisoformat(criado_em.replace("Z", "+00:00"))
        except Exception:
            pass

    return None


def extrair_titulo(nome_arquivo: str) -> str:
    """Extrai um título legível do nome do arquivo de transcrição."""
    import re

    # Remove extensão
    titulo = re.sub(r"\.(txt|vtt|docx?)$", "", nome_arquivo, flags=re.IGNORECASE)
    # Remove prefixos comuns do Gemini
    titulo = re.sub(r"^(Transcrição|Transcript|Gravação|Recording|Notas|Notes)\s*[-_]\s*", "", titulo, flags=re.IGNORECASE)
    return titulo.strip() or nome_arquivo
