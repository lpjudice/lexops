"""APScheduler — rotinas automáticas do app em horário de São Paulo."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
DIARIO_TRIBUNAIS_ORDEM = ["DJEN", "TJSP", "TJES", "TJAM", "TJRJ"]
DIARIO_DAYS_BACK = 3


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


def _sync_diarios_monitorados() -> None:
    try:
        from app.database import SessionLocal
        from app.models.cliente import Cliente
        from app.routers.diario import _filtrar_itens_monitorados_exatos, _inserir_publicacoes
        from app.services.diario_monitoring import load_monitoring_config
        from app.services.scraping_tribunais import scrape_todos

        db = SessionLocal()
        try:
            config = load_monitoring_config()
            nomes_clientes = [
                c.nome.strip()
                for c in db.query(Cliente).order_by(Cliente.nome).all()
                if getattr(c, "nome", None) and c.nome.strip()
            ]
            termos = list(dict.fromkeys([*nomes_clientes, *(config.get("termos_extras") or [])]))
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
    scheduler.start()
    logger.info("Scheduler iniciado — DataJud diário às 03:00 BRT, Diário Oficial monitorado de segunda a sexta às 08:00 BRT, jus.br noturno se ativo, manutenção do jus.br a cada 6 horas e renovação da conta Google master a cada 6 horas")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
