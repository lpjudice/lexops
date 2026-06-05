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
from aiogram.exceptions import TelegramBadRequest
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
# Bare 20-digit CNJ (sem . ou -), opcionalmente com espaços
_CNJ_DIGITS_RE = re.compile(r"(?<!\d)(\d[\d\s]{18,}\d)(?!\d)")


def _format_cnj(digits: str) -> str:
    """20 dígitos → NNNNNNN-DD.AAAA.J.TT.OOOO."""
    return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:20]}"


def _extract_cnj(text: str) -> str | None:
    """Aceita CNJ formatado OU 20 dígitos corridos (com/sem espaços)."""
    m = _CNJ_RE.search(text)
    if m:
        return m.group(0)
    for raw in _CNJ_DIGITS_RE.findall(text):
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 20:
            return _format_cnj(digits)
    return None


# ── Per-chat state ────────────────────────────────────────────────────────────

@dataclass
class QueryState:
    cnj: str
    andamentos: list = field(default_factory=list)
    page: int = 0


_state: dict[int, QueryState] = {}


_HELP_TEXT = (
    "🏛️ *Bot de Andamentos Processuais*\n"
    "Consulta andamentos e documentos direto do jus.br/PDPJ.\n\n"
    "*Buscar andamentos:*\n"
    "• Envie o *número CNJ* — com pontos/traços (`0001234-56.2023.8.26.0100`) "
    "ou os 20 dígitos corridos. O bot reorganiza sozinho.\n"
    "• `/buscar <cnj>` — mesma coisa, via comando.\n\n"
    "*Buscar pelo cliente (cadastro do lexops):*\n"
    "• `/busca <nome>` — filtra clientes pelo nome e lista os processos "
    "(partes, vara/comarca, matéria, status e a descrição). Toque no processo p/ ver andamentos.\n"
    "• `/busca` (sem nome) — lista *todos* os clientes em ordem alfabética, de 10 em 10.\n\n"
    "*Sessão jus.br (login gov.br):*\n"
    "• `/login` — revalida o acesso manualmente (gera o link de login gov.br).\n"
    "• `/sessao` — mostra se a sessão está ativa e quando expira.\n\n"
    "*Ajuda:*\n"
    "• `/help` ou `/ajuda` — mostra esta mensagem.\n\n"
    "_Nos resultados: 📎 = tem documento · botão “Quero os documentos” envia os PDFs aqui · "
    "“Ver mais” pagina os andamentos._"
)


async def _safe_send(bot: Bot, chat_id: int, text: str, reply_markup=None):
    """Envia em Markdown; se o conteúdo dinâmico quebrar o parser (descrição de
    andamento com * _ ` soltos), reenvia em texto puro para nunca falhar."""
    try:
        return await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=reply_markup)
    except TelegramBadRequest:
        return await bot.send_message(chat_id, text, reply_markup=reply_markup)

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
    await _safe_send(
        bot, chat_id, "\n".join(lines),
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


# ── Busca por cliente / processo (dados do lexops) ─────────────────────────────

def _query_clientes(termo: str) -> list[tuple[str, str, int]]:
    """Retorna (id, nome, qtd_processos) dos clientes que casam com o termo."""
    from app.database import SessionLocal
    from app.models.cliente import Cliente

    db = SessionLocal()
    try:
        q = db.query(Cliente).order_by(Cliente.nome.asc())
        if termo:
            q = q.filter(Cliente.nome.ilike(f"%{termo}%")).limit(15)
        rows = q.all()
        return [(str(c.id), c.nome, len(c.processos)) for c in rows]
    finally:
        db.close()


_CLI_PAGE = 10


def _query_clientes_pagina(offset: int) -> tuple[list[tuple[str, str, int]], int]:
    """Página de TODOS os clientes (ordem alfabética). Retorna (linhas, total)."""
    from app.database import SessionLocal
    from app.models.cliente import Cliente

    db = SessionLocal()
    try:
        total = db.query(Cliente).count()
        rows = (
            db.query(Cliente)
            .order_by(Cliente.nome.asc())
            .offset(offset)
            .limit(_CLI_PAGE)
            .all()
        )
        return [(str(c.id), c.nome, len(c.processos)) for c in rows], total
    finally:
        db.close()


def _query_processos(cliente_id: str) -> tuple[str, list[dict]]:
    """Retorna (nome_cliente, lista de dicts de processo) de um cliente."""
    from app.database import SessionLocal
    from app.models.cliente import Cliente
    from app.models.processo import Processo

    db = SessionLocal()
    try:
        cli = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if not cli:
            return "", []
        procs = (
            db.query(Processo)
            .filter(Processo.cliente_id == cliente_id)
            .order_by(Processo.created_at.desc())
            .all()
        )
        out = []
        for p in procs:
            litis = ", ".join(c.nome for c in p.clientes_litisconsorcio) if p.clientes_litisconsorcio else ""
            out.append({
                "numero_cnj": p.numero_cnj,
                "tribunal": p.tribunal or "",
                "polo": p.polo or "",
                "objeto": p.objeto or "",
                "materia": p.materia or "",
                "vara": p.vara or "",
                "comarca": p.comarca or "",
                "status": p.status or "",
                "litisconsorcio": litis,
            })
        return cli.nome, out
    finally:
        db.close()


async def _busca_clientes(bot: Bot, chat_id: int, termo: str) -> None:
    # Sem termo → lista paginada de todos. Com termo → busca parcial direta.
    if not termo:
        await _busca_clientes_pagina(bot, chat_id, 0)
        return

    clientes = _query_clientes(termo)
    if not clientes:
        await bot.send_message(chat_id, f"Nenhum cliente para “{termo}”.")
        return
    rows = [
        [InlineKeyboardButton(text=f"{nome} ({qtd} proc.)", callback_data=f"acli:{cid}")]
        for cid, nome, qtd in clientes
    ]
    await _safe_send(
        bot, chat_id,
        f"👤 *{len(clientes)} cliente(s)* para “{termo}”:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _busca_clientes_pagina(bot: Bot, chat_id: int, offset: int) -> None:
    clientes, total = _query_clientes_pagina(offset)
    if not clientes:
        await bot.send_message(chat_id, "Nenhum cliente cadastrado.")
        return
    rows = [
        [InlineKeyboardButton(text=f"{nome} ({qtd} proc.)", callback_data=f"acli:{cid}")]
        for cid, nome, qtd in clientes
    ]
    # Navegação + chip "digitar nome"
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀ Anteriores", callback_data=f"aclg:{max(0, offset - _CLI_PAGE)}"))
    if offset + _CLI_PAGE < total:
        nav.append(InlineKeyboardButton(text="Próximos 10 ▶", callback_data=f"aclg:{offset + _CLI_PAGE}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="✏️ Digitar nome", callback_data="aclhint")])

    ini, fim = offset + 1, min(offset + _CLI_PAGE, total)
    await _safe_send(
        bot, chat_id,
        f"👤 *Clientes {ini}–{fim} de {total}* (ordem alfabética):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _fmt_processo(p: dict, idx: int) -> str:
    linhas = [f"*{idx}.* `{p['numero_cnj']}`"]
    meta = " · ".join(x for x in [p["tribunal"], p["polo"], p["status"]] if x)
    if meta:
        linhas.append(f"   {meta}")
    local = " · ".join(x for x in [p["vara"], p["comarca"]] if x)
    if local:
        linhas.append(f"   {local}")
    if p["materia"]:
        linhas.append(f"   📂 {p['materia']}")
    if p["litisconsorcio"]:
        linhas.append(f"   👥 {p['litisconsorcio']}")
    if p["objeto"]:
        linhas.append(f"   📝 {p['objeto'].strip()[:300]}")
    return "\n".join(linhas)


async def _listar_processos(bot: Bot, chat_id: int, cliente_id: str) -> None:
    nome, procs = _query_processos(cliente_id)
    if not procs:
        await bot.send_message(chat_id, f"{nome or 'Cliente'} não tem processos cadastrados.")
        return
    await _safe_send(bot, chat_id, f"⚖️ *Processos de {nome}* ({len(procs)}):")
    for i, p in enumerate(procs, 1):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔍 Buscar andamentos", callback_data=f"aproc:{p['numero_cnj']}")
        ]])
        await _safe_send(bot, chat_id, _fmt_processo(p, i), reply_markup=kb)


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

    async def _enviar_ajuda(msg: Message) -> None:
        await msg.answer(_HELP_TEXT, parse_mode="Markdown", disable_web_page_preview=True)

    @dp.message(Command("start"))
    async def cmd_start(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        await _enviar_ajuda(msg)

    @dp.message(Command("help"))
    @dp.message(Command("ajuda"))
    async def cmd_help(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        await _enviar_ajuda(msg)

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
        cnj = _extract_cnj(command.args or "")
        if not cnj:
            await msg.answer("Formato inválido. Ex: `0001234-56.2023.8.26.0100` ou os 20 dígitos corridos.", parse_mode="Markdown")
            return
        await _run_lookup(msg.bot, msg.chat.id, cnj)

    @dp.message(Command("busca"))
    async def cmd_busca(msg: Message, command: CommandObject) -> None:
        if not _allowed(msg.from_user.id):
            return
        termo = (command.args or "").strip()
        # /busca sem termo → lista todos os clientes; com termo → busca parcial
        if termo and len(termo) < 2:
            await msg.answer("Digite ao menos 2 letras, ou só `/busca` para listar todos.", parse_mode="Markdown")
            return
        await _busca_clientes(msg.bot, msg.chat.id, termo)

    @dp.message(Command("login"))
    async def cmd_login(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        sess = andamentos_auth.load_session()
        if sess:
            await msg.answer(
                f"✅ A sessão jus.br já está ativa (expira o access em {sess.get('expires_at')}).\n"
                "Para forçar um login novo mesmo assim, é só seguir o link abaixo."
            )
        await _send_login_link(msg.bot, msg.chat.id)

    @dp.message(F.text)
    async def text_handler(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        text = msg.text or ""
        chat_id = msg.chat.id

        # CNJ (formatado ou 20 dígitos) → start a lookup
        cnj = _extract_cnj(text)
        if cnj:
            await _run_lookup(msg.bot, chat_id, cnj)
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

    @dp.callback_query(F.data.startswith("acli:"))
    async def cb_cliente(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        cliente_id = query.data.split(":", 1)[1]
        await query.answer()
        await _listar_processos(query.bot, query.message.chat.id, cliente_id)

    @dp.callback_query(F.data.startswith("aclg:"))
    async def cb_clientes_pagina(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        offset = int(query.data.split(":", 1)[1])
        await query.answer()
        await _busca_clientes_pagina(query.bot, query.message.chat.id, offset)

    @dp.callback_query(F.data == "aclhint")
    async def cb_clientes_hint(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        await query.answer()
        await query.bot.send_message(
            query.message.chat.id,
            "✏️ Digite `/busca <parte do nome>` — ex: `/busca silva` — que eu filtro os clientes.",
            parse_mode="Markdown",
        )

    @dp.callback_query(F.data.startswith("aproc:"))
    async def cb_processo(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        cnj = query.data.split(":", 1)[1]
        await query.answer()
        await _run_lookup(query.bot, query.message.chat.id, cnj)

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
            doc = BufferedInputFile(content, filename=filename)
            try:
                await query.bot.send_document(chat_id, document=doc, caption=caption, parse_mode="Markdown")
            except TelegramBadRequest:
                doc = BufferedInputFile(content, filename=filename)
                await query.bot.send_document(chat_id, document=doc, caption=caption)

    return dp


async def run_polling(token: str, dispatcher: Dispatcher) -> None:
    bot = Bot(token=token)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
