"""E-mail de aviso de novos destaques do Informativo STJ.

Mesmo estilo visual (teal, cartão branco, tabela de detalhes) do aviso de
lembretes de prazo em app/services/prazo_lembretes.py.
"""

from __future__ import annotations

import html

from app.config import settings
from app.models.informativo_stj import InformativoStjEdicao, InformativoStjItem

DESTINATARIO = "lucasjudice@gmail.com"


def _linha_item(item: InformativoStjItem) -> str:
    frontend = (settings.frontend_url or "").rstrip("/")
    link = f"{frontend}/informativo-stj/{item.edicao_id}" if frontend else "#"
    resumo = item.resumo_tema_central or item.destaque_oficial
    return f"""
    <div style="border-left:3px solid #0d9488;padding:10px 14px;margin-bottom:10px;background:#f0fdfa">
      <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:#0d9488;letter-spacing:.04em">
        {html.escape(item.ramo_direito)}
      </div>
      <div style="font-size:14px;font-weight:600;color:#111827;margin-top:2px">{html.escape(item.titulo)}</div>
      <div style="font-size:13px;color:#374151;margin-top:4px;line-height:1.5">{html.escape(resumo or '')}</div>
      <a href="{html.escape(link)}" style="font-size:12px;color:#0d9488">Abrir no sistema →</a>
    </div>
    """


def corpo_html(edicao: InformativoStjEdicao, itens_destacados: list[InformativoStjItem]) -> str:
    itens_html = "".join(_linha_item(i) for i in itens_destacados)
    frontend = (settings.frontend_url or "").rstrip("/")
    link_edicao = f"{frontend}/informativo-stj/{edicao.id}" if frontend else "#"

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8" /></head>
<body style="margin:0;padding:24px;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
  <div style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:10px;padding:24px">
    <div style="border-left:4px solid #0d9488;padding-left:12px;margin-bottom:20px">
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#0d9488;font-weight:700">
        Informativo STJ nº {edicao.numero}
      </div>
      <div style="font-size:20px;font-weight:700;color:#111827;margin-top:4px">
        {len(itens_destacados)} julgado(s) destacado(s) nesta edição
      </div>
      {f'<div style="font-size:14px;color:#374151;margin-top:6px;line-height:1.5">{html.escape(edicao.resumo_edicao)}</div>' if edicao.resumo_edicao else ''}
    </div>

    {itens_html}

    <p style="margin-top:24px">
      <a href="{html.escape(link_edicao)}" style="background:#0d9488;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:600">
        Abrir edição completa
      </a>
    </p>
  </div>
</body></html>"""


def enviar_email_destaques(edicao: InformativoStjEdicao, itens_destacados: list[InformativoStjItem]) -> None:
    if not itens_destacados:
        return
    from app.services.email_service import _send_via_gmail_oauth

    assunto = f"Informativo STJ nº {edicao.numero} — {len(itens_destacados)} destaque(s)"
    html_msg = corpo_html(edicao, itens_destacados)
    _send_via_gmail_oauth(DESTINATARIO, assunto, html_msg)
