"""
Email service — magic link invites for Gestor Jurídico.

Uses the same Gmail OAuth tokens already stored for the reembolsos flow.
Falls back to console print if Google is not authenticated.
"""
from __future__ import annotations

import base64
import email.mime.multipart as mime_multi
import email.mime.text as mime_text
import logging
import pathlib

logger = logging.getLogger(__name__)

TEAL = "#00b090"
TEAL_DARK = "#007a62"

_ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"
_LOGO_CACHE: dict[str, str] = {}


def _logo_data_uri(nome: str = "logo_light.png") -> str:
    """Logo (letras claras, fundo transparente) como data-URI base64, para usar
    em faixas coloridas de e-mail — mesmo padrão do brinde_instagram."""
    if nome not in _LOGO_CACHE:
        try:
            data = (_ASSETS / nome).read_bytes()
            _LOGO_CACHE[nome] = "data:image/png;base64," + base64.b64encode(data).decode()
        except Exception:
            _LOGO_CACHE[nome] = ""
    return _LOGO_CACHE[nome]


def _build_invite_html(invite_url: str, inviter_name: str, to_email: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Convite — Pimenta Judice</title>
</head>
<body style="margin:0;padding:0;background:#111111;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#111111;min-height:100vh;">
    <tr>
      <td align="center" style="padding:48px 16px;">

        <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
               style="max-width:480px;background:#1a1a1a;border-radius:16px;border:1px solid #2a2a2a;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:#141414;padding:24px 32px;border-bottom:1px solid #2a2a2a;">
              <p style="margin:0;font-size:13px;font-weight:800;letter-spacing:0.14em;
                         text-transform:uppercase;color:#f5f5f5;">PIMENTA JUDICE</p>
              <p style="margin:2px 0 0;font-size:10px;letter-spacing:0.12em;
                         text-transform:uppercase;color:#555;">Advogados</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 32px 28px;">
              <h1 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#f5f5f5;line-height:1.3;">
                Você foi convidado
              </h1>
              <p style="margin:0 0 28px;font-size:14px;color:#888;line-height:1.6;">
                <strong style="color:#d4d4d4;">{inviter_name}</strong> convidou você para acessar o
                <strong style="color:#d4d4d4;">Gestor Jurídico</strong> do escritório
                Pimenta Judice Advogados.
              </p>

              <!-- CTA button -->
              <table cellpadding="0" cellspacing="0" role="presentation" style="margin-bottom:28px;">
                <tr>
                  <td style="border-radius:10px;background:{TEAL};">
                    <a href="{invite_url}"
                       style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:700;
                              color:#ffffff;text-decoration:none;border-radius:10px;
                              letter-spacing:0.01em;">
                      Definir senha e ativar conta →
                    </a>
                  </td>
                </tr>
              </table>

              <!-- What you'll access -->
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                     style="background:#141414;border-radius:10px;border:1px solid #2a2a2a;
                            margin-bottom:28px;">
                <tr>
                  <td style="padding:18px 20px;">
                    <p style="margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:0.08em;
                               text-transform:uppercase;color:#666;">
                      O que você vai acessar
                    </p>
                    <table cellpadding="0" cellspacing="0" role="presentation">
                      <tr><td style="padding:4px 0;font-size:13px;color:#aaa;line-height:1.5;">✦&nbsp; Gestão de clientes e processos</td></tr>
                      <tr><td style="padding:4px 0;font-size:13px;color:#aaa;line-height:1.5;">✦&nbsp; Prazos, tarefas e atendimentos</td></tr>
                      <tr><td style="padding:4px 0;font-size:13px;color:#aaa;line-height:1.5;">✦&nbsp; Diário Oficial e teses com IA</td></tr>
                      <tr><td style="padding:4px 0;font-size:13px;color:#aaa;line-height:1.5;">✦&nbsp; Integração com Gmail e Google Calendar</td></tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Google note -->
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                     style="background:#0a1f1c;border-radius:10px;border:1px solid #1a3a33;
                            margin-bottom:28px;">
                <tr>
                  <td style="padding:14px 18px;">
                    <p style="margin:0;font-size:13px;color:#6ee7b7;line-height:1.5;">
                      <strong>Importante:</strong> após ativar sua conta, conecte sua conta Google
                      <strong>@pimentajudice.com.br</strong> para habilitar Gmail e Calendar.
                    </p>
                  </td>
                </tr>
              </table>

              <!-- Fallback link -->
              <p style="margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:0.06em;
                         text-transform:uppercase;color:#555;">
                Ou copie este link
              </p>
              <p style="margin:0;font-size:11px;color:#555;word-break:break-all;line-height:1.6;
                         background:#141414;padding:10px 12px;border-radius:8px;
                         border:1px solid #2a2a2a;font-family:'Courier New',monospace;">
                {invite_url}
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px 28px;border-top:1px solid #2a2a2a;">
              <p style="margin:0;font-size:11px;color:#444;line-height:1.6;text-align:center;">
                Este link expira em <strong style="color:#666;">48 horas</strong>
                e pode ser usado apenas uma vez.<br/>
                Enviado para <strong style="color:#666;">{to_email}</strong>.
                Se você não esperava este convite, pode ignorá-lo.
              </p>
            </td>
          </tr>

        </table>

        <p style="margin:20px 0 0;font-size:11px;color:#444;text-align:center;">
          Pimenta Judice Advogados &mdash; Gestor Jurídico
        </p>

      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_via_gmail_oauth(
    to_email: str, subject: str, html: str, cc: list[str] | None = None,
    attachments: list[tuple[str, bytes]] | None = None,
) -> None:
    """Send using the same stored Google OAuth tokens as the reembolsos flow.

    `attachments`: lista de (nome_do_arquivo, conteúdo_pdf_bytes). Quando presente,
    o e-mail vira multipart/mixed com os PDFs anexados.
    """
    import httpx
    from app.services.google_calendar import _load_tokens, _refresh_token

    tokens = _load_tokens()
    if not tokens:
        raise RuntimeError("Google não autenticado — faça OAuth em /auth/google primeiro")

    try:
        refreshed = _refresh_token(tokens)
        access_token = refreshed.get("access_token")
    except Exception:
        access_token = tokens.get("access_token")

    if not access_token:
        raise RuntimeError("Não foi possível obter access_token do Google")

    corpo = mime_multi.MIMEMultipart("alternative")
    corpo.attach(mime_text.MIMEText(html, "html", "utf-8"))

    if attachments:
        from email.mime.application import MIMEApplication
        msg = mime_multi.MIMEMultipart("mixed")
        msg.attach(corpo)
        for nome, conteudo in attachments:
            parte = MIMEApplication(conteudo, _subtype="pdf")
            parte.add_header("Content-Disposition", "attachment", filename=nome)
            msg.attach(parte)
    else:
        msg = corpo

    msg["to"] = to_email
    if cc:
        msg["cc"] = ", ".join(cc)
    msg["from"] = "me"
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    resp = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        content=__import__("json").dumps({"raw": raw}),
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Gmail API retornou {resp.status_code}: {resp.text}")


def _build_cadastro_html(cadastro_url: str, nome: str | None, is_update: bool) -> str:
    saudacao = f"Olá{(' ' + nome) if nome else ''},"
    intro = (
        "Para mantermos seu cadastro atualizado, preencha ou confira seus dados "
        "no formulário seguro abaixo."
        if is_update else
        "Para darmos início ao seu atendimento, preencha seus dados no formulário "
        "seguro abaixo."
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Cadastro — Pimenta Judice</title></head>
<body style="margin:0;padding:0;background:#111111;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#111111;">
    <tr><td align="center" style="padding:48px 16px;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:480px;background:#1a1a1a;border-radius:16px;border:1px solid #2a2a2a;overflow:hidden;">
        <tr><td style="background:#141414;padding:24px 32px;border-bottom:1px solid #2a2a2a;">
          <p style="margin:0;font-size:13px;font-weight:800;letter-spacing:0.14em;text-transform:uppercase;color:#f5f5f5;">PIMENTA JUDICE</p>
          <p style="margin:2px 0 0;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#555;">Advogados</p>
        </td></tr>
        <tr><td style="padding:36px 32px 28px;">
          <h1 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#f5f5f5;line-height:1.3;">{saudacao}</h1>
          <p style="margin:0 0 28px;font-size:14px;color:#888;line-height:1.6;">{intro}</p>
          <table cellpadding="0" cellspacing="0" role="presentation" style="margin-bottom:28px;">
            <tr><td style="border-radius:10px;background:{TEAL};">
              <a href="{cadastro_url}" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px;">
                {"Atualizar meus dados" if is_update else "Preencher meu cadastro"} →
              </a>
            </td></tr>
          </table>
          <p style="margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:#8a8a8a;">Ou copie este link</p>
          <p style="margin:0;font-size:12px;word-break:break-all;line-height:1.6;background:#141414;padding:10px 12px;border-radius:8px;border:1px solid #2a2a2a;font-family:'Courier New',monospace;">
            <a href="{cadastro_url}" style="color:#5eead4;text-decoration:underline;">{cadastro_url}</a>
          </p>
        </td></tr>
        <tr><td style="padding:20px 32px 28px;border-top:1px solid #2a2a2a;">
          <p style="margin:0;font-size:11px;color:#444;line-height:1.6;text-align:center;">
            Seus dados são tratados conforme a LGPD (Lei nº 13.709/2018).<br/>
            Se você não esperava este e-mail, pode ignorá-lo.
          </p>
        </td></tr>
      </table>
      <p style="margin:20px 0 0;font-size:11px;color:#444;text-align:center;">Pimenta Judice Advogados</p>
    </td></tr>
  </table>
</body></html>"""


def build_cobranca_html(
    *, nome: str, descricao: str, parcela_numero: int, parcela_valor: str,
    parcela_venc: str, valor_total: str, n_parcelas_total: int, n_parcelas_pend: int,
    pos_vencimento: bool, pagamento: dict | None = None,
) -> str:
    """
    Lembrete de parcela — mesmo padrão visual dos outros e-mails automáticos
    (fundo claro, card branco, faixa escura no topo com a logo). Tom amigável,
    não de cobrança. `pos_vencimento`=True muda o texto para o lembrete único
    enviado alguns dias após o vencimento. O destaque (chip) mostra o valor da
    parcela que está vencendo agora; abaixo, o contexto do total dos honorários.
    `pagamento`: {"pix_chave", "pix_tipo", "favorecido", "contato"} — mostrados
    também no corpo do e-mail (além do PDF em anexo).
    """
    logo = _logo_data_uri("logo_light.png")
    logo_img = (
        f'<img src="{logo}" width="130" alt="Pimenta Judice Advogados" style="display:block;"/>'
        if logo else
        '<p style="margin:0;font-size:13px;font-weight:800;letter-spacing:0.14em;'
        'text-transform:uppercase;color:#ffffff;">PIMENTA JUDICE ADVOGADOS</p>'
    )
    saud = f"Olá{(' ' + nome) if nome else ''},"
    if pos_vencimento:
        corpo = (
            f"Notamos que a parcela {parcela_numero} de <b>{descricao}</b>, com vencimento "
            f"em <b>{parcela_venc}</b>, ainda não consta como paga em nosso sistema. Se você "
            f"já efetuou o pagamento, por favor desconsidere — e, se puder, nos envie o "
            f"comprovante para darmos baixa. Caso ainda não, os dados para pagamento estão "
            f"no PDF em anexo."
        )
    else:
        corpo = (
            f"Passando só para lembrar que a parcela {parcela_numero} referente a "
            f"<b>{descricao}</b> vence em <b>{parcela_venc}</b>. Em anexo segue um resumo "
            f"com o cronograma e os dados para pagamento (PIX)."
        )
    rotulo_data = "Venceu em" if pos_vencimento else "Vence em"
    plano_txt = f"Valor total dos honorários: <b style=\"color:#374151\">{valor_total}</b>" + (
        f" · {n_parcelas_total} parcelas, {n_parcelas_pend} em aberto"
        if n_parcelas_total > 1 else "")

    pagamento_box = ""
    tem_contato = pagamento and (
        pagamento.get("contato_nome") or pagamento.get("contato_email") or pagamento.get("contato_whatsapp")
    )
    if pagamento and (pagamento.get("pix_chave") or tem_contato):
        linhas = []
        if pagamento.get("pix_chave"):
            tipo = pagamento.get("pix_tipo")
            linhas.append(f"<b>PIX{(' (' + tipo + ')') if tipo else ''}:</b> {pagamento['pix_chave']}")
        if pagamento.get("favorecido"):
            linhas.append(f"<b>Favorecido:</b> {pagamento['favorecido']}")
        if tem_contato:
            contato_linhas = []
            if pagamento.get("contato_nome"):
                contato_linhas.append(pagamento["contato_nome"])
            if pagamento.get("contato_email"):
                contato_linhas.append(pagamento["contato_email"])
            if pagamento.get("contato_whatsapp"):
                wa_url = f"https://wa.me/{pagamento['contato_whatsapp']}"
                wa_disp = pagamento.get("contato_whatsapp_fmt") or pagamento["contato_whatsapp"]
                contato_linhas.append(
                    f'WhatsApp: <a href="{wa_url}" style="color:#2563eb;text-decoration:underline;">{wa_disp}</a>'
                )
            linhas.append("<b>Contato:</b><br/>" + "<br/>".join(contato_linhas))
        linhas_html = "<br/>".join(linhas)
        pagamento_box = f"""
          <table cellpadding="0" cellspacing="0" role="presentation" width="100%" style="margin-bottom:20px;">
            <tr><td style="border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;background:#fafafa;">
              <p style="margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;color:#6b7280;">Como pagar</p>
              <p style="margin:0;font-size:13px;color:#374151;line-height:1.7;">{linhas_html}</p>
            </td></tr>
          </table>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Lembrete — Pimenta Judice</title></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#f5f5f5;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <tr><td style="background:#141414;padding:26px 36px;">
          {logo_img}
        </td></tr>
        <tr><td style="padding:28px 36px 8px;">
          <p style="margin:0 0 18px;">
            <span style="display:inline-block;background:#fef3c7;color:#92400e;font-size:11px;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;padding:5px 11px;border-radius:999px;">Mensagem automática</span>
          </p>
          <h1 style="margin:0 0 10px;font-size:20px;font-weight:700;color:#111827;line-height:1.3;">{saud}</h1>
          <p style="margin:0 0 20px;font-size:14px;color:#374151;line-height:1.65;">{corpo}</p>
          <table cellpadding="0" cellspacing="0" role="presentation" width="100%" style="margin-bottom:10px;">
            <tr><td style="background:{TEAL};border-radius:10px;padding:16px 20px;">
              <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:rgba(255,255,255,0.85);">{rotulo_data} {parcela_venc}</p>
              <p style="margin:4px 0 0;font-size:26px;font-weight:800;color:#ffffff;line-height:1.2;">{parcela_valor}</p>
              {f'<p style="margin:2px 0 0;font-size:12px;color:rgba(255,255,255,0.85);">Parcela {parcela_numero} de {n_parcelas_total}</p>' if n_parcelas_total > 1 else ''}
            </td></tr>
          </table>
          <p style="margin:0 0 16px;font-size:13px;color:#6b7280;line-height:1.6;">{plano_txt}</p>
          {pagamento_box}
        </td></tr>
        <tr><td style="padding:20px 36px 28px;border-top:1px solid #f3f4f6;">
          <p style="margin:0;font-size:11px;color:#9ca3af;line-height:1.6;text-align:center;">Pimenta Judice Advogados</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def send_cadastro_email(
    to_email: str, cadastro_url: str, nome: str | None = None,
    cc: list[str] | None = None, is_update: bool = False,
) -> None:
    """Envia o link de autocadastro com a identidade visual do escritório.

    Levanta exceção em falha (o router traduz em HTTP) — diferente do convite,
    aqui queremos que o usuário saiba se não foi enviado.
    """
    subject = "Atualização de cadastro — Pimenta Judice" if is_update else "Seu cadastro — Pimenta Judice"
    html = _build_cadastro_html(cadastro_url, nome, is_update)
    _send_via_gmail_oauth(to_email, subject, html, cc=cc)


async def send_invite_email(to_email: str, invite_url: str, inviter_name: str) -> bool:
    subject = "Você foi convidado — Gestor Jurídico"
    html = _build_invite_html(invite_url, inviter_name, to_email)

    try:
        _send_via_gmail_oauth(to_email, subject, html)
        logger.info(f"[CONVITE] Email enviado via Gmail OAuth para {to_email}")
        print(f"[CONVITE] Email enviado via Gmail OAuth para {to_email}", flush=True)
        return True
    except Exception as exc:
        logger.warning(f"[CONVITE] Gmail OAuth falhou: {exc}")
        print(
            f"\n{'='*60}\n"
            f"[CONVITE] Gmail não autenticado ou falhou ({exc}).\n"
            f"  Para: {to_email}\n"
            f"  Link: {invite_url}\n"
            f"{'='*60}\n",
            flush=True,
        )
        return False
