"""Telegram bot — process lookup via jus.br/PDPJ.

Long polling (not webhook) so this runs locally on the Mac without needing
to register a webhook or open a public port for Telegram updates.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import session as session_store
import tunnel
from collector import fetch_andamentos, fetch_document

logger = logging.getLogger(__name__)

_CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
_PAGE_SIZE = 5


@dataclass
class QueryState:
    cnj: str
    andamentos: list = field(default_factory=list)
    page: int = 0  # index of the last shown page


# Per chat_id state — in-memory, lost on restart (fine for interactive use)
_state: dict[int, QueryState] = {}


def _is_allowed(user_id: int, allowed_ids: list[int]) -> bool:
    return user_id in allowed_ids


def _fmt_andamento(a, index: int) -> str:
    data = a.data_andamento.strftime("%d/%m/%Y") if a.data_andamento else "—"
    tipo = f"  __{a.tipo}__\n" if a.tipo else ""
    desc = (a.descricao or "").strip()
    if len(desc) > 280:
        desc = desc[:277] + "..."
    has_doc = bool(a.arquivo_url or a.arquivo_nome)
    doc_mark = " 📎" if has_doc else ""
    return f"*{index}.* 📅 {data}{doc_mark}\n{tipo}{desc}"


def _build_page_keyboard(cnj: str, page: int, total: int, page_items: list) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    has_docs = any(a.arquivo_url or a.arquivo_nome for a in page_items)
    if has_docs:
        rows.append([InlineKeyboardButton(
            text="📄 Quero os documentos desta página",
            callback_data=f"docs:{cnj}:{page}",
        )])

    shown = (page + 1) * _PAGE_SIZE
    remaining = total - shown
    if remaining > 0:
        rows.append([InlineKeyboardButton(
            text=f"↓ Ver mais {min(remaining, _PAGE_SIZE)} andamentos ({remaining} restantes)",
            callback_data=f"more:{cnj}:{page + 1}",
        )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _page_text(cnj: str, page_items: list, page: int, total: int) -> str:
    start_idx = page * _PAGE_SIZE + 1
    lines = [f"📋 *{cnj}*\n"]
    for i, a in enumerate(page_items):
        lines.append(_fmt_andamento(a, start_idx + i))
        lines.append("")
    lines.append(f"_Mostrando {start_idx}–{start_idx + len(page_items) - 1} de {total} andamentos_")
    return "\n".join(lines)


async def _send_page(bot: Bot, chat_id: int, state: QueryState, page: int) -> None:
    all_a = state.andamentos
    start = page * _PAGE_SIZE
    page_items = all_a[start: start + _PAGE_SIZE]
    if not page_items:
        await bot.send_message(chat_id, "Não há mais andamentos.")
        return
    state.page = page
    text = _page_text(state.cnj, page_items, page, len(all_a))
    kb = _build_page_keyboard(state.cnj, page, len(all_a), page_items)
    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


async def _run_lookup(bot: Bot, chat_id: int, cnj: str, browser_mgr) -> None:
    """Full lookup flow: check session → maybe auth → collect → show first page."""
    sess = session_store.load_session()

    if not sess:
        await bot.send_message(chat_id, "🔐 Sessão jus.br inativa. Iniciando autenticação no portal...")
        browser_mgr.reset_auth_event()
        await browser_mgr.navigate_to_portal()

        await bot.send_message(chat_id, "🌐 Aguardando Cloudflare Tunnel...")
        base_url = await tunnel.get_url(timeout=45)
        if not base_url:
            await bot.send_message(
                chat_id,
                "⚠️ Cloudflare Tunnel não iniciou.\n"
                "Verifique se `cloudflared` está instalado (`brew install cloudflared`) "
                "e tente novamente."
            )
            return

        token, _exp = browser_mgr.create_viewer_token()
        link = f"{base_url}/viewer/{token}"
        await bot.send_message(
            chat_id,
            f"📱 *Login gov.br necessário*\n\nAbra este link no celular para fazer login:\n{link}\n\n"
            "_Link expira em 10 minutos. Após concluir o login no browser remoto, o bot continua automaticamente._",
            parse_mode="Markdown",
        )

        try:
            sess = await browser_mgr.wait_for_auth(timeout_seconds=600)
        except TimeoutError:
            await bot.send_message(chat_id, "⏰ Timeout aguardando login. Tente `/buscar` novamente.")
            return

        await bot.send_message(chat_id, "✅ Autenticado! Buscando andamentos...")

    else:
        await bot.send_message(chat_id, f"🔍 Buscando andamentos para `{cnj}`...", parse_mode="Markdown")

    try:
        andamentos = await fetch_andamentos(cnj, sess)  # type: ignore[arg-type]
    except ValueError as exc:
        await bot.send_message(chat_id, f"❌ {exc}")
        return
    except Exception as exc:
        logger.exception("Erro ao buscar andamentos para %s", cnj)
        await bot.send_message(chat_id, f"❌ Erro ao consultar: {str(exc)[:200]}")
        return

    if not andamentos:
        await bot.send_message(chat_id, f"Nenhum andamento encontrado para `{cnj}`.", parse_mode="Markdown")
        return

    state = QueryState(cnj=cnj, andamentos=andamentos)
    _state[chat_id] = state
    await _send_page(bot, chat_id, state, 0)


# ── Handler factory ──────────────────────────────────────────────────────────

def create_dispatcher(allowed_user_ids: list[int], browser_mgr) -> Dispatcher:
    dp = Dispatcher()

    def _allowed(uid: int | None) -> bool:
        return bool(uid and uid in allowed_user_ids)

    @dp.message(Command("start"))
    async def cmd_start(msg: Message) -> None:
        if not _allowed(msg.from_user and msg.from_user.id):
            return
        await msg.answer(
            "🏛️ *Bot de Andamentos Processuais*\n\n"
            "Envie o número CNJ ou use `/buscar NNNNNN-NN.NNNN.N.NN.NNNN`\n\n"
            "Outros comandos:\n"
            "/sessao — status da sessão jus.br\n"
            "/resetar — limpar sessão salva\n"
            "/ajuda — ajuda",
            parse_mode="Markdown",
        )

    @dp.message(Command("ajuda"))
    async def cmd_ajuda(msg: Message) -> None:
        if not _allowed(msg.from_user and msg.from_user.id):
            return
        await msg.answer(
            "*Como usar:*\n"
            "1. Envie o número CNJ (ex: `0001234-56.2023.8.26.0100`)\n"
            "2. Se a sessão jus.br estiver válida, os andamentos aparecem na hora\n"
            "3. Se expirada, você receberá um link para fazer login gov.br no celular\n"
            "4. Após login, os andamentos aparecem automaticamente\n\n"
            "📎 = andamento tem documento\n"
            "Toque em *Quero os documentos* para receber os PDFs aqui",
            parse_mode="Markdown",
        )

    @dp.message(Command("sessao"))
    async def cmd_sessao(msg: Message) -> None:
        if not _allowed(msg.from_user and msg.from_user.id):
            return
        await msg.answer(session_store.session_summary())

    @dp.message(Command("resetar"))
    async def cmd_resetar(msg: Message) -> None:
        if not _allowed(msg.from_user and msg.from_user.id):
            return
        session_store.clear_session()
        await browser_mgr.reset_session()
        await msg.answer("🗑️ Sessão jus.br e perfil do browser limpos.")

    @dp.message(Command("buscar"))
    async def cmd_buscar(msg: Message, command: CommandObject) -> None:
        if not _allowed(msg.from_user and msg.from_user.id):
            return
        raw = (command.args or "").strip()
        m = _CNJ_RE.search(raw)
        if not m:
            await msg.answer("Número CNJ inválido. Formato: `NNNNNNN-DD.AAAA.J.TT.OOOO`", parse_mode="Markdown")
            return
        await _run_lookup(msg.bot, msg.chat.id, m.group(0), browser_mgr)

    @dp.message(F.text)
    async def text_handler(msg: Message) -> None:
        if not _allowed(msg.from_user and msg.from_user.id):
            return
        text = (msg.text or "").strip()
        m = _CNJ_RE.search(text)
        if m:
            await _run_lookup(msg.bot, msg.chat.id, m.group(0), browser_mgr)

    @dp.callback_query(F.data.startswith("more:"))
    async def cb_more(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        _, cnj, page_str = query.data.split(":", 2)
        page = int(page_str)
        state = _state.get(query.message.chat.id)
        if not state or state.cnj != cnj:
            await query.answer("Consulta expirada. Busque novamente.")
            return
        await query.answer()
        await _send_page(query.bot, query.message.chat.id, state, page)

    @dp.callback_query(F.data.startswith("docs:"))
    async def cb_docs(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        _, cnj, page_str = query.data.split(":", 2)
        page = int(page_str)
        state = _state.get(query.message.chat.id)
        if not state or state.cnj != cnj:
            await query.answer("Consulta expirada. Busque novamente.")
            return

        start = page * _PAGE_SIZE
        page_items = state.andamentos[start: start + _PAGE_SIZE]
        docs = [(i, a) for i, a in enumerate(page_items) if a.arquivo_url or a.arquivo_nome]

        if not docs:
            await query.answer("Nenhum documento nesta página.")
            return

        await query.answer(f"Baixando {len(docs)} documento(s)...")
        chat_id = query.message.chat.id
        sess = session_store.load_session()

        for rel_i, a in docs:
            abs_i = start + rel_i + 1
            data = a.data_andamento.strftime("%d/%m/%Y") if a.data_andamento else "—"
            caption = f"*{abs_i}.* 📅 {data}\n{(a.descricao or '')[:200]}"

            if not a.arquivo_url:
                await query.bot.send_message(chat_id, f"⚠️ Andamento {abs_i}: sem URL de documento.", parse_mode="Markdown")
                continue

            await query.bot.send_message(chat_id, f"⏳ Baixando documento {abs_i}...", parse_mode="Markdown")
            try:
                result = await fetch_document(a.arquivo_url, sess)
            except Exception as exc:
                await query.bot.send_message(chat_id, f"❌ Erro ao baixar documento {abs_i}: {str(exc)[:120]}")
                continue

            if not result:
                await query.bot.send_message(chat_id, f"⚠️ Documento {abs_i} não disponível (sessão pode estar expirada).")
                continue

            content, mimetype = result
            filename = a.arquivo_nome or f"documento_{abs_i}.pdf"
            from aiogram.types import BufferedInputFile
            await query.bot.send_document(
                chat_id,
                document=BufferedInputFile(content, filename=filename),
                caption=caption,
                parse_mode="Markdown",
            )

    return dp


async def run_polling(bot_token: str, dispatcher: Dispatcher) -> None:
    bot = Bot(token=bot_token)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
