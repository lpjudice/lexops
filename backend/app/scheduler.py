"""APScheduler — daily andamentos sync at 03:00 BRT."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


def _sync_all_processos() -> None:
    """Sync andamentos for all active processes. Runs as a background thread job."""
    try:
        from app.database import SessionLocal
        from app.models.processo import Processo
        from app.services.consulta_processual.orchestrator import sincronizar_processo

        db = SessionLocal()
        try:
            processos = (
                db.query(Processo)
                .filter(Processo.status == "ativo")
                .all()
            )
            logger.info("Scheduler: sincronizando %d processos ativos", len(processos))
            for p in processos:
                try:
                    asyncio.run(sincronizar_processo(p, db))
                except Exception as exc:
                    logger.warning("Erro ao sincronizar %s: %s", p.numero_cnj, exc)
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Erro crítico no scheduler de andamentos: %s", exc)


def start_scheduler() -> None:
    scheduler.add_job(
        _sync_all_processos,
        trigger=CronTrigger(hour=3, minute=0),
        id="sync_andamentos",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado — sync diário às 03:00 BRT")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
