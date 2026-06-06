"""Serviço de email para notificação de tarefas atribuídas.

Usa a mesma infra de Gmail (master token) dos outros emails do sistema.
Chame `notificar_responsavel(db, tarefa, dry_run=True)` para logar sem enviar.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models.tarefa import Tarefa
from app.models.usuario import Usuario

log = logging.getLogger(__name__)

# Cor do header dos emails de tarefa — azul-índigo, diferente do verde (#00b090) dos reembolsos
_HEADER_COLOR = "#4f46e5"


def _fmt_data(d) -> str:
    if not d:
        return "Sem prazo definido"
    if hasattr(d, "strftime"):
        return d.strftime("%d/%m/%Y")
    return str(d)


def build_tarefa_email_html(
    tarefa: Tarefa,
    responsavel_nome: str,
    adicionado_por_nome: str | None,
    cliente_nome: str | None,
    processo_numero: str | None,
    frontend_url: str,
) -> str:
    from_telegram = tarefa.tags and "telegram" in tarefa.tags
    origem_badge = (
        '<span style="display:inline-block;background:#e0f2fe;color:#0369a1;'
        'font-size:11px;font-weight:700;border-radius:4px;padding:2px 8px;margin-left:8px;">'
        "✈ Via Telegram</span>"
        if from_telegram else ""
    )

    prazo_str = _fmt_data(tarefa.data_limite)
    prazo_color = "#dc2626" if tarefa.data_limite and tarefa.data_limite < datetime.today().date() else "#374151"

    _td_label = 'style="padding:7px 0 7px 20px;font-size:13px;color:#6b7280;width:130px;"'
    _td_value = 'style="padding:7px 20px 7px 0;font-size:13px;color:#1d1e20;"'
    _td_value_bold = 'style="padding:7px 20px 7px 0;font-size:13px;color:#1d1e20;font-weight:500;"'

    cliente_row = (
        f'<tr><td {_td_label}>Cliente</td>'
        f'<td {_td_value_bold}>{cliente_nome}</td></tr>'
        if cliente_nome else ""
    )
    processo_row = (
        f'<tr><td {_td_label}>Processo</td>'
        f'<td {_td_value}>{processo_numero}</td></tr>'
        if processo_numero else ""
    )
    descricao_row = (
        f'<tr><td colspan="2" style="padding:7px 20px 12px;font-size:13px;border-top:1px solid #f3f4f6;">'
        f'<div style="margin-bottom:4px;font-weight:600;color:#374151;">Notas</div>'
        f'<div style="color:#374151;line-height:1.6;">{tarefa.descricao}</div></td></tr>'
        if tarefa.descricao else ""
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
        style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:{_HEADER_COLOR};padding:28px 36px;">
            <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.7);">
              Pimenta Judice Advogados Associados
            </p>
            <h1 style="margin:8px 0 0;font-size:22px;font-weight:700;color:#ffffff;line-height:1.2;">
              Tarefa atribuída a você
            </h1>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:28px 36px 8px;">
            <p style="margin:0 0 20px;font-size:14px;color:#374151;line-height:1.6;">
              Olá, <strong>{responsavel_nome}</strong>. Uma tarefa foi atribuída a você{f" por <strong>{adicionado_por_nome}</strong>" if adicionado_por_nome else ""}.
            </p>

            <!-- Tarefa box -->
            <table width="100%" cellpadding="0" cellspacing="0"
              style="background:#f0f1ff;border:1px solid #c7d2fe;border-radius:8px;margin-bottom:24px;">
              <tr>
                <td style="padding:16px 20px;">
                  <p style="margin:0 0 4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#6366f1;">
                    Tarefa
                  </p>
                  <p style="margin:0;font-size:18px;font-weight:700;color:#1d1e20;line-height:1.3;">
                    {tarefa.titulo}{origem_badge}
                  </p>
                </td>
              </tr>
            </table>

            <!-- Detalhes -->
            <table width="100%" cellpadding="0" cellspacing="0"
              style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-bottom:28px;">
              <tbody style="padding:12px 20px;">
                <tr><td colspan="2" style="padding:12px 20px 0;"></td></tr>
                {cliente_row}
                {processo_row}
                <tr>
                  <td style="padding:7px 0 7px 20px;font-size:13px;color:#6b7280;width:130px;">Prazo</td>
                  <td style="padding:7px 20px 7px 0;font-size:13px;font-weight:600;color:{prazo_color};">{prazo_str}</td>
                </tr>
                {f'<tr><td style="padding:7px 0 7px 20px;font-size:13px;color:#6b7280;">Adicionado em</td><td style="padding:7px 20px 7px 0;font-size:13px;color:#374151;">{_fmt_data(tarefa.created_at.date() if tarefa.created_at else None)}</td></tr>' if tarefa.created_at else ""}
                <tr><td colspan="2" style="padding:0 20px 12px;"></td></tr>
                {descricao_row}
              </tbody>
            </table>

            <!-- CTA -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:32px;">
              <tr>
                <td align="center">
                  <a href="{frontend_url}/tarefas"
                    style="display:inline-block;padding:12px 28px;background:{_HEADER_COLOR};color:#fff;
                    font-size:14px;font-weight:700;text-decoration:none;border-radius:8px;letter-spacing:0.02em;">
                    Abrir no LexOps →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 36px;background:#f9fafb;border-top:1px solid #f3f4f6;">
            <p style="margin:0;font-size:11px;color:#9ca3af;text-align:center;">
              Gestor Jurídico — Pimenta Judice Advogados &middot;
              <a href="{frontend_url}" style="color:#9ca3af;">lexops.fly.dev</a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def notificar_responsavel(
    db: Session,
    tarefa: Tarefa,
    dry_run: bool = False,
) -> bool:
    """Envia email ao responsável da tarefa.

    Retorna True se enviado (ou logado em dry_run), False se não há email/token.
    dry_run=True: loga HTML mas não envia.
    """
    dest_email = tarefa.responsavel_email
    if not dest_email:
        # Tenta encontrar usuário pelo nome
        if tarefa.responsavel:
            u = db.query(Usuario).filter(Usuario.nome == tarefa.responsavel, Usuario.ativo == True).first()  # noqa: E712
            if u:
                dest_email = u.email

    if not dest_email:
        log.info("tarefa_email: responsavel '%s' sem email — skip", tarefa.responsavel)
        return False

    # Enriquecer dados
    responsavel_nome = tarefa.responsavel or dest_email
    adicionado_por_nome: str | None = None
    if tarefa.criado_por_id:
        criador = db.query(Usuario).filter(Usuario.id == tarefa.criado_por_id).first()
        if criador:
            adicionado_por_nome = criador.nome

    cliente_nome: str | None = None
    if tarefa.cliente_id:
        from app.models.cliente import Cliente
        c = db.query(Cliente).filter(Cliente.id == tarefa.cliente_id).first()
        if c:
            cliente_nome = c.nome

    processo_numero: str | None = None
    if tarefa.processo_id:
        from app.models.processo import Processo
        p = db.query(Processo).filter(Processo.id == tarefa.processo_id).first()
        if p:
            processo_numero = p.numero_cnj

    html = build_tarefa_email_html(
        tarefa=tarefa,
        responsavel_nome=responsavel_nome,
        adicionado_por_nome=adicionado_por_nome,
        cliente_nome=cliente_nome,
        processo_numero=processo_numero,
        frontend_url=settings.frontend_url,
    )

    subject = f"Tarefa atribuída: {tarefa.titulo}"

    if dry_run:
        log.info("tarefa_email DRY-RUN → %s | assunto: %s\n\n%s", dest_email, subject, html)
        return True

    # Enviar via Gmail master token (mesma lógica do bot de Reembolsos)
    try:
        from app.services.google_calendar import _load_tokens, _refresh_token
        tokens = _load_tokens()
        if not tokens:
            log.warning("tarefa_email: sem tokens Gmail para enviar")
            return False
        try:
            tokens = _refresh_token(tokens)
        except Exception:
            pass
        access_token = tokens.get("access_token")
        if not access_token:
            return False

        import email.mime.multipart as mime_multi
        import email.mime.text as mime_text
        import base64
        import httpx

        msg = mime_multi.MIMEMultipart("alternative")
        msg["to"] = dest_email
        msg["from"] = "me"
        msg["subject"] = subject
        msg.attach(mime_text.MIMEText(html, "html", "utf-8"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"raw": raw},
            timeout=20,
        )
        if resp.status_code in (200, 201):
            log.info("tarefa_email: enviado para %s", dest_email)
            return True
        log.warning("tarefa_email: Gmail API %s — %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        log.exception("tarefa_email: erro ao enviar — %s", exc)
        return False
