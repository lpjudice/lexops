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

logger = logging.getLogger(__name__)

TEAL = "#00b090"
TEAL_DARK = "#007a62"


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
    to_email: str, subject: str, html: str, cc: list[str] | None = None
) -> None:
    """Send using the same stored Google OAuth tokens as the reembolsos flow."""
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

    msg = mime_multi.MIMEMultipart("alternative")
    msg["to"] = to_email
    if cc:
        msg["cc"] = ", ".join(cc)
    msg["from"] = "me"
    msg["subject"] = subject
    msg.attach(mime_text.MIMEText(html, "html", "utf-8"))

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
