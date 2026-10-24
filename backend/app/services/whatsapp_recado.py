"""Repasse de recado do cliente (WhatsApp) à equipe.

Quando o assistente do WhatsApp percebe que o cliente precisa do advogado (análise
jurídica, pedido pra falar com alguém, assunto fora do que ele enxerga, financeiro),
em vez de prometer algo que ninguém cumpre, o sistema AVISA a equipe de verdade:

  - quem recebe: os responsáveis do cliente (campo Cliente.responsaveis_ids; se vazio,
    os responsáveis dos contratos dele) + sempre a cópia obrigatória do escritório;
  - por onde: e-mail SEMPRE; Telegram também, pra quem tiver o Telegram vinculado;
  - fica registrado em `whatsapp_recados`, com o resultado de cada canal.

O assistente só diz ao cliente "passei seu recado" se pelo menos um canal funcionou.
"""
from __future__ import annotations

import html
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.contrato import Contrato
from app.models.responsavel import Responsavel
from app.models.whatsapp_bot import WhatsappRecado

logger = logging.getLogger(__name__)

# Mesma cópia obrigatória dos lembretes de prazo.
COPIA_OBRIGATORIA = "pj@pimentajudice.com.br"
# Evita inundar a equipe se o cliente insistir: acima disso o assistente só avisa que já repassou.
LIMITE_RECADOS_POR_HORA = 3


def recados_na_ultima_hora(db: Session, cliente_id: uuid.UUID) -> int:
    desde = datetime.now(timezone.utc) - timedelta(hours=1)
    return db.query(func.count(WhatsappRecado.id)).filter(
        WhatsappRecado.cliente_id == cliente_id, WhatsappRecado.created_at >= desde
    ).scalar() or 0


def _ids_validos(brutos) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for b in brutos or []:
        try:
            u = uuid.UUID(str(b))
        except ValueError:
            continue
        if u not in ids:
            ids.append(u)
    return ids


def responsaveis_do_cliente(db: Session, cliente: Cliente) -> list[Responsavel]:
    """Responsáveis ativos do cliente (campo próprio primeiro; depois os dos contratos)."""
    ids = _ids_validos(cliente.responsaveis_ids)
    for (rids,) in db.query(Contrato.responsaveis_ids).filter(Contrato.cliente_id == cliente.id).all():
        for u in _ids_validos(rids):
            if u not in ids:
                ids.append(u)
    if not ids:
        return []
    por_id = {r.id: r for r in db.query(Responsavel).filter(Responsavel.id.in_(ids), Responsavel.ativo.is_(True)).all()}
    return [por_id[i] for i in ids if i in por_id]


def _montar(cliente: Cliente, telefone: str, mensagem: str, resumo: str, cnj: str | None) -> tuple[str, str, str]:
    digitos = re.sub(r"\D", "", telefone)
    link_wa = f"https://wa.me/{digitos}"
    linhas_proc = f"Processo citado: {cnj}\n" if cnj else ""
    assunto = f"Recado de cliente pelo WhatsApp: {cliente.nome}"
    corpo_html = (
        f"<p><b>{html.escape(cliente.nome)}</b> mandou uma mensagem pelo WhatsApp do escritório que o assistente "
        "não resolve, e o recado foi repassado a você.</p>"
        f"<p>📱 <a href=\"{link_wa}\">{html.escape(telefone)}</a> (toque para responder pelo WhatsApp)</p>"
        + (f"<p>Processo citado: <b>{html.escape(cnj)}</b></p>" if cnj else "")
        + f"<p><b>Mensagem do cliente:</b></p><blockquote>{html.escape(mensagem)}</blockquote>"
        + (f"<p><b>Resumo do assistente:</b> {html.escape(resumo)}</p>" if resumo else "")
        + "<p style=\"color:#6b7280;font-size:12px\">O assistente informou ao cliente que o recado foi repassado ao advogado responsável.</p>"
    )
    corpo_tg = (
        f"💬 <b>Recado de cliente (WhatsApp)</b>\n<b>{html.escape(cliente.nome)}</b> — {html.escape(telefone)}\n"
        + (f"Processo: {html.escape(cnj)}\n" if cnj else "")
        + f"\n“{html.escape(mensagem[:700])}”\n"
        + (f"\n<i>{html.escape(resumo)}</i>\n" if resumo else "")
        + f"\nResponder: {link_wa}"
    )
    return assunto, corpo_html, corpo_tg


def repassar_recado(
    db: Session, cliente: Cliente, telefone: str, mensagem: str, resumo: str, cnj: str | None = None,
) -> bool:
    """Avisa a equipe. True se ao menos um canal (e-mail ou Telegram) deu certo."""
    from app.services import telegram_api
    from app.services.email_service import _send_via_gmail_oauth

    responsaveis = responsaveis_do_cliente(db, cliente)
    copia = db.query(Responsavel).filter(
        func.lower(Responsavel.email) == COPIA_OBRIGATORIA.lower(), Responsavel.ativo.is_(True)
    ).first()
    pessoas = list(responsaveis)
    if copia and copia.id not in {r.id for r in pessoas}:
        pessoas.append(copia)

    assunto, corpo_html, corpo_tg = _montar(cliente, telefone, mensagem, resumo, cnj)
    resultado: list[dict] = []
    algum_ok = False

    # E-mail: um único envio, para + cc (a cópia obrigatória sempre vai, mesmo sem responsável).
    emails = [r.email.strip().lower() for r in responsaveis if r.email and r.email.strip()]
    emails = list(dict.fromkeys(e for e in emails if e != COPIA_OBRIGATORIA.lower()))
    para = emails[0] if emails else COPIA_OBRIGATORIA
    cc = emails[1:] + ([COPIA_OBRIGATORIA] if emails else [])
    status_email = "enviado"
    try:
        _send_via_gmail_oauth(para, assunto, corpo_html, cc=cc or None)
        algum_ok = True
    except Exception as exc:
        logger.warning("recado WhatsApp: e-mail falhou: %s", exc)
        status_email = f"erro: {str(exc)[:200]}"
    resultado.append({"destinatario": ", ".join([para] + cc), "email": status_email, "telegram": "-"})

    # Telegram: DM pra cada pessoa com o Telegram vinculado.
    for r in pessoas:
        if not r.telegram_chat_id:
            resultado.append({"destinatario": r.nome, "email": "-", "telegram": "nao_vinculado"})
            continue
        try:
            ok = telegram_api.send_message_html(r.telegram_chat_id, corpo_tg)
        except Exception:
            logger.exception("recado WhatsApp: Telegram falhou pra %s", r.nome)
            ok = False
        resultado.append({"destinatario": r.nome, "email": "-", "telegram": "enviado" if ok else "falhou"})
        algum_ok = algum_ok or bool(ok)

    db.add(WhatsappRecado(
        cliente_id=cliente.id, telefone=re.sub(r"\D", "", telefone)[-20:], mensagem=mensagem[:4000],
        resumo=(resumo or None), processo_cnj=cnj, resultado=resultado,
    ))
    db.commit()
    return algum_ok
