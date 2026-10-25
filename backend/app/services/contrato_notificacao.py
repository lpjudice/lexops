"""Aviso aos responsáveis de um contrato/procuração — e-mail + Telegram (DM).

Conteúdo: título, tipo, cliente, escopo/recomendações, quem são os responsáveis e
um botão pra pasta raiz do cliente no Drive. NUNCA inclui dado financeiro
(honorários, parcelas, valores) — de propósito, esse aviso circula pra equipe
operacional e não deve expor isso.

Falha de um canal/pessoa não derruba os outros: cada envio é independente e o
resultado de cada um volta no retorno (usado pela tela e pelo log).
"""
from __future__ import annotations

import html
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.contrato import Contrato
from app.models.responsavel import Responsavel
from app.services import telegram_api
from app.services.email_service import TEAL, _logo_data_uri, _send_via_gmail_oauth

logger = logging.getLogger(__name__)

# Rótulos com concordância de gênero ("Novo contrato" / "Nova procuração").
_NOVO = {"contrato": "Novo contrato", "procuracao": "Nova procuração"}
_TIPO = {"contrato": "Contrato", "procuracao": "Procuração"}

# Teto de texto livre no Telegram (limite do Telegram é 4096 por mensagem).
_TELEGRAM_ESCOPO_MAX = 2500


def listar_responsaveis(db: Session, contrato: Contrato) -> list[Responsavel]:
    """Responsáveis ativos do contrato, na ordem em que foram escolhidos. Ids
    inválidos/de responsável removido ou inativo são ignorados."""
    ordem: list[str] = []
    for bruto in contrato.responsaveis_ids or []:
        try:
            ordem.append(str(uuid.UUID(str(bruto))))
        except ValueError:
            continue
    if not ordem:
        return []
    rows = (
        db.query(Responsavel)
        .filter(Responsavel.id.in_([uuid.UUID(i) for i in ordem]), Responsavel.ativo.is_(True))
        .all()
    )
    por_id = {str(r.id): r for r in rows}
    return [por_id[i] for i in ordem if i in por_id]


def _link_pasta_cliente(cliente: Cliente) -> str | None:
    try:
        from app.services.google_drive import ensure_cliente_folder
        return ensure_cliente_folder(cliente.nome)
    except Exception as exc:
        logger.warning("Aviso responsáveis: sem link da pasta do cliente %s: %s", cliente.nome, exc)
        return None


def _html_texto(s: str) -> str:
    return html.escape(s).replace("\n", "<br/>")


def build_aviso_html(
    *, tipo: str, titulo: str, cliente_nome: str, escopo: str | None,
    responsaveis_nomes: list[str], link_pasta: str | None,
) -> str:
    logo = _logo_data_uri("logo_light.png")
    logo_img = (
        f'<img src="{logo}" width="130" alt="Pimenta Judice Advogados" style="display:block;"/>'
        if logo else
        '<p style="margin:0;font-size:13px;font-weight:800;letter-spacing:0.14em;'
        'text-transform:uppercase;color:#ffffff;">PIMENTA JUDICE ADVOGADOS</p>'
    )
    escopo_box = ""
    if escopo and escopo.strip():
        escopo_box = f"""
          <p style="margin:22px 0 6px;font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;color:#6b7280;">Escopo e recomendações</p>
          <table cellpadding="0" cellspacing="0" role="presentation" width="100%">
            <tr><td style="border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;background:#fafafa;">
              <p style="margin:0;font-size:14px;color:#374151;line-height:1.7;">{_html_texto(escopo.strip())}</p>
            </td></tr>
          </table>"""
    pasta_btn = ""
    if link_pasta:
        pasta_btn = f"""
          <table cellpadding="0" cellspacing="0" role="presentation" style="margin:26px 0 4px;">
            <tr><td style="background:{TEAL};border-radius:8px;">
              <a href="{html.escape(link_pasta, quote=True)}" style="display:inline-block;padding:12px 22px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;">📁 Abrir pasta do cliente</a>
            </td></tr>
          </table>"""
    resp_txt = ", ".join(html.escape(n) for n in responsaveis_nomes) or "—"
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{html.escape(_NOVO.get(tipo, "Novo documento"))} — Pimenta Judice</title></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#f5f5f5;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <tr><td style="background:#141414;padding:26px 36px;">{logo_img}</td></tr>
        <tr><td style="padding:28px 36px 8px;">
          <p style="margin:0 0 14px;">
            <span style="display:inline-block;background:#d1fae5;color:#065f46;font-size:11px;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;padding:5px 11px;border-radius:999px;">{html.escape(_NOVO.get(tipo, "Novo documento"))}</span>
          </p>
          <h1 style="margin:0 0 6px;font-size:20px;font-weight:700;color:#111827;line-height:1.3;">{html.escape(titulo)}</h1>
          <p style="margin:0 0 4px;font-size:14px;color:#374151;"><b>Cliente:</b> {html.escape(cliente_nome)}</p>
          <p style="margin:0;font-size:14px;color:#374151;"><b>Responsáveis:</b> {resp_txt}</p>
          {escopo_box}
          {pasta_btn}
        </td></tr>
        <tr><td style="padding:20px 36px 28px;border-top:1px solid #f3f4f6;">
          <p style="margin:0;font-size:11px;color:#9ca3af;line-height:1.6;text-align:center;">Mensagem automática — Pimenta Judice Advogados</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def build_aviso_telegram(
    *, tipo: str, titulo: str, cliente_nome: str, escopo: str | None,
    responsaveis_nomes: list[str],
) -> str:
    esc = html.escape
    linhas = [
        f"🆕 <b>{esc(_NOVO.get(tipo, 'Novo documento'))}</b>",
        f"<b>{esc(titulo)}</b>",
        f"Cliente: {esc(cliente_nome)}",
        f"Responsáveis: {esc(', '.join(responsaveis_nomes) or '—')}",
    ]
    if escopo and escopo.strip():
        texto = escopo.strip()
        if len(texto) > _TELEGRAM_ESCOPO_MAX:
            texto = texto[:_TELEGRAM_ESCOPO_MAX].rstrip() + "…"
        linhas += ["", "<b>Escopo e recomendações</b>", esc(texto)]
    return "\n".join(linhas)


def notificar_responsaveis(db: Session, contrato: Contrato) -> list[dict]:
    """Envia o aviso a cada responsável do contrato (e-mail e, se vinculado,
    Telegram). Retorna um item por pessoa: {"responsavel", "email", "telegram"}
    com o status de cada canal. Marca `responsaveis_notificados_em` se ao menos
    um envio deu certo."""
    responsaveis = listar_responsaveis(db, contrato)
    if not responsaveis:
        return []

    cliente = db.query(Cliente).filter(Cliente.id == contrato.cliente_id).first()
    cliente_nome = cliente.nome if cliente else "—"
    link_pasta = _link_pasta_cliente(cliente) if cliente else None
    nomes = [r.nome for r in responsaveis]
    tipo = contrato.tipo_documento or "contrato"

    assunto = f"{_NOVO.get(tipo, 'Novo documento')}: {contrato.titulo} — {cliente_nome}"
    corpo_html = build_aviso_html(
        tipo=tipo, titulo=contrato.titulo, cliente_nome=cliente_nome,
        escopo=contrato.escopo_recomendacoes, responsaveis_nomes=nomes, link_pasta=link_pasta,
    )
    corpo_tg = build_aviso_telegram(
        tipo=tipo, titulo=contrato.titulo, cliente_nome=cliente_nome,
        escopo=contrato.escopo_recomendacoes, responsaveis_nomes=nomes,
    )

    resultados: list[dict] = []
    algum_ok = False
    chats_ja_avisados: set[str] = set()  # mesma pessoa com dois cadastros no mesmo chat: uma DM só
    for r in responsaveis:
        res = {"responsavel": r.nome, "email": "sem_email", "telegram": "nao_vinculado"}
        if r.email:
            try:
                _send_via_gmail_oauth(r.email, assunto, corpo_html)
                res["email"] = "enviado"
                algum_ok = True
            except Exception as exc:
                logger.warning("Aviso responsáveis: e-mail pra %s falhou: %s", r.email, exc)
                res["email"] = f"erro: {exc}"
        if r.telegram_chat_id and r.telegram_chat_id in chats_ja_avisados:
            res["telegram"] = "mesmo_chat"
        elif r.telegram_chat_id:
            chats_ja_avisados.add(r.telegram_chat_id)
            botao = ("📁 Pasta do cliente", link_pasta) if link_pasta else None
            if telegram_api.send_message_html(r.telegram_chat_id, corpo_tg, botao):
                res["telegram"] = "enviado"
                algum_ok = True
            else:
                res["telegram"] = "falhou"
        resultados.append(res)

    if algum_ok:
        contrato.responsaveis_notificados_em = datetime.now(timezone.utc)
        db.commit()
    return resultados


def notificar_em_background(contrato_id: uuid.UUID) -> None:
    """Para BackgroundTasks: abre a própria sessão (a da request já fechou)."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        contrato = db.query(Contrato).filter(Contrato.id == contrato_id).first()
        if contrato:
            notificar_responsaveis(db, contrato)
    except Exception:
        logger.exception("Aviso responsáveis: falha inesperada no contrato %s", contrato_id)
    finally:
        db.close()
