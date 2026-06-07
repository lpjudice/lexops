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


def _html(dados: dict) -> str:
    ini, fim = dados["periodo"]
    linhas_nf = "".join(
        f"<tr><td>{n.numero_nfse or '—'}</td><td>{n.tomador_nome}</td>"
        f"<td style='text-align:right'>{_fmt(n.valor_servicos)}</td></tr>"
        for n in dados["notas"]
    ) or "<tr><td colspan=3 style='color:#888'>Nenhuma NF emitida</td></tr>"

    mes_label = datetime.strptime(dados["competencia"] + "-01", "%Y-%m-%d").strftime("%m/%Y")
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;color:#1f2937">
<h2 style="color:#00B090">Relatório Fiscal — {mes_label}</h2>
<p>Período: {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')} — Pimenta Judice Advogados</p>

<h3>Resumo</h3>
<ul>
  <li><b>NFS-e emitidas:</b> {dados['nf_qtd']} — total {_fmt(dados['nf_total'])}</li>
  <li><b>Recebimentos no mês:</b> {_fmt(dados['receb_total'])}</li>
  <li><b>Reembolsos pagos:</b> {_fmt(dados['reemb_total'])}</li>
</ul>

<h3>Notas Fiscais emitidas</h3>
<table border=1 cellpadding=6 cellspacing=0 style="border-collapse:collapse;font-size:13px">
  <thead style="background:#ecfdf5"><tr><th>Nº</th><th>Tomador</th><th>Valor</th></tr></thead>
  <tbody>{linhas_nf}</tbody>
</table>

<p style="font-size:12px;color:#6b7280;margin-top:20px">
Os PDFs (DANFSe) das notas seguem em anexo. Relatório gerado automaticamente pelo LexOps.
</p>
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
            anexos.append((f"NFSe_{n.numero_nfse or n.chave_acesso}.pdf", pdf))

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
