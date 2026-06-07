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


def _sync_jusbr_notificaveis() -> None:
    """18h45 BRT — sincroniza jus.br dos processos com push ativo."""
    try:
        from app.services.andamentos_push import sync_jusbr_notificaveis
        sync_jusbr_notificaveis()
    except Exception as exc:
        logger.warning("Scheduler: sync_jusbr_notificaveis falhou: %s", exc)


def _push_andamentos_telegram() -> None:
    """19h BRT — envia o resumo do dia no grupo do Telegram."""
    try:
        from app.services.andamentos_push import push_andamentos_telegram
        push_andamentos_telegram()
    except Exception as exc:
        logger.warning("Scheduler: push_andamentos_telegram falhou: %s", exc)


def _refresh_andamentos_session() -> None:
    """Mantém vivo o offline token do bot @jusbr_andamentos_bot (sessão id=2).

    O refresh token é offline (não expira), mas o Keycloak encerra a sessão
    offline por inatividade. Renovar periodicamente mantém viva indefinidamente.
    """
    try:
        from app.services.andamentos_auth import refresh_proactively

        if refresh_proactively():
            logger.info("Scheduler: sessão andamentos (offline) renovada")
        else:
            logger.info("Scheduler: nenhuma sessão andamentos para renovar")
    except Exception as exc:
        logger.warning("Scheduler: falha ao renovar sessão andamentos: %s", exc)


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
            _oabs_monitoradas,
            _termos_monitorados_para_busca,
        )
        from app.services.scraping_tribunais import scrape_todos

        db = SessionLocal()
        try:
            termos = _termos_monitorados_para_busca(db)
            oabs = _oabs_monitoradas()
            if not termos and not oabs:
                logger.info("Scheduler: nenhum termo/OAB monitorado para Diário Oficial")
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
                        oabs=oabs or None,
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


def _sync_diario2_gmail() -> None:
    try:
        from app.routers.diario2 import sync_diario2_job

        result = sync_diario2_job(days_back=7)
        logger.info(
            "Scheduler: Diário 2 Gmail concluído (%d novas, %d duplicatas, %d sem publicação, %d erros)",
            result.inseridas,
            result.duplicatas,
            result.sem_publicacoes,
            result.erros,
        )
    except Exception as exc:
        logger.warning("Scheduler: falha na sincronização automática do Diário 2 Gmail: %s", exc)


def _relatorio_fiscal_contador() -> None:
    """Diariamente às 8h30 — envia o relatório fiscal se hoje == dia configurado."""
    from datetime import datetime
    try:
        from app.database import SessionLocal
        from app.models.config_fiscal import ConfigFiscal
        from app.services.nfse.relatorio_contador import enviar_relatorio
        db = SessionLocal()
        try:
            cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
            if not cfg or not cfg.enviar_relatorio_auto:
                return
            dia = cfg.dia_envio_relatorio or 1
            if datetime.now().day != dia:
                return
            res = enviar_relatorio(db)  # mês anterior
            logger.info("Relatório fiscal ao contador: %s", res)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Scheduler: relatório fiscal falhou: %s", exc)


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
        _refresh_andamentos_session,
        trigger=CronTrigger(hour='*/12', minute=40),
        id="refresh_andamentos_session",
        replace_existing=True,
    )
    # Push diário do @jusbr_andamentos_bot — coleta jus.br 18h45 e envia 19h
    scheduler.add_job(
        _sync_jusbr_notificaveis,
        trigger=CronTrigger(hour=18, minute=45, timezone="America/Sao_Paulo"),
        id="sync_jusbr_notificaveis",
        replace_existing=True,
    )
    scheduler.add_job(
        _push_andamentos_telegram,
        trigger=CronTrigger(hour=19, minute=0, timezone="America/Sao_Paulo"),
        id="push_andamentos_telegram",
        replace_existing=True,
    )
    scheduler.add_job(
        _sync_diarios_monitorados,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=0),
        id="sync_diario_monitorado",
        replace_existing=True,
    )
    scheduler.add_job(
        _sync_diario2_gmail,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=0),
        id="sync_diario2_gmail_0900",
        replace_existing=True,
    )
    scheduler.add_job(
        _sync_diario2_gmail,
        trigger=CronTrigger(day_of_week="mon-fri", hour=11, minute=0),
        id="sync_diario2_gmail_1100",
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
    # Relatório fiscal ao contador — verifica diariamente às 8h; envia no dia configurado
    scheduler.add_job(
        _relatorio_fiscal_contador,
        trigger=CronTrigger(hour=8, minute=30, timezone="America/Sao_Paulo"),
        id="relatorio_fiscal_contador",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado — DataJud 03:00, Diário Oficial 08:00, Diário 2 Gmail 09:00/11:00, Drive watch 06:00, lembretes de reembolso 09:10")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
