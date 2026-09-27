"""Notifica o CLIENTE via WhatsApp quando há andamento novo no processo dele.

Espelha app.services.andamentos_push (Telegram interno), mas:
  - só processa Processo.notificar_whatsapp=True (opt-in explícito do cliente);
  - exige Cliente.whatsapp preenchido;
  - envia por template aprovado (categoria Utility) — mensagem iniciada pelo
    escritório, fora de qualquer janela de 24h;
  - marca AndamentoProcesso.notificado_whatsapp=True (flag própria, não mexe
    no `notificado` do Telegram).

Template esperado no WhatsApp Manager (nome configurável abaixo), com 3
variáveis de corpo: {{1}} nome do cliente, {{2}} número CNJ, {{3}} resumo do
andamento mais recente.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.config import settings
from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.cliente import Cliente
from app.models.processo import Processo
from app.services import whatsapp_api

logger = logging.getLogger(__name__)

TEMPLATE_ANDAMENTO_NOVO = "andamento_novo"
# Andamento com data mais antiga que isso é considerado histórico retroativo —
# marca como notificado sem enviar (mesma lógica do push do Telegram).
_JANELA_DIAS = 14


def push_andamentos_whatsapp() -> dict:
    """Varre processos com notificar_whatsapp=True e manda 1 mensagem por
    processo com andamento novo. Retorna um resumo (enviados, sem_whatsapp,
    erros) para uso no endpoint manual e em logs do scheduler."""
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        logger.warning("push_whatsapp: WHATSAPP_ACCESS_TOKEN/PHONE_NUMBER_ID não configurados — pulando.")
        return {"enviados": 0, "sem_whatsapp": 0, "erros": 0, "motivo": "não configurado"}

    cutoff_data = date.today() - timedelta(days=_JANELA_DIAS)
    enviados = 0
    sem_whatsapp = 0
    erros = 0

    db = SessionLocal()
    try:
        procs = (
            db.query(Processo, Cliente)
            .join(Cliente, Cliente.id == Processo.cliente_id)
            .filter(Processo.notificar_whatsapp.is_(True))
            .filter(Processo.status == "ativo")
            .all()
        )
        for p, cliente in procs:
            novos = (
                db.query(AndamentoProcesso)
                .filter(AndamentoProcesso.processo_id == p.id)
                .filter(AndamentoProcesso.notificado_whatsapp.is_(False))
                .filter(AndamentoProcesso.data_andamento >= cutoff_data)
                .order_by(AndamentoProcesso.data_andamento.desc().nullslast())
                .all()
            )
            # Histórico antigo: marca silenciosamente, não reenvia amanhã.
            antigos_ids = [
                x[0] for x in db.query(AndamentoProcesso.id)
                .filter(AndamentoProcesso.processo_id == p.id)
                .filter(AndamentoProcesso.notificado_whatsapp.is_(False))
                .filter(AndamentoProcesso.data_andamento < cutoff_data)
                .all()
            ]
            if antigos_ids:
                db.query(AndamentoProcesso).filter(AndamentoProcesso.id.in_(antigos_ids)).update(
                    {AndamentoProcesso.notificado_whatsapp: True}, synchronize_session=False
                )
                db.commit()

            if not novos:
                continue

            if not cliente.whatsapp:
                sem_whatsapp += 1
                logger.info(
                    "push_whatsapp: %s tem %d andamento(s) novo(s) mas cliente sem número WhatsApp cadastrado.",
                    p.numero_cnj, len(novos),
                )
                continue

            mais_recente = novos[0]
            resumo = (mais_recente.descricao or "").strip()[:200]
            data_fmt = mais_recente.data_andamento.strftime("%d/%m/%Y") if mais_recente.data_andamento else "—"
            texto_resumo = f"{data_fmt} — {resumo}" if len(novos) == 1 else f"{len(novos)} atualizações, a mais recente em {data_fmt}: {resumo}"

            resultado = whatsapp_api.send_template_message(
                to=cliente.whatsapp,
                template_name=TEMPLATE_ANDAMENTO_NOVO,
                parametros=[cliente.nome, p.numero_cnj, texto_resumo],
            )
            if not resultado or resultado.get("erro"):
                erros += 1
                logger.warning("push_whatsapp: falha ao notificar %s (%s): %s", cliente.nome, p.numero_cnj, resultado)
                continue

            enviados += 1
            ids = [a.id for a in novos]
            db.query(AndamentoProcesso).filter(AndamentoProcesso.id.in_(ids)).update(
                {AndamentoProcesso.notificado_whatsapp: True}, synchronize_session=False
            )
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("push_whatsapp: erro inesperado")
        erros += 1
    finally:
        db.close()

    logger.info(
        "push_whatsapp: concluído — %d enviado(s), %d sem WhatsApp cadastrado, %d erro(s).",
        enviados, sem_whatsapp, erros,
    )
    return {"enviados": enviados, "sem_whatsapp": sem_whatsapp, "erros": erros}
