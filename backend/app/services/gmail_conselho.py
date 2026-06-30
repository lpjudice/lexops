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


def _obter_access_token(usuario: Usuario, db: Session) -> tuple[str, str] | None:
    """Retorna (access_token, email_remetente) priorizando o Google do usuário logado."""
    from app.services.google_calendar import _load_tokens as _load_master, _refresh_token as _refresh_master
    from app.services.meet_sync import _refresh_tokens

    if isinstance(usuario.google_tokens, dict) and usuario.google_tokens.get("refresh_token"):
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
        if access_token:
            return access_token, tokens.get("email") or usuario.email

    master = _load_master()
    if master:
        try:
            master = _refresh_master(master)
        except Exception:
            pass
        access_token = master.get("access_token")
        if access_token:
            return access_token, master.get("email") or "conta master"

    return None


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
    """Envia via Gmail API. Retorna o e-mail usado como remetente. Levanta Exception em falha."""
    remetente = _obter_access_token(usuario, db)
    if not remetente:
        raise RuntimeError("Nenhuma conta Google conectada (nem do usuário, nem a master)")
    access_token, email_remetente = remetente

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
    resp = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        content=json.dumps({"raw": raw}),
        timeout=20,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Gmail API retornou {resp.status_code}: {resp.text}")

    return email_remetente
