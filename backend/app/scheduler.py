"""APScheduler — rotinas automáticas do app em horário de São Paulo."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
DIARIO_TRIBUNAIS_ORDEM = ["DJEN", "TJSP", "TJES", "TJAM", "TJRJ"]
DIARIO_DAYS_BACK = 30
REEMBOLSO_REMINDER_INTERVAL = timedelta(days=3)


def _processos_ativos(db):
    from app.models.processo import Processo

    return (
        db.query(Processo)
        .filter(Processo.status == "ativo")
        .all()
    )


def _sync_all_processos() -> None:
    """Sync andamentos for all active processes using DataJud and, when available, jus.br."""
    try:
        from app.database import SessionLocal
        from app.services.consulta_processual.jusbr_session import load_session
        from app.services.consulta_processual.orchestrator import (
            sincronizar_processo,
            sincronizar_processo_jusbr,
        )

        db = SessionLocal()
        try:
            processos = _processos_ativos(db)
            logger.info("Scheduler: sincronizando %d processos ativos via DataJud", len(processos))
            for p in processos:
                try:
                    asyncio.run(sincronizar_processo(p, db))
                except Exception as exc:
                    logger.warning("Erro DataJud ao sincronizar %s: %s", p.numero_cnj, exc)

            session_data = load_session()
            if session_data:
                logger.info("Scheduler: sessão jus.br ativa, sincronizando %d processos via jus.br", len(processos))
                for p in processos:
                    try:
                        asyncio.run(sincronizar_processo_jusbr(p, db, session_data=session_data))
                    except Exception as exc:
                        logger.warning("Erro jus.br ao sincronizar %s: %s", p.numero_cnj, exc)
            else:
                logger.info("Scheduler: sessão jus.br indisponível, rodada noturna seguirá só com DataJud")
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Erro crítico no scheduler de andamentos: %s", exc)


def _refresh_jusbr_session() -> None:
    try:
        from app.services.consulta_processual.jusbr_session import refresh_session_if_needed

        session_data = refresh_session_if_needed(buffer_minutes=90)
        if session_data:
            logger.info("Scheduler: sessão jus.br verificada/atualizada com sucesso")
        else:
            logger.info("Scheduler: nenhuma sessão jus.br ativa para manter")
    except Exception as exc:
        logger.warning("Scheduler: falha ao renovar sessão jus.br: %s", exc)


def _refresh_google_master_session() -> None:
    try:
        from app.services.google_calendar import _load_tokens, _refresh_token

        tokens = _load_tokens()
        if not tokens:
            logger.info("Scheduler: nenhuma conta Google master conectada para manter")
            return
        if not tokens.get("refresh_token"):
            logger.info("Scheduler: conta Google master sem refresh token disponível")
            return
        _refresh_token(tokens)
        logger.info("Scheduler: conta Google master renovada com sucesso")
    except Exception as exc:
        logger.warning("Scheduler: falha ao renovar conta Google master: %s", exc)


def _renovar_drive_watch() -> None:
    try:
        from app.services.drive_watch import renovar_se_necessario
        renovar_se_necessario()
    except Exception as exc:
        logger.warning("Scheduler: falha ao renovar Drive watch channel: %s", exc)


def _sync_diarios_monitorados() -> None:
    try:
        from app.database import SessionLocal
        from app.routers.diario import (
            _filtrar_itens_monitorados_exatos,
            _inserir_publicacoes,
            _termos_monitorados_para_busca,
        )
        from app.services.scraping_tribunais import scrape_todos

        db = SessionLocal()
        try:
            termos = _termos_monitorados_para_busca(db)
            if not termos:
                logger.info("Scheduler: nenhum termo monitorado para Diário Oficial")
                return

            totais = {"inseridas": 0, "duplicatas": 0, "erros": 0}
            logger.info(
                "Scheduler: sincronizando Diário Oficial (%s) com %d termo(s), janela de %d dia(s)",
                " > ".join(DIARIO_TRIBUNAIS_ORDEM),
                len(termos),
                DIARIO_DAYS_BACK,
            )
            for tribunal in DIARIO_TRIBUNAIS_ORDEM:
                try:
                    itens = scrape_todos(
                        tribunais=[tribunal],
                        termos=termos,
                        days_back=DIARIO_DAYS_BACK,
                    )
                    itens = _filtrar_itens_monitorados_exatos(itens, db, termos)
                    ins, dup, err = _inserir_publicacoes(itens, db)
                    totais["inseridas"] += ins
                    totais["duplicatas"] += dup
                    totais["erros"] += err
                    logger.info(
                        "Scheduler: Diário Oficial %s concluído (%d novas, %d duplicatas, %d erros)",
                        tribunal,
                        ins,
                        dup,
                        err,
                    )
                except Exception as exc:
                    totais["erros"] += 1
                    logger.warning("Scheduler: falha ao sincronizar Diário Oficial %s: %s", tribunal, exc)
            logger.info(
                "Scheduler: Diário Oficial concluído (%d novas, %d duplicatas, %d erros)",
                totais["inseridas"],
                totais["duplicatas"],
                totais["erros"],
            )
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Scheduler: falha na sincronização automática do Diário Oficial: %s", exc)


def _enviar_lembretes_reembolso() -> None:
    try:
        from app.database import SessionLocal
        from app.models.cliente import Cliente
        from app.models.reembolso import Reembolso
        from app.routers.reembolsos import (
            BCC_EMAIL_FIXO,
            _build_email_html,
            _get_pdf_with_drive_link,
            _refresh_if_needed,
            _send_gmail,
        )

        access_token = _refresh_if_needed()
        if not access_token:
            logger.info("Scheduler: conta Google indisponível para lembretes de reembolso")
            return

        now = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            reembolsos = (
                db.query(Reembolso)
                .filter(Reembolso.status.in_(["enviado", "aguardando_pagamento"]))
                .all()
            )
            enviados = 0
            for r in reembolsos:
                destinatario = (r.email_destinatario or "").strip()
                if not destinatario:
                    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
                    destinatario = (cliente.email or "").strip() if cliente and cliente.email else ""
                if not destinatario:
                    logger.info("Scheduler: reembolso %s sem e-mail para lembrete", r.id)
                    continue

                ultimo = r.ultimo_lembrete_em
                if ultimo and ultimo.tzinfo is None:
                    ultimo = ultimo.replace(tzinfo=timezone.utc)
                if ultimo and now - ultimo < REEMBOLSO_REMINDER_INTERVAL:
                    continue

                try:
                    cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
                    cliente_nome = cliente.nome if cliente else "cliente"
                    pdf_bytes = _get_pdf_with_drive_link(r, db)
                    html = _build_email_html(r, header_color="#ea580c", is_lembrete=True)
                    _send_gmail(
                        access_token=access_token,
                        to=destinatario,
                        subject=f"Lembrete — Nota de Reembolso de Despesas — {r.titulo}",
                        html=html,
                        pdf_bytes=pdf_bytes,
                        pdf_filename=f"Nota de Reembolso - {cliente_nome}.pdf",
                        bcc=[BCC_EMAIL_FIXO],
                    )
                    r.email_destinatario = destinatario
                    r.ultimo_lembrete_em = now
                    db.commit()
                    enviados += 1
                except Exception as exc:
                    db.rollback()
                    logger.warning("Scheduler: falha ao lembrar reembolso %s: %s", r.id, exc)
            logger.info("Scheduler: lembretes de reembolso concluídos (%d enviados)", enviados)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Scheduler: falha geral nos lembretes de reembolso: %s", exc)


def start_scheduler() -> None:
    if scheduler.running:
        logger.info("Scheduler já estava ativo")
        return

    scheduler.add_job(
        _sync_all_processos,
        trigger=CronTrigger(hour=3, minute=0),
        id="sync_andamentos_noturno",
        replace_existing=True,
    )
    scheduler.add_job(
        _refresh_jusbr_session,
        trigger=CronTrigger(hour='*/6', minute=15),
        id="refresh_jusbr_session",
        replace_existing=True,
    )
    scheduler.add_job(
        _refresh_google_master_session,
        trigger=CronTrigger(hour='*/6', minute=25),
        id="refresh_google_master_session",
        replace_existing=True,
    )
    scheduler.add_job(
        _sync_diarios_monitorados,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=0),
        id="sync_diario_monitorado",
        replace_existing=True,
    )
    scheduler.add_job(
        _renovar_drive_watch,
        trigger=CronTrigger(hour=6, minute=0),
        id="renovar_drive_watch",
        replace_existing=True,
    )
    scheduler.add_job(
        _enviar_lembretes_reembolso,
        trigger=CronTrigger(hour=9, minute=10),
        id="lembretes_reembolso",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado — DataJud 03:00, Diário Oficial seg-sex 08:00, Drive watch 06:00, lembretes de reembolso 09:10")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
