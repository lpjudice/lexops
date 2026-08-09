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
    """18h45 BRT — sincroniza jus.br dos processos com push ativo.

    Qualquer exceção NÃO prevista aqui (fora dos casos já tratados dentro de
    sync_jusbr_notificaveis, como sessão caída) antes só virava um warning de
    log que ninguém via — o job "sumia" sem avisar. Agora também dispara o
    alerta no Telegram, senão o usuário não sabe que a varredura falhou.
    """
    try:
        from app.services.andamentos_push import sync_jusbr_notificaveis
        sync_jusbr_notificaveis()
    except Exception as exc:
        logger.exception("Scheduler: sync_jusbr_notificaveis falhou de forma inesperada")
        try:
            import asyncio
            from app.services.andamentos_push import _alert_sessao_caida, marcar_sync_falhou
            marcar_sync_falhou()
            asyncio.run(_alert_sessao_caida(f"Erro inesperado na varredura 18h45: {exc}"))
        except Exception:
            logger.exception("Scheduler: falha ao alertar sobre erro inesperado")


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


def _consolidar_drive_duplicatas() -> None:
    """Self-healing noturno: mescla pastas duplicadas no Drive (mantém a mais
    antiga, MOVE o conteúdo, e manda à lixeira só as cascas VAZIAS).
    NENHUM arquivo é apagado. Notifica o super admin por email quando houve ação."""
    try:
        from app.services.drive_manutencao import consolidar
        res = consolidar(max_depth=3, dry_run=False)
        if res.get("erro"):
            logger.info("Scheduler: consolidação Drive pulada — %s", res["erro"])
            return
        grupos = res.get("grupos_duplicados", 0)
        logger.info(
            "Scheduler: consolidação Drive — %d grupo(s), %d pasta(s) mesclada(s), %d arquivo(s) movido(s), %d pasta(s) à lixeira",
            grupos, res.get("pastas_mescladas", 0), res.get("arquivos_movidos", 0), len(res.get("pastas_lixeira", [])),
        )
        if grupos > 0:
            _notificar_consolidacao_email(res)
    except Exception as exc:
        logger.warning("Scheduler: falha na consolidação de duplicatas do Drive: %s", exc)


def _notificar_consolidacao_email(res: dict) -> None:
    """Envia email ao super admin com o resumo da consolidação noturna."""
    try:
        from app.database import SessionLocal
        from app.models.usuario import Usuario
        from app.services.email_service import _send_via_gmail_oauth

        with SessionLocal() as db:
            admin = db.query(Usuario).filter(Usuario.role == "super_admin", Usuario.ativo.is_(True)).first()
        if not admin or not admin.email:
            return

        lixeira = res.get("pastas_lixeira", [])
        linhas = "".join(f"<li>{p['name']} <code style='color:#9ca3af'>({p['id']})</code></li>" for p in lixeira[:200])
        html = f"""
        <div style="font-family:Arial,sans-serif;font-size:14px;color:#1d1e20">
          <h2 style="color:#0d9488">Consolidação de pastas do Drive</h2>
          <p>A rotina noturna encontrou e mesclou pastas duplicadas.</p>
          <ul>
            <li><b>{res.get('grupos_duplicados', 0)}</b> grupo(s) de pastas duplicadas</li>
            <li><b>{res.get('pastas_mescladas', 0)}</b> pasta(s) extra mescladas na mais antiga</li>
            <li><b>{res.get('arquivos_movidos', 0)}</b> arquivo(s) <b>movidos</b> (nenhum apagado)</li>
            <li><b>{len(lixeira)}</b> pasta(s) VAZIA(s) enviada(s) à lixeira do Drive (recuperável)</li>
          </ul>
          <p style="color:#065f46"><b>Critério:</b> mantém a pasta MAIS ANTIGA, move o conteúdo das cópias para dentro dela,
          e só manda à lixeira as pastas que ficaram vazias. <b>Nenhum arquivo é apagado</b> — arquivos duplicados de mesmo nome coexistem.</p>
          {f'<p><b>Pastas vazias enviadas à lixeira:</b></p><ul style="font-size:12px">{linhas}</ul>' if lixeira else ''}
        </div>
        """
        _send_via_gmail_oauth(admin.email, "Drive — pastas duplicadas consolidadas", html)
        logger.info("Scheduler: email de consolidação enviado para %s", admin.email)
    except Exception as exc:
        logger.warning("Scheduler: falha ao notificar consolidação por email: %s", exc)


def _relatorio_fiscal_contador() -> None:
    """Diariamente às 8h30 — envia o relatório fiscal se hoje == dia configurado.
    Idempotente: não reenvia se já houver log da competência (evita duplicidade).
    """
    from datetime import datetime, timedelta
    try:
        from app.database import SessionLocal
        from app.models.config_fiscal import ConfigFiscal
        from app.models.relatorio_fiscal_log import RelatorioFiscalLog
        from app.services.nfse.relatorio_contador import enviar_relatorio
        db = SessionLocal()
        try:
            cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
            if not cfg or not cfg.enviar_relatorio_auto:
                return
            dia = cfg.dia_envio_relatorio or 1
            if datetime.now().day != dia:
                return
            # Competência = mês anterior
            hoje = datetime.now().date()
            comp = (hoje.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            # DEDUP: já enviado com sucesso para esta competência?
            ja = (db.query(RelatorioFiscalLog)
                  .filter(RelatorioFiscalLog.competencia == comp,
                          RelatorioFiscalLog.status == "enviado").first())
            if ja:
                logger.info("Relatório %s já enviado em %s — pulando", comp, ja.enviado_em)
                return
            res = enviar_relatorio(db, comp)
            logger.info("Relatório fiscal ao contador: %s", res)
            if not res.get("enviado"):
                _alerta_falha_relatorio(db, cfg, comp, res.get("motivo", "desconhecido"))
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Scheduler: relatório fiscal falhou: %s", exc)
        try:
            from app.database import SessionLocal
            from app.models.config_fiscal import ConfigFiscal
            db2 = SessionLocal()
            _alerta_falha_relatorio(db2, db2.query(ConfigFiscal).get(1), "?", str(exc))
            db2.close()
        except Exception:
            pass


def _alerta_falha_relatorio(db, cfg, comp, motivo) -> None:
    """Avisa a conta master que o envio do relatório falhou."""
    try:
        from app.models.relatorio_fiscal_log import RelatorioFiscalLog
        db.add(RelatorioFiscalLog(competencia=comp or "?", status="erro", erro=str(motivo)[:500]))
        db.commit()
        from app.routers.reembolsos import _refresh_if_needed
        import httpx, base64, json
        import email.mime.text as mime_text
        token = _refresh_if_needed()
        master = (cfg.email_master if cfg else None) or "pj@pimentajudice.com.br"
        if token and master:
            msg = mime_text.MIMEText(
                f"O envio automático do relatório fiscal ({comp}) FALHOU.\nMotivo: {motivo}\n\n"
                f"Verifique o Config Fiscal e reenvie manualmente.", "plain", "utf-8")
            msg["to"] = master; msg["from"] = "me"
            msg["subject"] = f"[LexOps] ⚠️ Falha no relatório fiscal {comp}"
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            httpx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                       headers={"Authorization": f"Bearer {token}"},
                       content=json.dumps({"raw": raw}), timeout=30)
    except Exception as exc:
        logger.warning("Falha ao alertar erro de relatório: %s", exc)


def _gerar_instagram_diario() -> None:
    """07:00 BRT — Agente master gera 3 sugestões de post do dia."""
    try:
        from app.database import SessionLocal
        from app.services import ia_instagram

        db = SessionLocal()
        try:
            criadas = ia_instagram.gerar_sugestoes(db, quantidade=3)
            logger.info("Scheduler: %d sugestões de Instagram geradas", len(criadas))
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Scheduler: falha ao gerar sugestões de Instagram: %s", exc)


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
    # Access token do bot dura ~8h; roda a cada 6h pra sempre pegar ele ainda
    # vivo (evita o load_session() interno já ter refrescado antes da gente
    # chegar aqui, o que forçava 2 refreshes seguidos no Keycloak por ciclo).
    scheduler.add_job(
        _refresh_andamentos_session,
        trigger=CronTrigger(hour='*/6', minute=40),
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
    # Recorte Digital OAB (Diário 2 via Gmail): 07h/09h/11h/15h seg-sex.
    # Várias tentativas porque o diário às vezes não sai no horário certo.
    for _h in (7, 9, 11, 15):
        scheduler.add_job(
            _sync_diario2_gmail,
            trigger=CronTrigger(day_of_week="mon-fri", hour=_h, minute=0),
            id=f"sync_diario2_gmail_{_h:02d}00",
            replace_existing=True,
        )
    scheduler.add_job(
        _renovar_drive_watch,
        trigger=CronTrigger(hour=6, minute=0),
        id="renovar_drive_watch",
        replace_existing=True,
    )
    # Self-healing de pastas duplicadas no Drive — 04h
    scheduler.add_job(
        _consolidar_drive_duplicatas,
        trigger=CronTrigger(hour=4, minute=0),
        id="consolidar_drive_duplicatas",
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
    # Instagram — Agente master sugere posts todo dia às 07:00 BRT
    scheduler.add_job(
        _gerar_instagram_diario,
        trigger=CronTrigger(hour=7, minute=0, timezone="America/Sao_Paulo"),
        id="instagram_sugestoes_diarias",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado — DataJud 03:00, Diário Oficial 08:00, Recorte Digital (Diário 2) 07/09/11/15h, Drive watch 06:00, lembretes de reembolso 09:10")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
