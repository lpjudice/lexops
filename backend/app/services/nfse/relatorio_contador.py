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


def coletar_dados(db: Session, competencia: str, parcial: bool = False, ate: date | None = None) -> dict:
    from app.models.nota_fiscal import NotaFiscal
    from app.models.financeiro import Recebimento
    from app.models.reembolso import Reembolso
    from app.models.backoffice import FiscalDespesa

    ini, fim = _periodo(competencia)
    # Modo parcial: corta o fim no dia informado (ou hoje)
    if parcial:
        hoje = ate or date.today()
        if hoje < fim:
            fim = hoje

    notas = (
        db.query(NotaFiscal)
        .filter(NotaFiscal.status == "emitida", NotaFiscal.competencia == competencia,
                NotaFiscal.ambiente == 1)
        .all()
    )
    # Ordena por número da NFS-e — da mais alta (recente) para a mais baixa
    def _num(n):
        try:
            return int(n.numero_nfse)
        except (TypeError, ValueError):
            return -1
    notas.sort(key=_num, reverse=True)
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

    # Despesas do mes
    despesas = (
        db.query(FiscalDespesa)
        .filter(FiscalDespesa.mes == competencia)
        .order_by(FiscalDespesa.data.desc().nullslast(), FiscalDespesa.created_at)
        .all()
    )
    # Se parcial: filtra pelo campo data (quando existir)
    if parcial:
        despesas = [d for d in despesas if not d.data or d.data <= fim]
    desp_total = sum(float(d.valor) for d in despesas)
    desp_elegivel = sum(float(d.valor) for d in despesas if d.tem_nota and d.elegivel)

    return {
        "competencia": competencia,
        "periodo": (ini, fim),
        "parcial": parcial,
        "notas": notas,
        "nf_total": nf_total,
        "nf_qtd": len(notas),
        "recebimentos": recebimentos,
        "receb_total": receb_total,
        "reembolsos": reembolsos,
        "reemb_total": reemb_total,
        "despesas": despesas,
        "desp_total": desp_total,
        "desp_elegivel": desp_elegivel,
        "nf_iss": nf_iss,
    }


# Tema claro com destaque âmbar legível (distinto do teal dos demais e-mails)
AMBER = "#b45309"        # âmbar escuro — legível sobre branco
AMBER_BG = "#fef6e7"     # faixa âmbar clara
DARK = "#1f2937"
GRAY = "#6b7280"


def _bloco_despesas(dados: dict) -> str:
    """Tabela de despesas do mês com flag de elegibilidade IBS/CBS."""
    despesas = dados.get('despesas') or []
    if not despesas:
        return ""
    linhas = []
    for d in despesas:
        cat = (d.categoria or '—')[:40]
        forn = (d.fornecedor or '—')[:40]
        dt = d.data.strftime('%d/%m') if getattr(d, 'data', None) else '—'
        nf_label = '✓' if d.tem_nota else '—'
        eleg_label = '✓ IBS/CBS' if (d.tem_nota and d.elegivel) else '—'
        cor_eleg = '#15803d' if (d.tem_nota and d.elegivel) else '#9ca3af'
        link = ''
        if getattr(d, 'drive_link', None):
            link = f'<a href="{d.drive_link}" style="color:#1d4ed8;text-decoration:none;font-weight:700;">📎</a>'
        linhas.append(
            f'<tr><td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;font-size:12px;color:#6b7280;">{dt}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;font-size:12px;color:#1f2937;font-weight:600;">{forn}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;font-size:11px;color:#6b7280;">{cat}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;font-size:12px;text-align:right;">{_fmt(float(d.valor))}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;text-align:center;font-size:11px;">{nf_label}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;font-size:10px;font-weight:600;color:{cor_eleg};">{eleg_label}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;text-align:center;">{link}</td></tr>'
        )
    return f"""
      <p style="margin:24px 0 8px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#6b7280;">Despesas do mês</p>
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;font-size:13px;border:1px solid #eee;border-radius:8px;overflow:hidden;margin-bottom:12px;">
        <thead><tr style="background:#f9fafb;">
          <th style="padding:9px 10px;text-align:left;color:#6b7280;font-size:11px;">Data</th>
          <th style="padding:9px 10px;text-align:left;color:#6b7280;font-size:11px;">Fornecedor</th>
          <th style="padding:9px 10px;text-align:left;color:#6b7280;font-size:11px;">Categoria</th>
          <th style="padding:9px 10px;text-align:right;color:#6b7280;font-size:11px;">Valor</th>
          <th style="padding:9px 10px;text-align:center;color:#6b7280;font-size:11px;">NF</th>
          <th style="padding:9px 10px;text-align:left;color:#6b7280;font-size:11px;">Elegível</th>
          <th style="padding:9px 10px;text-align:center;color:#6b7280;font-size:11px;">Anexo</th>
        </tr></thead>
        <tbody>{''.join(linhas)}</tbody>
        <tfoot><tr style="background:#f9fafb;font-weight:700;">
          <td colspan="3" style="padding:9px 10px;font-size:11px;color:#374151;">Total · {len(despesas)} despesa(s) — elegível IBS/CBS: {_fmt(dados.get('desp_elegivel', 0))}</td>
          <td style="padding:9px 10px;text-align:right;color:#1f2937;">{_fmt(dados.get('desp_total', 0))}</td>
          <td colspan="3"></td>
        </tr></tfoot>
      </table>
    """


def _html(dados: dict) -> str:
    ini, fim = dados["periodo"]
    mes_label = datetime.strptime(dados["competencia"] + "-01", "%Y-%m-%d").strftime("%m/%Y")

    def _link_pdf(n) -> str:
        if getattr(n, "drive_link", None):
            return f'<a href="{n.drive_link}" style="color:{AMBER};text-decoration:none;font-weight:700;">PDF ↗</a>'
        return '<span style="color:#9ca3af;">anexo</span>'

    linhas_nf = "".join(
        f'<tr>'
        f'<td style="padding:9px 10px;border-bottom:1px solid #eee;color:{DARK};">{n.numero_nfse or "—"}</td>'
        f'<td style="padding:9px 10px;border-bottom:1px solid #eee;color:{DARK};">{n.tomador_nome}</td>'
        f'<td style="padding:9px 10px;border-bottom:1px solid #eee;text-align:right;color:{DARK};">{_fmt(n.valor_servicos)}</td>'
        f'<td style="padding:9px 10px;border-bottom:1px solid #eee;text-align:center;">{_link_pdf(n)}</td>'
        f'</tr>'
        for n in dados["notas"]
    ) or f'<tr><td colspan=4 style="padding:12px;color:{GRAY};">Nenhuma NF emitida no período</td></tr>'

    def _resumo(label, valor, cor=DARK):
        return (f'<td style="padding:14px 18px;background:#f9fafb;border:1px solid #eee;border-radius:10px;">'
                f'<p style="margin:0;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:{GRAY};">{label}</p>'
                f'<p style="margin:4px 0 0;font-size:18px;font-weight:800;color:{cor};">{valor}</p></td>')

    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#f3f4f6;">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:640px;background:#ffffff;border-radius:16px;border:1px solid #e5e7eb;overflow:hidden;">
        <!-- Header com faixa âmbar clara -->
        <tr><td style="background:{AMBER_BG};padding:22px 32px;border-bottom:3px solid {AMBER};">
          <p style="margin:0;font-size:14px;font-weight:800;letter-spacing:.10em;text-transform:uppercase;color:{AMBER};">RELATÓRIO FISCAL</p>
          <p style="margin:3px 0 0;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{GRAY};">Pimenta Judice Advogados · {mes_label}</p>
        </td></tr>
        <tr><td style="padding:28px 32px;">
          <p style="margin:0 0 20px;font-size:13px;color:{GRAY};">
            Período: {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}
          </p>
          <table width="100%" cellpadding="0" cellspacing="6" role="presentation" style="margin-bottom:24px;"><tr>
            {_resumo("NFS-e emitidas", f"{dados['nf_qtd']} · {_fmt(dados['nf_total'])}", AMBER)}
            {_resumo("Recebimentos", _fmt(dados['receb_total']), "#15803d")}
            {_resumo("Despesas do mês", _fmt(dados.get('desp_total', 0)), "#1d4ed8")}
            {_resumo("Reembolsos pagos", _fmt(dados['reemb_total']), "#b91c1c")}
          </tr></table>

          {"<p style='margin:0 0 16px;padding:8px 12px;background:#fef9c3;border:1px solid #fde047;border-radius:6px;font-size:12px;color:#92400e;'><b>⚠ Parcial:</b> dados até " + fim.strftime('%d/%m/%Y') + " — mês ainda não fechado.</p>" if dados.get('parcial') else ""}

          <p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{GRAY};">Notas Fiscais emitidas</p>
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                 style="border-collapse:collapse;font-size:13px;border:1px solid #eee;border-radius:8px;overflow:hidden;">
            <thead><tr style="background:#f9fafb;">
              <th style="padding:9px 10px;text-align:left;color:{GRAY};font-size:11px;">Nº</th>
              <th style="padding:9px 10px;text-align:left;color:{GRAY};font-size:11px;">Tomador</th>
              <th style="padding:9px 10px;text-align:right;color:{GRAY};font-size:11px;">Valor</th>
              <th style="padding:9px 10px;text-align:center;color:{GRAY};font-size:11px;">DANFSe</th>
            </tr></thead>
            <tbody>{linhas_nf}</tbody>
          </table>

          {(_bloco_despesas(dados) if dados.get('despesas') else "")}

          <p style="margin:22px 0 0;font-size:12px;color:{GRAY};line-height:1.6;">
            Os PDFs (DANFSe) seguem <b style="color:{DARK};">em anexo</b> e também por <b style="color:{AMBER};">link no Drive</b> em cada nota.
            Relatório gerado automaticamente pelo LexOps.
          </p>
        </td></tr>
        <tr><td style="background:#f9fafb;padding:16px 32px;border-top:1px solid #eee;">
          <p style="margin:0;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#9ca3af;">Pimenta Judice · LexOps</p>
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
    return resp.json().get("id")  # gmail message id


def enviar_relatorio(db: Session, competencia: str | None = None,
                     destinatario_override: str | None = None,
                     parcial: bool = False) -> dict:
    """Monta e envia o relatório do mês indicado (default: mês anterior).

    Se ``parcial=True``, corta o período no dia atual e marca o relatório como parcial.
    """
    from app.models.config_fiscal import ConfigFiscal
    from app.models.relatorio_fiscal_log import RelatorioFiscalLog
    from app.routers.reembolsos import _refresh_if_needed

    if not competencia:
        hoje = datetime.now(tz=BRT).date()
        primeiro = hoje.replace(day=1)
        ant = primeiro - timedelta(days=1)
        competencia = ant.strftime("%Y-%m")

    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
    master = cfg.email_master if cfg else None
    if destinatario_override:
        destinatarios = [destinatario_override]
    else:
        destinatarios = list(cfg.emails_contador) if cfg and cfg.emails_contador else []
        if not destinatarios and not master:
            return {"enviado": False, "motivo": "Sem e-mails configurados (contador/master)."}
        if not destinatarios and master:
            destinatarios = [master]
            master = None

    dados = coletar_dados(db, competencia, parcial=parcial)

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
    msg_id = _enviar(token, destinatarios, master,
                     f"Relatório Fiscal {mes_label} — Pimenta Judice",
                     _html(dados), anexos)

    # Link da pasta no Drive (Fiscal/NFe/Mês_Ano)
    pasta_link = None
    try:
        from app.services.google_drive import link_subpasta
        ano, mes = competencia[:4], int(competencia[5:7])
        from app.services.nfse.emitter import _MESES_PT
        pasta_link = link_subpasta("Fiscal", "NFe", f"{_MESES_PT[mes-1]}_{ano}")
    except Exception:
        pass

    # Registra no histórico
    log_row = RelatorioFiscalLog(
        competencia=competencia, destinatarios=destinatarios, cc=master,
        nf_qtd=dados["nf_qtd"], anexos=len(anexos),
        gmail_message_id=msg_id, drive_pasta_link=pasta_link, status="enviado",
    )
    db.add(log_row)
    db.commit()

    return {
        "enviado": True, "competencia": competencia,
        "destinatarios": destinatarios, "cc": master,
        "nf_qtd": dados["nf_qtd"], "anexos": len(anexos),
        "gmail_message_id": msg_id,
    }
