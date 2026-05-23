import base64
import json
import uuid
from datetime import date as date_type, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import httpx

from app.database import get_db
from app.dependencies import get_current_user
from app.models.reembolso import ItemReembolso, Reembolso
from app.models.usuario import Usuario
from app.schemas.reembolso import (
    ItemReembolsoCreate, ItemReembolsoOut, ItemReembolsoUpdate,
    ReembolsoCreate, ReembolsoOut, ReembolsoUpdate,
)
from app.services.gerar_nota_reembolso import gerar_pdf
from app.services.google_calendar import _load_tokens, _refresh_token

UPLOADS_DIR = Path("/app/uploads/reembolsos")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/reembolsos", tags=["reembolsos"])
BCC_EMAIL_FIXO = "pj@pimentajudice.com.br"


def _get_access_token() -> str | None:
    tokens = _load_tokens()
    if not tokens:
        return None
    return tokens.get("access_token")


def _refresh_if_needed() -> str | None:
    tokens = _load_tokens()
    if not tokens:
        return None
    try:
        refreshed = _refresh_token(tokens)
        return refreshed.get("access_token")
    except Exception:
        return tokens.get("access_token")


def _fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _usuario_email(usuario: Usuario) -> str | None:
    return getattr(usuario, "email", None) or getattr(usuario, "google_email", None)


def _bcc_com_usuario(usuario: Usuario, destinatario: str | None = None) -> list[str]:
    bcc = [BCC_EMAIL_FIXO]
    usuario_email = _usuario_email(usuario)
    if usuario_email and usuario_email not in {BCC_EMAIL_FIXO, destinatario}:
        bcc.append(usuario_email)
    return bcc


def _folder_prefix_date(r: Reembolso) -> str:
    base_date = r.created_at.date() if r.created_at else r.data_emissao
    return base_date.strftime("%Y-%m-%d")


def _sanitize_folder_segment(value: str) -> str:
    sanitized = " ".join((value or "").strip().split())
    sanitized = sanitized.replace("/", "-").replace("\\", "-").replace(":", " -")
    return sanitized[:120] or "Reembolso"


def _reembolso_folder_name(r: Reembolso) -> str:
    return f"{_folder_prefix_date(r)} - {_sanitize_folder_segment(r.titulo)} - {str(r.id)[:8]}"


def _build_email_html(
    r: Reembolso,
    header_color: str = "#00b090",
    is_cancelamento: bool = False,
    is_lembrete: bool = False,
    is_quitacao: bool = False,
    is_quitacao_erro: bool = False,
) -> str:
    """Builds the HTML email body."""
    itens_rows = "".join(
        f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#374151;">{item.data.strftime('%d/%m/%Y')}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#374151;">{item.descricao}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#374151;">{item.natureza}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#374151;text-align:right;font-weight:600;">{_fmt_brl(float(item.valor))}</td>
        </tr>"""
        for item in sorted(r.itens, key=lambda x: x.data)
    )
    vencimento_row = (
        f'<p style="margin:0 0 6px;font-size:13px;color:#6b7280;">'
        f'<strong>Vencimento:</strong> {r.data_vencimento.strftime("%d/%m/%Y")}</p>'
        if r.data_vencimento else ""
    )

    if is_cancelamento:
        headline = "Cancelamento — Nota de Reembolso de Despesas"
        box_bg = "#fef2f2"
        box_border = "#fca5a5"
        box_color = "#991b1b"
        total_color = "#dc2626"
        intro = (
            f"Informamos que a <strong>Nota de Reembolso de Despesas</strong> referente a "
            f"<strong style='color:#1d1e20;'>{r.titulo}</strong> foi <strong>cancelada</strong>. "
            f"Em caso de dúvidas, entre em contato com nosso escritório."
        )
    elif is_quitacao_erro:
        headline = "Desconsiderar quitação — Nota de Reembolso"
        box_bg = "#fff7ed"
        box_border = "#fed7aa"
        box_color = "#9a3412"
        total_color = "#ea580c"
        intro = (
            f"Informamos que a quitação enviada anteriormente para a "
            f"<strong>Nota de Reembolso de Despesas</strong> referente a "
            f"<strong style='color:#1d1e20;'>{r.titulo}</strong> foi emitida em erro. "
            f"Por favor, desconsidere o e-mail de quitação anterior."
        )
    elif is_quitacao:
        headline = "Quitação — Nota de Reembolso de Despesas"
        box_bg = "#f0fdf9"
        box_border = "#a7f3d0"
        box_color = "#065f46"
        total_color = "#00b090"
        intro = (
            f"Confirmamos a quitação da <strong>Nota de Reembolso de Despesas</strong> referente a: "
            f"<strong style='color:#1d1e20;'>{r.titulo}</strong>."
        )
    elif is_lembrete:
        headline = "Lembrete — Nota de Reembolso de Despesas"
        box_bg = "#fff7ed"
        box_border = "#fed7aa"
        box_color = "#9a3412"
        total_color = "#ea580c"
        intro = (
            f"Este é um lembrete da <strong>Nota de Reembolso de Despesas</strong> referente a: "
            f"<strong style='color:#1d1e20;'>{r.titulo}</strong>. "
            f"Caso o pagamento já tenha sido realizado, por favor desconsidere esta mensagem."
        )
    else:
        headline = "Nota de Reembolso de Despesas"
        box_bg = "#f0fdf9"
        box_border = "#a7f3d0"
        box_color = "#065f46"
        total_color = "#00b090"
        intro = (
            f"Segue em anexo a <strong>Nota de Reembolso de Despesas</strong> referente a: "
            f"<strong style='color:#1d1e20;'>{r.titulo}</strong>."
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:{header_color};padding:28px 36px;">
            <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.75);">Pimenta Judice Advogados Associados</p>
            <h1 style="margin:8px 0 0;font-size:22px;font-weight:700;color:#ffffff;line-height:1.2;">{headline}</h1>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:28px 36px 8px;">
            <p style="margin:0 0 16px;font-size:14px;color:#374151;line-height:1.6;">Prezado(a),</p>
            <p style="margin:0 0 20px;font-size:14px;color:#374151;line-height:1.6;">{intro}</p>

            <!-- Summary box -->
            <table width="100%" cellpadding="0" cellspacing="0" style="background:{box_bg};border:1px solid {box_border};border-radius:8px;margin-bottom:24px;">
              <tr>
                <td style="padding:16px 20px;">
                  {vencimento_row}
                  <p style="margin:0;font-size:15px;color:{box_color};">
                    <strong>{'Total cancelado' if is_cancelamento else 'Total quitado' if is_quitacao else 'Total em aberto' if is_quitacao_erro else 'Total a reembolsar'}:</strong>
                    <span style="font-size:20px;font-weight:700;color:{total_color};margin-left:8px;">{_fmt_brl(r.total)}</span>
                  </p>
                </td>
              </tr>
            </table>

            <!-- Itens table -->
            <p style="margin:0 0 8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#9ca3af;">Detalhamento das despesas</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-bottom:28px;">
              <thead>
                <tr style="background:#f9fafb;">
                  <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;border-bottom:1px solid #e5e7eb;">Data</th>
                  <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;border-bottom:1px solid #e5e7eb;">Descrição</th>
                  <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;border-bottom:1px solid #e5e7eb;">Natureza</th>
                  <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;border-bottom:1px solid #e5e7eb;">Valor</th>
                </tr>
              </thead>
              <tbody>
                {itens_rows}
                <tr style="background:#f9fafb;">
                  <td colspan="3" style="padding:10px 12px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#374151;text-align:right;">Total</td>
                  <td style="padding:10px 12px;font-size:14px;font-weight:700;color:{total_color};text-align:right;">{_fmt_brl(r.total)}</td>
                </tr>
              </tbody>
            </table>

            <p style="margin:0 0 28px;font-size:13px;color:#6b7280;line-height:1.6;">
              Em caso de dúvidas, entre em contato.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:20px 36px;">
            <p style="margin:0;font-size:12px;font-weight:700;color:#1d1e20;">Pimenta Judice Advogados Associados</p>
            <p style="margin:4px 0 0;font-size:11px;color:#9ca3af;">pj@pimentajudice.com.br</p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _send_gmail(
    access_token: str,
    to: str,
    subject: str,
    html: str,
    pdf_bytes: bytes | None = None,
    pdf_filename: str | None = None,
    bcc: list[str] | None = None,
) -> dict:
    import email.mime.application as mime_app
    import email.mime.multipart as mime_multi
    import email.mime.text as mime_text

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
        anexo.add_header("Content-Disposition", "attachment", filename=pdf_filename or "nota.pdf")
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
    )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {resp.text}")
    return resp.json()


def _get_pdf_with_drive_link(r: Reembolso, db: Session) -> bytes:
    """Generates (or reads) the PDF for a reembolso, always including Drive folder link."""
    from app.models.cliente import Cliente

    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
    cliente_nome = cliente.nome if cliente else "—"
    cliente_cpf_cnpj = cliente.cpf_cnpj if cliente else None

    processo_titulo = r.titulo
    if r.processo_id:
        from app.models.processo import Processo
        proc = db.query(Processo).filter(Processo.id == r.processo_id).first()
        if proc:
            processo_titulo = proc.numero_cnj

    itens_dict = [
        {
            "data": item.data,
            "descricao": item.descricao,
            "natureza": item.natureza,
            "documento_comprobatorio": item.documento_comprobatorio,
            "valor": float(item.valor),
        }
        for item in sorted(r.itens, key=lambda x: x.data)
    ]

    # Always fetch Drive folder link (specific subfolder for this reembolso)
    drive_folder_link: str | None = None
    try:
        from app.services.google_drive import get_folder_link
        drive_folder_link = get_folder_link(cliente_nome, "Reembolsos", sub_subfolder=_reembolso_folder_name(r))
    except Exception:
        pass

    return gerar_pdf(
        cliente_nome=cliente_nome,
        cliente_cpf_cnpj=cliente_cpf_cnpj,
        titulo=processo_titulo,
        data_emissao=r.data_emissao,
        data_vencimento=r.data_vencimento,
        itens=itens_dict,
        total=r.total,
        drive_folder_link=drive_folder_link,
    )


def _destinatario_reembolso(r: Reembolso, db: Session) -> tuple[str, str]:
    from app.models.cliente import Cliente

    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
    destinatario = (r.email_destinatario or "").strip()
    if not destinatario and cliente and cliente.email:
        destinatario = cliente.email.strip()
    if not destinatario:
        raise HTTPException(status_code=400, detail="Reembolso sem e-mail do cliente/destinatário")
    return destinatario, cliente.nome if cliente else "cliente"


# ── CRUD Reembolso ────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ReembolsoOut])
def listar_reembolsos(
    cliente_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Reembolso)
    if cliente_id:
        q = q.filter(Reembolso.cliente_id == cliente_id)
    return q.order_by(Reembolso.created_at.desc()).all()


@router.post("/", response_model=ReembolsoOut, status_code=status.HTTP_201_CREATED)
def criar_reembolso(data: ReembolsoCreate, db: Session = Depends(get_db)):
    r = Reembolso(**data.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.get("/{reembolso_id}", response_model=ReembolsoOut)
def obter_reembolso(reembolso_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    return r


@router.patch("/{reembolso_id}", response_model=ReembolsoOut)
def atualizar_reembolso(
    reembolso_id: uuid.UUID, data: ReembolsoUpdate, db: Session = Depends(get_db)
):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{reembolso_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_reembolso(reembolso_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    try:
        from app.models.cliente import Cliente
        from app.services.google_drive import deletar_arquivo, deletar_pasta
        cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
        if cliente:
            folder_name = _reembolso_folder_name(r)
            deletar_arquivo(cliente.nome, "Reembolsos", f"nota_reembolso_{reembolso_id}.pdf", sub_subfolder=folder_name)
            for item in r.itens or []:
                if item.comprovante_path:
                    deletar_arquivo(cliente.nome, "Reembolsos", Path(item.comprovante_path).name, sub_subfolder=folder_name)
            deletar_pasta(cliente.nome, "Reembolsos", folder_name)
    except Exception:
        pass
    db.delete(r)
    db.commit()


# ── Cancelar ──────────────────────────────────────────────────────────────────

@router.post("/{reembolso_id}/cancelar", response_model=ReembolsoOut)
def cancelar_reembolso(reembolso_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    r.status = "cancelado"
    db.commit()
    db.refresh(r)

    # Send cancellation email to client (best-effort)
    try:
        from app.models.cliente import Cliente
        cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
        if cliente and getattr(cliente, "email", None):
            access_token = _refresh_if_needed()
            if access_token:
                html = _build_email_html(r, header_color="#dc2626", is_cancelamento=True)
                _send_gmail(
                    access_token=access_token,
                    to=cliente.email,
                    subject=f"[CANCELADA] Nota de Reembolso — {r.titulo}",
                    html=html,
                    bcc=[BCC_EMAIL_FIXO],
                )
    except Exception:
        pass

    return r


@router.post("/{reembolso_id}/marcar-pago", response_model=ReembolsoOut)
def marcar_reembolso_pago(
    reembolso_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    if r.status == "pago":
        return r
    if r.status == "cancelado":
        raise HTTPException(status_code=400, detail="Reembolso cancelado não pode ser marcado como pago")

    destinatario, _cliente_nome = _destinatario_reembolso(r, db)
    access_token = _refresh_if_needed()
    if not access_token:
        raise HTTPException(status_code=503, detail="Google não autenticado. Faça o OAuth em /auth/google")

    html = _build_email_html(r, header_color="#00b090", is_quitacao=True)
    _send_gmail(
        access_token=access_token,
        to=destinatario,
        subject=f"Quitação — Nota de Reembolso de Despesas — {r.titulo}",
        html=html,
        bcc=_bcc_com_usuario(usuario, destinatario),
    )

    r.status = "pago"
    r.email_destinatario = destinatario
    db.commit()
    db.refresh(r)
    return r


@router.post("/{reembolso_id}/reverter-pagamento", response_model=ReembolsoOut)
def reverter_pagamento_reembolso(
    reembolso_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    if r.status != "pago":
        raise HTTPException(status_code=400, detail="Somente reembolsos pagos podem ter a quitação revertida")

    destinatario, _cliente_nome = _destinatario_reembolso(r, db)
    access_token = _refresh_if_needed()
    if not access_token:
        raise HTTPException(status_code=503, detail="Google não autenticado. Faça o OAuth em /auth/google")

    html = _build_email_html(r, header_color="#ea580c", is_quitacao_erro=True)
    _send_gmail(
        access_token=access_token,
        to=destinatario,
        subject=f"Desconsiderar quitação — Nota de Reembolso — {r.titulo}",
        html=html,
        bcc=_bcc_com_usuario(usuario, destinatario),
    )

    r.status = "enviado" if r.email_destinatario else "aguardando_pagamento"
    r.email_destinatario = destinatario
    r.ultimo_lembrete_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(r)
    return r


# ── Duplicar ──────────────────────────────────────────────────────────────────

@router.post("/{reembolso_id}/duplicar", response_model=ReembolsoOut, status_code=status.HTTP_201_CREATED)
def duplicar_reembolso(reembolso_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")

    from datetime import date
    novo = Reembolso(
        cliente_id=r.cliente_id,
        processo_id=r.processo_id,
        titulo=r.titulo + " (cópia)",
        data_emissao=date.today(),
        data_vencimento=r.data_vencimento,
        status="rascunho",
    )
    db.add(novo)
    db.flush()

    for item in sorted(r.itens, key=lambda x: x.data):
        novo_item = ItemReembolso(
            reembolso_id=novo.id,
            data=item.data,
            descricao=item.descricao,
            natureza=item.natureza,
            documento_comprobatorio=item.documento_comprobatorio,
            valor=item.valor,
        )
        db.add(novo_item)
        db.flush()
        # Copy comprovante file if it exists
        if item.comprovante_path:
            src = Path(item.comprovante_path)
            if src.exists():
                ext = src.suffix
                novo_nome = f"comprovante_{novo_item.id}{ext}"
                dest = UPLOADS_DIR / novo_nome
                dest.write_bytes(src.read_bytes())
                novo_item.comprovante_path = str(dest)

    db.commit()
    db.refresh(novo)
    return novo


# ── Itens ─────────────────────────────────────────────────────────────────────

@router.post("/{reembolso_id}/itens", response_model=ItemReembolsoOut,
             status_code=status.HTTP_201_CREATED)
def adicionar_item(
    reembolso_id: uuid.UUID, data: ItemReembolsoCreate, db: Session = Depends(get_db)
):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    item = ItemReembolso(reembolso_id=reembolso_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{reembolso_id}/itens/{item_id}", response_model=ItemReembolsoOut)
def atualizar_item(
    reembolso_id: uuid.UUID, item_id: uuid.UUID,
    data: ItemReembolsoUpdate, db: Session = Depends(get_db),
):
    item = db.query(ItemReembolso).filter(
        ItemReembolso.id == item_id,
        ItemReembolso.reembolso_id == reembolso_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{reembolso_id}/itens/{item_id}/upload-comprovante", response_model=ItemReembolsoOut)
def upload_comprovante(
    reembolso_id: uuid.UUID,
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    item = db.query(ItemReembolso).filter(
        ItemReembolso.id == item_id,
        ItemReembolso.reembolso_id == reembolso_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    reembolso = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()

    conteudo = file.file.read()
    ext = Path(file.filename or "comprovante.pdf").suffix or ".pdf"
    nome_arquivo = f"comprovante_{item_id}{ext}"

    # Salva localmente
    destino_local = UPLOADS_DIR / nome_arquivo
    destino_local.write_bytes(conteudo)
    item.comprovante_path = str(destino_local)
    # Auto-set documento_comprobatorio from filename if not set
    if not item.documento_comprobatorio and file.filename:
        item.documento_comprobatorio = file.filename

    db.commit()
    db.refresh(item)

    # Upload to Drive under specific reembolso subfolder (best-effort)
    try:
        from app.models.cliente import Cliente
        from app.services.google_drive import upload_arquivo
        if reembolso:
            cliente = db.query(Cliente).filter(Cliente.id == reembolso.cliente_id).first()
            if cliente:
                ext_lower = ext.lower()
                mime = "image/jpeg" if ext_lower in (".jpg", ".jpeg") else \
                       "image/png" if ext_lower == ".png" else "application/pdf"
                upload_arquivo(conteudo, nome_arquivo, cliente.nome, "Reembolsos", mime,
                               sub_subfolder=_reembolso_folder_name(reembolso))
    except Exception:
        pass

    return item


@router.delete("/{reembolso_id}/itens/{item_id}/comprovante", response_model=ItemReembolsoOut)
def remover_comprovante(
    reembolso_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    item = db.query(ItemReembolso).filter(
        ItemReembolso.id == item_id,
        ItemReembolso.reembolso_id == reembolso_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    reembolso = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if item.comprovante_path:
        nome_drive = Path(item.comprovante_path).name
        try:
            Path(item.comprovante_path).unlink(missing_ok=True)
        except Exception:
            pass
        try:
            from app.models.cliente import Cliente
            from app.services.google_drive import deletar_arquivo
            if reembolso:
                cliente = db.query(Cliente).filter(Cliente.id == reembolso.cliente_id).first()
                if cliente:
                    deletar_arquivo(cliente.nome, "Reembolsos", nome_drive, sub_subfolder=_reembolso_folder_name(reembolso))
        except Exception:
            pass
        item.comprovante_path = None
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{reembolso_id}/itens/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_item(
    reembolso_id: uuid.UUID, item_id: uuid.UUID, db: Session = Depends(get_db)
):
    item = db.query(ItemReembolso).filter(
        ItemReembolso.id == item_id,
        ItemReembolso.reembolso_id == reembolso_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    if item.comprovante_path:
        try:
            from app.models.cliente import Cliente
            from app.services.google_drive import deletar_arquivo
            reembolso = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
            if reembolso:
                cliente = db.query(Cliente).filter(Cliente.id == reembolso.cliente_id).first()
                if cliente:
                    deletar_arquivo(cliente.nome, "Reembolsos", Path(item.comprovante_path).name, sub_subfolder=_reembolso_folder_name(reembolso))
        except Exception:
            pass
    db.delete(item)
    db.commit()


# ── Gerar PDF ─────────────────────────────────────────────────────────────────

@router.post("/{reembolso_id}/gerar-pdf")
def gerar_nota_pdf(reembolso_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    if not r.itens:
        raise HTTPException(status_code=400, detail="Adicione ao menos um item antes de gerar o PDF")

    pdf_bytes = _get_pdf_with_drive_link(r, db)

    # Salva localmente
    from app.models.cliente import Cliente
    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
    cliente_nome = cliente.nome if cliente else "—"

    nome_arquivo = f"nota_reembolso_{reembolso_id}.pdf"
    destino = UPLOADS_DIR / nome_arquivo
    destino.write_bytes(pdf_bytes)
    r.pdf_path = str(destino)
    if r.status == "rascunho":
        r.status = "aguardando_pagamento"
    db.commit()

    # Upload PDF to Drive under specific reembolso subfolder
    drive_folder_link: str | None = None
    try:
        from app.services.google_drive import upload_pdf, get_folder_link
        folder_name = _reembolso_folder_name(r)
        upload_pdf(pdf_bytes, nome_arquivo, cliente_nome, "Reembolsos", sub_subfolder=folder_name)
        # Store the folder link (not the file link) for easier navigation
        drive_folder_link = get_folder_link(cliente_nome, "Reembolsos", sub_subfolder=folder_name)
        if drive_folder_link:
            r.drive_link = drive_folder_link
            db.commit()
    except Exception:
        pass

    return FileResponse(
        str(destino),
        media_type="application/pdf",
        filename=f"Nota de Reembolso - {cliente_nome}.pdf",
        headers={"X-Drive-Link": drive_folder_link or ""},
    )


@router.get("/{reembolso_id}/download-pdf")
def download_pdf(reembolso_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r or not r.pdf_path:
        raise HTTPException(status_code=404, detail="PDF não gerado ainda")
    from app.models.cliente import Cliente
    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
    nome = cliente.nome if cliente else str(reembolso_id)
    return FileResponse(r.pdf_path, media_type="application/pdf",
                        filename=f"Nota de Reembolso - {nome}.pdf")


# ── Enviar por e-mail via Gmail ───────────────────────────────────────────────

@router.post("/{reembolso_id}/enviar-email")
def enviar_email(
    reembolso_id: uuid.UUID,
    destinatario: str,
    copiar_usuario: bool = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    r = db.query(Reembolso).filter(Reembolso.id == reembolso_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado")
    if not r.itens:
        raise HTTPException(status_code=400, detail="Sem itens para enviar")

    from app.models.cliente import Cliente
    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
    cliente_nome = cliente.nome if cliente else "—"

    # Always regenerate PDF so Drive link is current
    pdf_bytes = _get_pdf_with_drive_link(r, db)
    nome_arquivo = f"nota_reembolso_{reembolso_id}.pdf"
    destino = UPLOADS_DIR / nome_arquivo
    destino.write_bytes(pdf_bytes)
    r.pdf_path = str(destino)
    try:
        from app.services.google_drive import get_folder_link, upload_pdf
        folder_name = _reembolso_folder_name(r)
        upload_pdf(pdf_bytes, nome_arquivo, cliente_nome, "Reembolsos", sub_subfolder=folder_name)
        r.drive_link = get_folder_link(cliente_nome, "Reembolsos", sub_subfolder=folder_name)
    except Exception:
        pass
    db.commit()

    access_token = _refresh_if_needed()
    if not access_token:
        raise HTTPException(status_code=503, detail="Google não autenticado. Faça o OAuth em /auth/google")

    html = _build_email_html(r)
    bcc = [BCC_EMAIL_FIXO]
    if copiar_usuario:
        usuario_email = _usuario_email(usuario)
        if usuario_email and usuario_email not in {destinatario, BCC_EMAIL_FIXO}:
            bcc.append(usuario_email)
    result = _send_gmail(
        access_token=access_token,
        to=destinatario,
        subject=f"Nota de Reembolso de Despesas — {r.titulo}",
        html=html,
        pdf_bytes=pdf_bytes,
        pdf_filename=f"Nota de Reembolso - {cliente_nome}.pdf",
        bcc=bcc,
    )

    r.status = "enviado"
    r.email_destinatario = destinatario
    r.ultimo_lembrete_em = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "message_id": result.get("id")}
