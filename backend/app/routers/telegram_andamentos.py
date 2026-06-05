"""Telegram bot for process lookup (@jusbr_andamentos_bot).

Login: PKCE in the USER's real browser (gov.br anti-automation makes a headless
server browser unviable). The bot hands a login link; the user logs in normally
and pastes back the redirect URL; we exchange the code for a token.
See app.services.andamentos_auth.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from fastapi import APIRouter

from app.config import settings
from app.services import andamentos_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/andamentos", tags=["andamentos-bot"])

_PAGE_SIZE = 5
_CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


# ── Per-chat state ────────────────────────────────────────────────────────────

@dataclass
class QueryState:
    cnj: str
    andamentos: list = field(default_factory=list)
    page: int = 0


_state: dict[int, QueryState] = {}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _allowed(user_id: int) -> bool:
    ids = {int(x.strip()) for x in settings.andamentos_allowed_user_ids.split(",") if x.strip()}
    return user_id in ids


def _fmt_andamento(a, index: int) -> str:
    data = a.data_andamento.strftime("%d/%m/%Y") if a.data_andamento else "—"
    tipo = f"  __{a.tipo}__\n" if a.tipo else ""
    desc = (a.descricao or "").strip()
    if len(desc) > 300:
        desc = desc[:297] + "..."
    doc_mark = " 📎" if (a.arquivo_url or a.arquivo_nome) else ""
    return f"*{index}.* 📅 {data}{doc_mark}\n{tipo}{desc}"


def _build_keyboard(cnj: str, page: int, total: int, items: list) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    has_docs = any(a.arquivo_url or a.arquivo_nome for a in items)
    if has_docs:
        rows.append([InlineKeyboardButton(
            text="📄 Quero os documentos desta página",
            callback_data=f"adocs:{cnj}:{page}",
        )])
    remaining = total - (page + 1) * _PAGE_SIZE
    if remaining > 0:
        rows.append([InlineKeyboardButton(
            text=f"↓ Ver mais {min(remaining, _PAGE_SIZE)} ({remaining} restantes)",
            callback_data=f"amore:{cnj}:{page + 1}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_page(bot: Bot, chat_id: int, state: QueryState, page: int) -> None:
    items = state.andamentos[page * _PAGE_SIZE: (page + 1) * _PAGE_SIZE]
    if not items:
        await bot.send_message(chat_id, "Não há mais andamentos.")
        return
    state.page = page
    start = page * _PAGE_SIZE + 1
    lines = [f"📋 *{state.cnj}*\n"]
    for i, a in enumerate(items):
        lines.append(_fmt_andamento(a, start + i))
        lines.append("")
    lines.append(f"_Mostrando {start}–{start + len(items) - 1} de {len(state.andamentos)} andamentos_")
    await bot.send_message(
        chat_id,
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_build_keyboard(state.cnj, page, len(state.andamentos), items),
    )


# Remember the CNJ the user wanted, so we can resume after login
_pending_cnj: dict[int, str] = {}


async def _send_login_link(bot: Bot, chat_id: int) -> None:
    url = andamentos_auth.build_login_url(chat_id)
    # URL goes in a SEPARATE plain-text message — Markdown eats the underscores
    # in the OAuth params (client_id, offline_access, code_challenge…).
    await bot.send_message(
        chat_id,
        "🔐 *Login jus.br necessário*\n\n"
        "1. Abra o link abaixo no navegador e faça login no gov.br normalmente.\n"
        "2. Depois do login o navegador vai para uma página do portaldeservicos.pdpj.jus.br "
        "(pode mostrar erro / Solicitação inválida — tudo bem). "
        "Copie a URL INTEIRA da barra de endereço (contém `code=`) e cole aqui no chat.\n\n"
        "_Login no seu navegador real, sem captcha. Só uma vez._",
        parse_mode="Markdown",
    )
    await bot.send_message(chat_id, url, disable_web_page_preview=True)


async def _run_lookup(bot: Bot, chat_id: int, cnj: str) -> None:
    from app.services.consulta_processual.pdpj import buscar_via_pdpj
    from app.services.consulta_processual.cnj import inferir_tribunal_pelo_cnj

    tribunal = inferir_tribunal_pelo_cnj(cnj)
    if not tribunal:
        await bot.send_message(chat_id, f"❌ Tribunal não identificado para o CNJ `{cnj}`.", parse_mode="Markdown")
        return

    sess = andamentos_auth.load_session()
    if not sess:
        _pending_cnj[chat_id] = cnj
        await _send_login_link(bot, chat_id)
        return

    await bot.send_message(chat_id, f"🔍 Buscando `{cnj}`...", parse_mode="Markdown")

    try:
        token = sess.get("token")
        andamentos = await buscar_via_pdpj(cnj, tribunal, token=token, session_data=sess)
    except Exception as exc:
        logger.exception("Erro buscar_via_pdpj para %s", cnj)
        await bot.send_message(chat_id, f"❌ Erro na consulta: {str(exc)[:200]}")
        return

    if not andamentos:
        await bot.send_message(chat_id, f"Nenhum andamento encontrado para `{cnj}`.", parse_mode="Markdown")
        return

    andamentos.sort(key=lambda a: a.data_andamento or __import__("datetime").date.min, reverse=True)
    state = QueryState(cnj=cnj, andamentos=andamentos)
    _state[chat_id] = state
    await _send_page(bot, chat_id, state, 0)


# ── Telegram handlers ─────────────────────────────────────────────────────────

def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        await msg.answer(
            "🏛️ *Bot de Andamentos Processuais*\n\n"
            "Envie o número CNJ para buscar andamentos.\n"
            "Formato: `NNNNNNN-DD.AAAA.J.TT.OOOO`\n\n"
            "/sessao — status da sessão jus.br\n"
            "/resetar — limpar sessão",
            parse_mode="Markdown",
        )

    @dp.message(Command("sessao"))
    async def cmd_sessao(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        sess = andamentos_auth.load_session()
        if sess:
            await msg.answer(f"✅ Sessão ativa (andamentos)\nExpira: {sess.get('expires_at')}")
        else:
            await msg.answer("❌ Sem sessão ativa. Envie um CNJ para iniciar o login.")

    @dp.message(Command("buscar"))
    async def cmd_buscar(msg: Message, command: CommandObject) -> None:
        if not _allowed(msg.from_user.id):
            return
        m = _CNJ_RE.search(command.args or "")
        if not m:
            await msg.answer("Formato inválido. Ex: `0001234-56.2023.8.26.0100`", parse_mode="Markdown")
            return
        await _run_lookup(msg.bot, msg.chat.id, m.group(0))

    @dp.message(F.text)
    async def text_handler(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        text = msg.text or ""
        chat_id = msg.chat.id

        # CNJ → start a lookup
        m = _CNJ_RE.search(text)
        if m:
            await _run_lookup(msg.bot, chat_id, m.group(0))
            return

        # Pasted redirect URL / code while a login is pending → exchange it
        if andamentos_auth.has_pending(chat_id) and ("code=" in text or "pdpj.jus.br" in text or len(text.strip()) > 30):
            await msg.answer("🔄 Trocando o código por token...")
            try:
                payload = andamentos_auth.exchange_code(chat_id, text)
            except ValueError as exc:
                await msg.answer(f"❌ {exc}")
                return
            # Report token type — THIS tests the offline_access premise
            info = andamentos_auth.describe_refresh(payload)
            tipo = info.get("typ") or "?"
            offline = "♾️ OFFLINE (renovável indefinidamente!)" if tipo == "Offline" else f"⏳ {tipo} (expira em {info.get('exp')})"
            await msg.answer(
                f"✅ *Login concluído!*\n\n"
                f"Tipo do refresh token: {offline}\n"
                f"Escopo: `{info.get('scope')}`",
                parse_mode="Markdown",
            )
            cnj = _pending_cnj.pop(chat_id, None)
            if cnj:
                await _run_lookup(msg.bot, chat_id, cnj)

    @dp.callback_query(F.data.startswith("amore:"))
    async def cb_more(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        _, cnj, page_str = query.data.split(":", 2)
        state = _state.get(query.message.chat.id)
        if not state or state.cnj != cnj:
            await query.answer("Consulta expirada. Busque novamente.")
            return
        await query.answer()
        await _send_page(query.bot, query.message.chat.id, state, int(page_str))

    @dp.callback_query(F.data.startswith("adocs:"))
    async def cb_docs(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        _, cnj, page_str = query.data.split(":", 2)
        state = _state.get(query.message.chat.id)
        if not state or state.cnj != cnj:
            await query.answer("Consulta expirada.")
            return

        page = int(page_str)
        items = state.andamentos[page * _PAGE_SIZE: (page + 1) * _PAGE_SIZE]
        docs = [(i, a) for i, a in enumerate(items) if a.arquivo_url or a.arquivo_nome]
        if not docs:
            await query.answer("Nenhum documento nesta página.")
            return

        await query.answer(f"Baixando {len(docs)} documento(s)...")
        chat_id = query.message.chat.id

        from app.services.consulta_processual.pdpj import baixar_documento_jusbr
        sess = andamentos_auth.load_session()

        for rel_i, a in docs:
            abs_i = page * _PAGE_SIZE + rel_i + 1
            data_str = a.data_andamento.strftime("%d/%m/%Y") if a.data_andamento else "—"
            caption = f"*{abs_i}.* 📅 {data_str}\n{(a.descricao or '')[:200]}"

            if not a.arquivo_url:
                await query.bot.send_message(chat_id, f"⚠️ Andamento {abs_i}: sem URL de documento.")
                continue

            await query.bot.send_message(chat_id, f"⏳ Baixando documento {abs_i}...")
            try:
                result = await baixar_documento_jusbr(
                    a.arquivo_url,
                    token=sess.get("token") if sess else None,
                    session_data=sess,
                )
            except Exception as exc:
                await query.bot.send_message(chat_id, f"❌ Erro doc {abs_i}: {str(exc)[:120]}")
                continue

            if not result:
                await query.bot.send_message(chat_id, f"⚠️ Documento {abs_i} indisponível.")
                continue

            content, _ = result
            filename = a.arquivo_nome or f"documento_{abs_i}.pdf"
            await query.bot.send_document(
                chat_id,
                document=BufferedInputFile(content, filename=filename),
                caption=caption,
                parse_mode="Markdown",
            )

    return dp


async def run_polling(token: str, dispatcher: Dispatcher) -> None:
    bot = Bot(token=token)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
