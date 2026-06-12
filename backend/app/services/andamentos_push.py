"""Cron de coleta + envio diário de andamentos via @jusbr_andamentos_bot.

Dois jobs encadeados:
  - 18h45 (BRT)  → sincroniza jus.br dos processos monitorados (escritório
                   via lógica travada; CNJs avulsos via coletor próprio).
  - 19h00 (BRT)  → lê do banco os andamentos com notificado=False, agrupa
                   por processo e envia 1 mensagem por processo no grupo
                   (ANDAMENTOS_PUSH_CHAT_ID). Sem nada → "Nenhum andamento novo".

Toda a lógica é orquestração — quem coleta de verdade é a função travada
sincronizar_processo_jusbr (escritório) ou o andamento_extra_collector (avulsos).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.andamento_telegram_extra import AndamentoTelegramExtra
from app.models.cliente import Cliente
from app.models.processo import Processo
from app.models.processo_telegram_extra import ProcessoTelegramExtra

logger = logging.getLogger(__name__)

_BRT = ZoneInfo("America/Sao_Paulo")
# Janela: andamentos "novos hoje" → criados nas últimas 24h. Larga o bastante
# pra não perder se o cron das 3h coletar coisa retroativa.
_JANELA_HORAS = 24


# ── Sync 18h45 ────────────────────────────────────────────────────────────────

def sync_jusbr_notificaveis() -> None:
    """Sincroniza via jus.br os processos com notificar_telegram=True (escritório)
    + CNJs avulsos com notificar=True (extras)."""
    asyncio.run(_async_sync())


async def _async_sync() -> None:
    """O bot tem sessão própria (id=2, offline_access perene). Usamos ela como
    PRIORITÁRIA — não dependemos da sessão do lexops (id=1) ficar viva. Se por
    algum motivo a id=2 cair, caímos pra id=1 como rede de segurança."""
    from app.services.andamentos_auth import load_session as load_bot_session
    from app.services.consulta_processual.jusbr_session import load_session as load_lexops_session
    from app.services.consulta_processual.orchestrator import sincronizar_processo_jusbr
    from app.services.andamento_extra_collector import sincronizar_extra

    sess = load_bot_session() or load_lexops_session()
    if not sess:
        logger.warning("push_18h45: nem id=2 (bot) nem id=1 (lexops) ativa — pulando sync.")
        return
    fonte = "id=2 (bot, perene)" if load_bot_session() else "id=1 (lexops, fallback)"
    logger.info("push_18h45: usando sessão %s", fonte)

    token = sess.get("token")

    # Processos do escritório (lógica travada, intocada)
    db = SessionLocal()
    try:
        procs = (
            db.query(Processo)
            .filter(Processo.notificar_telegram.is_(True))
            .filter(Processo.status == "ativo")
            .all()
        )
        logger.info("push_18h45: sincronizando %d processo(s) escritório via jus.br", len(procs))
        for p in procs:
            try:
                await sincronizar_processo_jusbr(p, db, token=token, session_data=sess)
            except Exception:
                logger.exception("push_18h45 sync processo %s falhou", p.numero_cnj)
                db.rollback()
    finally:
        db.close()

    # Avulsos (coletor próprio, sem alterar travado)
    db = SessionLocal()
    try:
        extras = (
            db.query(ProcessoTelegramExtra)
            .filter(ProcessoTelegramExtra.notificar.is_(True))
            .all()
        )
        logger.info("push_18h45: sincronizando %d CNJ(s) avulso(s)", len(extras))
        for e in extras:
            try:
                novos = await sincronizar_extra(db, e, token)
                if novos:
                    logger.info("push_18h45: extra %s +%d", e.cnj, novos)
            except Exception:
                logger.exception("push_18h45 sync extra %s falhou", e.cnj)
                db.rollback()
    finally:
        db.close()


# ── Push 19h ──────────────────────────────────────────────────────────────────

def push_andamentos_telegram() -> None:
    """Envia o resumo do dia no grupo do Telegram."""
    asyncio.run(_async_push())


async def _async_push() -> None:
    chat_id_raw = (settings.andamentos_push_chat_id or "").strip()
    if not chat_id_raw:
        logger.warning("push_19h: ANDAMENTOS_PUSH_CHAT_ID não configurado — pulando.")
        return
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        logger.error("push_19h: ANDAMENTOS_PUSH_CHAT_ID inválido (%r).", chat_id_raw)
        return

    bot_token = settings.andamentos_bot_token
    if not bot_token:
        logger.warning("push_19h: andamentos_bot_token não configurado.")
        return

    from aiogram import Bot
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_JANELA_HORAS)
    grupos: list[dict] = []

    db = SessionLocal()
    try:
        # Escritório
        procs = (
            db.query(Processo, Cliente.nome)
            .join(Cliente, Cliente.id == Processo.cliente_id)
            .filter(Processo.notificar_telegram.is_(True))
            .all()
        )
        for p, nome_cli in procs:
            novos = (
                db.query(AndamentoProcesso)
                .filter(AndamentoProcesso.processo_id == p.id)
                .filter(AndamentoProcesso.notificado.is_(False))
                .filter(AndamentoProcesso.created_at >= cutoff)
                .order_by(AndamentoProcesso.data_andamento.desc().nullslast())
                .all()
            )
            if not novos:
                continue
            grupos.append({
                "tipo": "proc",
                "ref_id": str(p.id),
                "cabecalho": _cabecalho_proc(p, nome_cli),
                "qtd": len(novos),
                "mais_recente": novos[0].data_andamento,
                "andamento_ids": [a.id for a in novos],
            })

        # Avulsos
        extras = db.query(ProcessoTelegramExtra).filter(ProcessoTelegramExtra.notificar.is_(True)).all()
        for e in extras:
            novos = (
                db.query(AndamentoTelegramExtra)
                .filter(AndamentoTelegramExtra.extra_id == e.id)
                .filter(AndamentoTelegramExtra.notificado.is_(False))
                .filter(AndamentoTelegramExtra.created_at >= cutoff)
                .order_by(AndamentoTelegramExtra.data_andamento.desc().nullslast())
                .all()
            )
            if not novos:
                continue
            grupos.append({
                "tipo": "extra",
                "ref_id": str(e.id),
                "cabecalho": _cabecalho_extra(e),
                "qtd": len(novos),
                "mais_recente": novos[0].data_andamento,
                "andamento_ids": [a.id for a in novos],
            })
    finally:
        db.close()

    bot = Bot(token=bot_token)
    hoje_br = datetime.now(_BRT).strftime("%d/%m/%Y")
    try:
        if not grupos:
            await bot.send_message(chat_id, f"✅ Nenhum andamento novo hoje, {hoje_br}.")
            return

        await bot.send_message(
            chat_id,
            f"📨 *Andamentos do dia — {hoje_br}*\n{len(grupos)} processo(s) com novidade.",
            parse_mode="Markdown",
        )

        # Envia 1 msg por processo + botão "Ver andamentos"
        for g in grupos:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"📋 Ver {g['qtd']} andamento(s)",
                    callback_data=f"apv:{g['tipo']}:{g['ref_id']}",
                )
            ]])
            data_extra = g["mais_recente"].strftime("%d/%m") if g.get("mais_recente") else "—"
            texto = f"{g['cabecalho']}\n📨 {g['qtd']} novo(s) · mais recente em {data_extra}"
            try:
                await bot.send_message(chat_id, texto, parse_mode="Markdown", reply_markup=kb)
            except TelegramBadRequest:
                await bot.send_message(chat_id, texto, reply_markup=kb)
            await asyncio.sleep(0.05)  # throttle

        # Marca como notificado AGORA (idempotente: não repete amanhã).
        db = SessionLocal()
        try:
            for g in grupos:
                ids = g["andamento_ids"]
                if not ids:
                    continue
                if g["tipo"] == "proc":
                    db.query(AndamentoProcesso).filter(AndamentoProcesso.id.in_(ids)).update(
                        {AndamentoProcesso.notificado: True}, synchronize_session=False
                    )
                else:
                    db.query(AndamentoTelegramExtra).filter(AndamentoTelegramExtra.id.in_(ids)).update(
                        {AndamentoTelegramExtra.notificado: True}, synchronize_session=False
                    )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("push_19h: erro marcando notificados")
        finally:
            db.close()
    finally:
        await bot.session.close()


# ── Formatação ────────────────────────────────────────────────────────────────

def _cabecalho_proc(p: Processo, nome_cliente: str) -> str:
    linhas = [f"⚖️ *{nome_cliente}*"]
    linhas.append(f"📋 `{p.numero_cnj}`")
    meta = " · ".join(x for x in [(p.tribunal or ""), (p.vara or ""), (p.comarca or "")] if x)
    if meta:
        linhas.append(f"🏛️ {meta}")
    if p.objeto:
        linhas.append(f"📝 {p.objeto.strip()[:240]}")
    return "\n".join(linhas)


def _cabecalho_extra(e: ProcessoTelegramExtra) -> str:
    titulo = e.apelido or e.nome_cliente or e.cnj
    linhas = [f"📌 *{titulo}*"]
    linhas.append(f"📋 `{e.cnj}`")
    meta = " · ".join(x for x in [(e.tribunal or ""), (e.vara or ""), (e.comarca or "")] if x)
    if meta:
        linhas.append(f"🏛️ {meta}")
    if e.descricao:
        linhas.append(f"📝 {e.descricao.strip()[:240]}")
    if e.info_adicional:
        linhas.append(f"_({e.info_adicional})_")
    return "\n".join(linhas)
