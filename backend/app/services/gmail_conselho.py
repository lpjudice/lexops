"""Envio real de e-mail (Gmail API) para o módulo Conselho/Expansão.

Usa o Gmail pessoal do usuário logado (usuario.google_tokens) quando conectado;
cai para a conta master do escritório caso contrário.
"""
import base64
import email.mime.application as mime_app
import email.mime.multipart as mime_multi
import email.mime.text as mime_text
import json

import httpx
from sqlalchemy.orm import Session

from app.models.usuario import Usuario


def _token_usuario(usuario: Usuario, db: Session) -> tuple[str, str] | None:
    from app.services.meet_sync import _refresh_tokens

    if not (isinstance(usuario.google_tokens, dict) and usuario.google_tokens.get("refresh_token")):
        return None
    tokens = usuario.google_tokens
    try:
        refreshed = _refresh_tokens(tokens, save=False)
        if refreshed.get("access_token") != tokens.get("access_token"):
            usuario.google_tokens = refreshed
            db.commit()
        tokens = refreshed
    except Exception:
        pass
    access_token = tokens.get("access_token")
    if not access_token:
        return None
    return access_token, tokens.get("email") or usuario.email


def _token_master() -> tuple[str, str] | None:
    from app.services.google_calendar import _load_tokens as _load_master, _refresh_token as _refresh_master

    master = _load_master()
    if not master:
        return None
    try:
        master = _refresh_master(master)
    except Exception:
        pass
    access_token = master.get("access_token")
    if not access_token:
        return None
    return access_token, master.get("email") or "conta master"


def _scope_insuficiente(resp: httpx.Response) -> bool:
    if resp.status_code != 403:
        return False
    try:
        return "insufficient" in resp.text.lower()
    except Exception:
        return False


def enviar_email(
    usuario: Usuario,
    db: Session,
    to: str,
    subject: str,
    html: str,
    pdf_bytes: bytes | None = None,
    pdf_filename: str | None = None,
    bcc: list[str] | None = None,
) -> str:
    """Envia via Gmail API. Tenta o Google pessoal do usuário; se faltar escopo de envio
    (conexão pessoal hoje é só leitura), cai automaticamente para a conta master.
    Retorna o e-mail usado como remetente. Levanta Exception em falha."""
    candidatos = [c for c in (_token_usuario(usuario, db), _token_master()) if c]
    if not candidatos:
        raise RuntimeError("Nenhuma conta Google conectada (nem do usuário, nem a master)")

    html_part = mime_multi.MIMEMultipart("alternative")
    html_part.attach(mime_text.MIMEText(html, "html", "utf-8"))

    if pdf_bytes:
        outer = mime_multi.MIMEMultipart("mixed")
        outer["to"] = to
        outer["from"] = "me"
        outer["subject"] = subject
        if bcc:
            outer["bcc"] = ", ".join(bcc)
        outer.attach(html_part)
        anexo = mime_app.MIMEApplication(pdf_bytes, _subtype="pdf")
        anexo.add_header("Content-Disposition", "attachment", filename=pdf_filename or "anexo.pdf")
        outer.attach(anexo)
        msg_bytes = outer.as_bytes()
    else:
        html_part["to"] = to
        html_part["from"] = "me"
        html_part["subject"] = subject
        if bcc:
            html_part["bcc"] = ", ".join(bcc)
        msg_bytes = html_part.as_bytes()

    raw = base64.urlsafe_b64encode(msg_bytes).decode()

    ultimo_erro: str | None = None
    for access_token, email_remetente in candidatos:
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            content=json.dumps({"raw": raw}),
            timeout=20,
        )
        if resp.status_code in (200, 201):
            return email_remetente
        if _scope_insuficiente(resp) and len(candidatos) > 1:
            # conexão pessoal do usuário é só leitura — tenta o próximo candidato (master)
            ultimo_erro = f"Gmail API retornou {resp.status_code}: {resp.text}"
            continue
        raise RuntimeError(f"Gmail API retornou {resp.status_code}: {resp.text}")

    raise RuntimeError(ultimo_erro or "Falha ao enviar e-mail")
