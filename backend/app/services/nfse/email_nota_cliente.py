"""Envia a NFS-e (DANFSe PDF) por e-mail ao tomador, com cópia para a conta master."""
from __future__ import annotations

import base64
import json
import logging

import httpx

log = logging.getLogger(__name__)

TEAL = "#00b090"
DARK = "#1f2937"
GRAY = "#6b7280"


def _html(nf, prestador_nome: str) -> str:
    valor = f"R$ {float(nf.valor_servicos):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    num = nf.numero_nfse or "—"
    comp = nf.competencia
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#f3f4f6;">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:560px;background:#fff;border-radius:16px;border:1px solid #e5e7eb;overflow:hidden;">
        <tr><td style="background:#ecfdf5;padding:22px 32px;border-bottom:3px solid {TEAL};">
          <p style="margin:0;font-size:14px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:{TEAL};">NOTA FISCAL DE SERVIÇO</p>
          <p style="margin:3px 0 0;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:{GRAY};">{prestador_nome}</p>
        </td></tr>
        <tr><td style="padding:28px 32px;">
          <p style="margin:0 0 16px;font-size:14px;color:{DARK};line-height:1.6;">
            Olá{(' ' + nf.tomador_nome) if nf.tomador_nome else ''}, segue a sua Nota Fiscal de Serviço eletrônica (NFS-e).
          </p>
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                 style="background:#f9fafb;border:1px solid #eee;border-radius:10px;margin-bottom:18px;">
            <tr><td style="padding:14px 18px;font-size:13px;color:{DARK};line-height:1.9;">
              <b>Número:</b> {num}<br/>
              <b>Competência:</b> {comp}<br/>
              <b>Valor:</b> {valor}<br/>
              <b>Chave de acesso:</b> <span style="font-size:11px;word-break:break-all;">{nf.chave_acesso or '—'}</span>
            </td></tr>
          </table>
          <p style="margin:0 0 8px;font-size:13px;color:{DARK};"><b>Pagamento</b></p>
          <p style="margin:0 0 16px;font-size:13px;color:{GRAY};line-height:1.7;">
            PIX (chave CNPJ): <b style="color:{DARK};">10.901.611/0001-64</b><br/>
            TED: Banco Inter (077) · Ag 0001 · CC 1812719-3
          </p>
          <p style="margin:0;font-size:12px;color:{GRAY};line-height:1.6;">
            O PDF (DANFSe) segue em anexo. Autenticidade em
            <a href="https://www.nfse.gov.br/consultapublica" style="color:{TEAL};">nfse.gov.br/consultapublica</a>.
          </p>
        </td></tr>
        <tr><td style="background:#f9fafb;padding:16px 32px;border-top:1px solid #eee;">
          <p style="margin:0;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#9ca3af;">{prestador_nome}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def enviar_nf_ao_cliente(nf, pdf: bytes, master_email: str | None,
                         prestador_nome: str = "Pimenta Judice Advogados") -> bool:
    """Envia a NFS-e ao e-mail do tomador (cc master). Requer Gmail master autenticado."""
    if not nf.tomador_email:
        return False
    from app.routers.reembolsos import _refresh_if_needed
    token = _refresh_if_needed()
    if not token:
        log.warning("NF e-mail cliente: master Google não autenticado")
        return False

    import email.mime.application as mime_app
    import email.mime.multipart as mime_multi
    import email.mime.text as mime_text

    outer = mime_multi.MIMEMultipart("mixed")
    outer["to"] = nf.tomador_email
    outer["from"] = "me"
    outer["subject"] = f"NFS-e nº {nf.numero_nfse or ''} — {prestador_nome}"
    if master_email:
        outer["cc"] = master_email
    alt = mime_multi.MIMEMultipart("alternative")
    alt.attach(mime_text.MIMEText(_html(nf, prestador_nome), "html", "utf-8"))
    outer.attach(alt)
    a = mime_app.MIMEApplication(pdf, _subtype="pdf")
    a.add_header("Content-Disposition", "attachment",
                 filename=f"NFSe_{nf.numero_nfse or nf.chave_acesso}.pdf")
    outer.attach(a)

    raw = base64.urlsafe_b64encode(outer.as_bytes()).decode()
    resp = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        content=json.dumps({"raw": raw}), timeout=60,
    )
    if resp.status_code not in (200, 201):
        log.warning("NF e-mail cliente falhou: %s %s", resp.status_code, resp.text[:200])
        return False
    return True