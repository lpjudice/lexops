"""Relatório mensal para o contador: resumo de NFs, recebimentos e reembolsos pagos.

Envia por e-mail (Gmail OAuth master) para os contadores + cópia master,
anexando os PDFs das NFs emitidas no mês.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import date, datetime, timezone, timedelta

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
BRT = timezone(timedelta(hours=-3))


def _fmt(v) -> str:
    return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _periodo(competencia: str) -> tuple[date, date]:
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    ini = date(ano, mes, 1)
    fim = date(ano + (mes // 12), (mes % 12) + 1, 1) - timedelta(days=1)
    return ini, fim


def coletar_dados(db: Session, competencia: str) -> dict:
    from app.models.nota_fiscal import NotaFiscal
    from app.models.financeiro import Recebimento
    from app.models.reembolso import Reembolso

    ini, fim = _periodo(competencia)

    notas = (
        db.query(NotaFiscal)
        .filter(NotaFiscal.status == "emitida", NotaFiscal.competencia == competencia)
        .order_by(NotaFiscal.data_emissao)
        .all()
    )
    nf_total = sum(float(n.valor_servicos) for n in notas)
    nf_iss = 0.0  # ISS vem no XML; resumo aproximado

    recebimentos = (
        db.query(Recebimento)
        .filter(Recebimento.data_recebimento >= ini, Recebimento.data_recebimento <= fim)
        .all()
    )
    receb_total = sum(float(r.valor) for r in recebimentos)

    # Reembolsos pagos no período
    reembolsos = []
    reemb_total = 0.0
    try:
        q = db.query(Reembolso).filter(Reembolso.status == "pago")
        for r in q.all():
            dt = getattr(r, "data_pagamento", None) or getattr(r, "updated_at", None)
            d = dt.date() if hasattr(dt, "date") else dt
            if d and ini <= d <= fim:
                reembolsos.append(r)
                reemb_total += float(getattr(r, "valor_total", 0) or 0)
    except Exception as exc:
        log.warning("Reembolsos no relatório: %s", exc)

    return {
        "competencia": competencia,
        "periodo": (ini, fim),
        "notas": notas,
        "nf_total": nf_total,
        "nf_qtd": len(notas),
        "recebimentos": recebimentos,
        "receb_total": receb_total,
        "reembolsos": reembolsos,
        "reemb_total": reemb_total,
    }


# Cor de destaque do relatório fiscal — âmbar/dourado (distinta do teal dos demais e-mails)
AMBER = "#d4a017"
AMBER_SOFT = "#3a3320"


def _html(dados: dict) -> str:
    ini, fim = dados["periodo"]
    mes_label = datetime.strptime(dados["competencia"] + "-01", "%Y-%m-%d").strftime("%m/%Y")

    def _link_pdf(n) -> str:
        if getattr(n, "drive_link", None):
            return f'<a href="{n.drive_link}" style="color:{AMBER};text-decoration:none;font-weight:700;">PDF ↗</a>'
        return '<span style="color:#555;">anexo</span>'

    linhas_nf = "".join(
        f'<tr>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #2a2a2a;color:#d4d4d4;">{n.numero_nfse or "—"}</td>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #2a2a2a;color:#d4d4d4;">{n.tomador_nome}</td>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #2a2a2a;text-align:right;color:#d4d4d4;">{_fmt(n.valor_servicos)}</td>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #2a2a2a;text-align:center;">{_link_pdf(n)}</td>'
        f'</tr>'
        for n in dados["notas"]
    ) or '<tr><td colspan=4 style="padding:12px;color:#666;">Nenhuma NF emitida no período</td></tr>'

    def _resumo(label, valor, cor="#f5f5f5"):
        return (f'<td style="padding:14px 18px;background:#141414;border:1px solid #2a2a2a;border-radius:10px;">'
                f'<p style="margin:0;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#777;">{label}</p>'
                f'<p style="margin:4px 0 0;font-size:18px;font-weight:800;color:{cor};">{valor}</p></td>')

    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#111;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#111;">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:640px;background:#1a1a1a;border-radius:16px;border:1px solid #2a2a2a;overflow:hidden;">
        <!-- Header com faixa âmbar -->
        <tr><td style="background:{AMBER_SOFT};padding:22px 32px;border-bottom:2px solid {AMBER};">
          <p style="margin:0;font-size:13px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:{AMBER};">📊 RELATÓRIO FISCAL</p>
          <p style="margin:2px 0 0;font-size:11px;letter-spacing:.10em;text-transform:uppercase;color:#999;">Pimenta Judice Advogados · {mes_label}</p>
        </td></tr>
        <!-- Corpo -->
        <tr><td style="padding:28px 32px;">
          <p style="margin:0 0 20px;font-size:13px;color:#888;">
            Período: {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}
          </p>
          <table width="100%" cellpadding="0" cellspacing="6" role="presentation" style="margin-bottom:24px;"><tr>
            {_resumo("NFS-e emitidas", f"{dados['nf_qtd']} · {_fmt(dados['nf_total'])}", AMBER)}
            {_resumo("Recebimentos", _fmt(dados['receb_total']), "#4ade80")}
            {_resumo("Reembolsos pagos", _fmt(dados['reemb_total']), "#f87171")}
          </tr></table>

          <p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#777;">Notas Fiscais emitidas</p>
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                 style="border-collapse:collapse;font-size:13px;background:#141414;border-radius:8px;overflow:hidden;">
            <thead><tr style="background:#222;">
              <th style="padding:8px 10px;text-align:left;color:#999;font-size:11px;">Nº</th>
              <th style="padding:8px 10px;text-align:left;color:#999;font-size:11px;">Tomador</th>
              <th style="padding:8px 10px;text-align:right;color:#999;font-size:11px;">Valor</th>
              <th style="padding:8px 10px;text-align:center;color:#999;font-size:11px;">DANFSe</th>
            </tr></thead>
            <tbody>{linhas_nf}</tbody>
          </table>

          <p style="margin:22px 0 0;font-size:12px;color:#666;line-height:1.6;">
            Os PDFs (DANFSe) seguem <b style="color:#999;">em anexo</b> e também por <b style="color:{AMBER};">link no Drive</b> em cada nota.
            Relatório gerado automaticamente pelo LexOps.
          </p>
        </td></tr>
        <tr><td style="background:#141414;padding:16px 32px;border-top:1px solid #2a2a2a;">
          <p style="margin:0;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#555;">Pimenta Judice · LexOps</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _enviar(access_token: str, to_list: list[str], cc_master: str | None,
            subject: str, html: str, anexos: list[tuple[str, bytes]]) -> None:
    import email.mime.application as mime_app
    import email.mime.multipart as mime_multi
    import email.mime.text as mime_text

    outer = mime_multi.MIMEMultipart("mixed")
    outer["to"] = ", ".join(to_list)
    outer["from"] = "me"
    outer["subject"] = subject
    if cc_master:
        outer["cc"] = cc_master

    alt = mime_multi.MIMEMultipart("alternative")
    alt.attach(mime_text.MIMEText(html, "html", "utf-8"))
    outer.attach(alt)

    for nome, pdf in anexos:
        a = mime_app.MIMEApplication(pdf, _subtype="pdf")
        a.add_header("Content-Disposition", "attachment", filename=nome)
        outer.attach(a)

    raw = base64.urlsafe_b64encode(outer.as_bytes()).decode()
    resp = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        content=json.dumps({"raw": raw}), timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Gmail falhou: {resp.status_code} {resp.text[:200]}")


def enviar_relatorio(db: Session, competencia: str | None = None) -> dict:
    """Monta e envia o relatório do mês indicado (default: mês anterior)."""
    from app.models.config_fiscal import ConfigFiscal
    from app.routers.reembolsos import _refresh_if_needed

    if not competencia:
        hoje = datetime.now(tz=BRT).date()
        primeiro = hoje.replace(day=1)
        ant = primeiro - timedelta(days=1)
        competencia = ant.strftime("%Y-%m")

    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
    destinatarios = list(cfg.emails_contador) if cfg and cfg.emails_contador else []
    master = cfg.email_master if cfg else None
    if not destinatarios and not master:
        return {"enviado": False, "motivo": "Sem e-mails configurados (contador/master)."}
    if not destinatarios and master:
        destinatarios = [master]
        master = None

    dados = coletar_dados(db, competencia)

    # Anexos: PDFs das NFs (gera se faltar)
    import os
    from app.services.nfse.danfse_pdf import gerar_danfse_pdf
    from app.services.nfse.emitter import subir_pdf_drive
    anexos: list[tuple[str, bytes]] = []
    for n in dados["notas"]:
        pdf = None
        if n.pdf_path and os.path.exists(n.pdf_path):
            pdf = open(n.pdf_path, "rb").read()
        elif n.xml_nfse:
            try:
                pdf = gerar_danfse_pdf(n.xml_nfse, n.chave_acesso)
            except Exception:
                pdf = None
        if pdf:
            nome = f"NFSe_{n.numero_nfse or n.chave_acesso}.pdf"
            anexos.append((nome, pdf))
            # Garante link do Drive em cada NF
            if not getattr(n, "drive_link", None):
                link = subir_pdf_drive(pdf, nome, n.tomador_nome)
                if link:
                    n.drive_link = link
    db.commit()

    token = _refresh_if_needed()
    if not token:
        return {"enviado": False, "motivo": "Conta Google master não autenticada."}

    mes_label = datetime.strptime(competencia + "-01", "%Y-%m-%d").strftime("%m/%Y")
    _enviar(token, destinatarios, master,
            f"Relatório Fiscal {mes_label} — Pimenta Judice",
            _html(dados), anexos)

    return {
        "enviado": True, "competencia": competencia,
        "destinatarios": destinatarios, "cc": master,
        "nf_qtd": dados["nf_qtd"], "anexos": len(anexos),
    }
