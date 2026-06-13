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
    "• Envie o *número CNJ* — formatado (`0001234-56.2023.8.26.0100`) ou os 20 dígitos corridos. "
    "Detecto sozinho.\n"
    "• `/busca <cnj>` — mesma coisa via comando.\n\n"
    "*Lista e monitoramento (push diário 19h):*\n"
    "• `/lista` — todos os processos monitorados (escritório + avulsos).\n"
    "• `/add <cnj>` — adiciona um CNJ avulso (fora da carteira do escritório).\n"
    "• `/silenciar <cnj>` · `/ativar <cnj>` — controla o push individualmente.\n"
    "• `/silenciados` — lista só os que estão silenciados.\n"
    "• `/cancelar` — aborta um cadastro em andamento.\n\n"
    "*Sessão jus.br (login gov.br):*\n"
    "• `/login` — revalida o acesso (gera o link de login gov.br).\n"
    "• `/sessao` — status da sessão.\n"
    "• `/chatid` — descobre o id do chat atual (útil pra setup do grupo de push).\n\n"
    "*Ajuda:* `/help` ou `/ajuda`\n\n"
    "_📎 = tem documento · 📊 = processo do escritório · 📌 = CNJ avulso · "
    "🔔 = notificando · 🔕 = silenciado_"
)


def _diagnostico_doc(content: bytes, mimetype: str | None, nome: str | None) -> dict:
    """Coleta sinais úteis pra diagnosticar PDF/HTML que abre em branco."""
    size = len(content)
    head = content[:16]
    tail = content[-64:] if size > 64 else content
    is_pdf = content[:5] == b"%PDF-"
    pdf_version = content[5:8].decode("ascii", errors="replace") if is_pdf else None
    has_eof = b"%%EOF" in tail  # PDFs válidos terminam com %%EOF
    has_encrypt = b"/Encrypt" in content[:4096] or b"/Encrypt" in content[-4096:]
    has_xref = b"xref" in content or b"/XRef" in content
    # JPEG/PNG embeddeds (sentença escaneada)?
    has_jpeg = b"/DCTDecode" in content[:8192]
    has_image_only = has_jpeg and b"/Font" not in content[:16384]
    return {
        "size": size,
        "head_hex": head.hex(),
        "head_ascii": head.decode("latin1", errors="replace"),
        "tail_ascii": tail.decode("latin1", errors="replace").replace("\n", "\\n")[-80:],
        "is_pdf": is_pdf,
        "pdf_version": pdf_version,
        "has_eof": has_eof,
        "encrypted": has_encrypt,
        "has_xref": has_xref,
        "image_only_likely": has_image_only,
        "mimetype": mimetype,
        "nome": nome,
    }


def _nome_documento(content: bytes, mimetype: str | None, nome: str | None, idx: int) -> tuple[str, str]:
    """Corrige a extensão pelo conteúdo REAL (magic bytes), não pelo nome.

    Documentos do jus.br às vezes vêm em HTML mas nomeados .pdf → abrem em branco
    num leitor de PDF. Detectamos o tipo de verdade e renomeamos.
    Retorna (filename, tipo_legivel).
    """
    base = (nome or f"documento_{idx}").strip() or f"documento_{idx}"
    stem = base.rsplit(".", 1)[0] if "." in base else base
    mime = (mimetype or "").lower()
    head = content[:1024].lstrip().lower()

    if content[:5] == b"%PDF-" or "pdf" in mime:
        return f"{stem}.pdf", "PDF"
    if content[:5] == b"{\\rtf" or "rtf" in mime:
        return f"{stem}.rtf", "RTF"
    if head.startswith(b"<") and (b"<html" in head or b"<!doctype" in head or "html" in mime):
        return f"{stem}.html", "HTML"
    if content[:4] == b"PK\x03\x04":  # zip/docx/xlsx
        ext = base.rsplit(".", 1)[1] if "." in base else "zip"
        return f"{stem}.{ext}", ext.upper()
    # fallback: mantém o que tinha, ou .bin
    ext = base.rsplit(".", 1)[1] if "." in base else "bin"
    return f"{stem}.{ext}", ext.upper()


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

# State machine do /add — em memória, curto fluxo.
# chat_id → {step, cnj, resumo, apelido, descricao, info_adicional}
_add_state: dict[int, dict] = {}
_LISTA_PAGE = 10


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
    """Retorna (nome_cliente, lista de dicts de processo) de um cliente.

    Cada dict inclui as partes coletadas (se houver) e a flag notificar_telegram.
    """
    from app.database import SessionLocal
    from app.models.cliente import Cliente
    from app.models.processo import Processo
    from app.models.processo_parte import ProcessoParte

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
        ids = [p.id for p in procs]
        partes_por_proc: dict = {}
        if ids:
            for parte in db.query(ProcessoParte).filter(ProcessoParte.processo_id.in_(ids)).order_by(
                ProcessoParte.ordem
            ).all():
                partes_por_proc.setdefault(parte.processo_id, {}).setdefault(parte.polo, []).append(parte.nome)
        out = []
        for p in procs:
            litis = ", ".join(c.nome for c in p.clientes_litisconsorcio) if p.clientes_litisconsorcio else ""
            out.append({
                "processo_id": str(p.id),
                "numero_cnj": p.numero_cnj,
                "tribunal": p.tribunal or "",
                "polo": p.polo or "",
                "objeto": p.objeto or "",
                "materia": p.materia or "",
                "vara": p.vara or "",
                "comarca": p.comarca or "",
                "status": p.status or "",
                "litisconsorcio": litis,
                "notificar_telegram": bool(getattr(p, "notificar_telegram", True)),
                "partes_por_polo": partes_por_proc.get(p.id, {}),
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


_POLO_LABEL = {"ATIVO": "Polo ativo", "PASSIVO": "Polo passivo", "OUTROS": "Outras partes"}


def _fmt_polo(nomes: list[str], max_visible: int = 2) -> str:
    """1 → 'X' · 2 → 'X e Y' · 3+ → 'X, Y e Outros (N)'."""
    if not nomes:
        return ""
    n = len(nomes)
    if n == 1:
        return nomes[0]
    if n == 2:
        return f"{nomes[0]} e {nomes[1]}"
    visiveis = ", ".join(nomes[:max_visible])
    return f"{visiveis} e Outros ({n - max_visible})"


def _tem_overflow(partes_por_polo: dict[str, list[str]], threshold: int = 3) -> bool:
    return any(len(v) >= threshold for v in (partes_por_polo or {}).values())


def _fmt_processo(p: dict, idx: int) -> str:
    linhas = [f"*{idx}.* `{p['numero_cnj']}`"]
    meta = " · ".join(x for x in [p["tribunal"], p["polo"], p["status"]] if x)
    if meta:
        linhas.append(f"   {meta}")
    local = " · ".join(x for x in [p["vara"], p["comarca"]] if x)
    if local:
        linhas.append(f"   {local}")
    if p.get("materia"):
        linhas.append(f"   📂 {p['materia']}")

    # Partes coletadas via PDPJ — prevalecem sobre o fallback (litisconsórcio).
    partes_por_polo = p.get("partes_por_polo") or {}
    if partes_por_polo:
        for polo in ("ATIVO", "PASSIVO", "OUTROS"):
            nomes = partes_por_polo.get(polo) or []
            if nomes:
                linhas.append(f"   👥 {_POLO_LABEL[polo]}: {_fmt_polo(nomes)}")
    elif p.get("litisconsorcio"):
        linhas.append(f"   👥 {p['litisconsorcio']}")

    if p.get("objeto"):
        linhas.append(f"   📝 {p['objeto'].strip()[:300]}")
    return "\n".join(linhas)


async def _listar_processos(bot: Bot, chat_id: int, cliente_id: str) -> None:
    nome, procs = _query_processos(cliente_id)
    if not procs:
        await bot.send_message(chat_id, f"{nome or 'Cliente'} não tem processos cadastrados.")
        return
    await _safe_send(bot, chat_id, f"⚖️ *Processos de {nome}* ({len(procs)}):")
    for i, p in enumerate(procs, 1):
        botoes = []
        if _tem_overflow(p.get("partes_por_polo") or {}):
            botoes.append(InlineKeyboardButton(
                text="👥 Ver todas as partes",
                callback_data=f"apart:p:{p['processo_id']}",
            ))
        botoes.append(InlineKeyboardButton(
            text="🔍 Buscar andamentos",
            callback_data=f"aproc:{p['numero_cnj']}",
        ))
        kb = InlineKeyboardMarkup(inline_keyboard=[botoes])
        await _safe_send(bot, chat_id, _fmt_processo(p, i), reply_markup=kb)


# ── Monitorados (processos do escritório + CNJs avulsos do /add) ──────────────

def _listar_monitorados(offset: int, soh_silenciados: bool = False) -> tuple[list[dict], int]:
    """Une processos do escritório + extras do bot, ordena por nome.

    Cada item: {tipo: 'proc'|'extra', id, label, cnj, descricao, tribunal,
                notificar, vara, comarca, partes_por_polo, ref_id_str}.
    """
    from app.database import SessionLocal
    from app.models.cliente import Cliente
    from app.models.processo import Processo
    from app.models.processo_parte import ProcessoParte
    from app.models.processo_telegram_extra import ProcessoTelegramExtra

    db = SessionLocal()
    try:
        qp = db.query(Processo, Cliente.nome).join(Cliente, Cliente.id == Processo.cliente_id)
        if soh_silenciados:
            qp = qp.filter(Processo.notificar_telegram.is_(False))
        procs = qp.all()

        qe = db.query(ProcessoTelegramExtra)
        if soh_silenciados:
            qe = qe.filter(ProcessoTelegramExtra.notificar.is_(False))
        extras = qe.all()

        # partes em batch
        proc_ids = [p.id for p, _ in procs]
        extra_ids = [e.id for e in extras]
        partes_p, partes_e = {}, {}
        if proc_ids:
            for x in db.query(ProcessoParte).filter(ProcessoParte.processo_id.in_(proc_ids)).order_by(ProcessoParte.ordem).all():
                partes_p.setdefault(x.processo_id, {}).setdefault(x.polo, []).append(x.nome)
        if extra_ids:
            for x in db.query(ProcessoParte).filter(ProcessoParte.extra_id.in_(extra_ids)).order_by(ProcessoParte.ordem).all():
                partes_e.setdefault(x.extra_id, {}).setdefault(x.polo, []).append(x.nome)

        items: list[dict] = []
        for p, nome_cliente in procs:
            items.append({
                "tipo": "proc",
                "ref_id_str": str(p.id),
                "label": nome_cliente,
                "cnj": p.numero_cnj,
                "tribunal": p.tribunal or "",
                "vara": p.vara or "",
                "comarca": p.comarca or "",
                "descricao": (p.objeto or "").strip(),
                "notificar": bool(getattr(p, "notificar_telegram", True)),
                "partes_por_polo": partes_p.get(p.id, {}),
            })
        for e in extras:
            items.append({
                "tipo": "extra",
                "ref_id_str": str(e.id),
                "label": e.apelido or e.nome_cliente or e.cnj,
                "cnj": e.cnj,
                "tribunal": e.tribunal or "",
                "vara": e.vara or "",
                "comarca": e.comarca or "",
                "descricao": (e.descricao or "").strip(),
                "notificar": bool(e.notificar),
                "partes_por_polo": partes_e.get(e.id, {}),
            })

        items.sort(key=lambda x: (x["label"] or "").lower())
        total = len(items)
        return items[offset: offset + _LISTA_PAGE], total
    finally:
        db.close()


def _fmt_monitorado(item: dict, idx: int) -> str:
    ico = "📊" if item["tipo"] == "proc" else "📌"
    estado = "🔔" if item["notificar"] else "🔕"
    linhas = [f"*{idx}.* {ico} *{item['label']}* {estado}"]
    linhas.append(f"   `{item['cnj']}`")
    meta = " · ".join(x for x in [item["tribunal"], item["vara"], item["comarca"]] if x)
    if meta:
        linhas.append(f"   {meta}")
    partes = item.get("partes_por_polo") or {}
    for polo in ("ATIVO", "PASSIVO"):
        nomes = partes.get(polo) or []
        if nomes:
            linhas.append(f"   👥 {_POLO_LABEL[polo]}: {_fmt_polo(nomes)}")
    if item["descricao"]:
        linhas.append(f"   📝 {item['descricao'][:240]}")
    return "\n".join(linhas)


async def _send_lista_pagina(bot: Bot, chat_id: int, offset: int, soh_silenciados: bool = False) -> None:
    items, total = _listar_monitorados(offset, soh_silenciados)
    if not items and offset == 0:
        msg = "Nenhum processo silenciado." if soh_silenciados else "Nenhum processo monitorado ainda. Use `/add <cnj>` para começar."
        await bot.send_message(chat_id, msg, parse_mode="Markdown")
        return
    titulo = "🔕 *Silenciados*" if soh_silenciados else "🔔 *Monitorados*"
    ini, fim = offset + 1, min(offset + _LISTA_PAGE, total)
    await _safe_send(bot, chat_id, f"{titulo} — {ini}–{fim} de {total}")
    for i, item in enumerate(items, ini):
        ref = item["ref_id_str"]
        kind = item["tipo"]  # 'proc' ou 'extra'
        toggle_label = "🔔 Reativar" if not item["notificar"] else "🔕 Silenciar"
        botoes = [InlineKeyboardButton(
            text=toggle_label, callback_data=f"atoggle:{kind}:{ref}"
        )]
        if _tem_overflow(item.get("partes_por_polo") or {}):
            botoes.insert(0, InlineKeyboardButton(
                text="👥 Ver partes",
                callback_data=f"apart:{kind[0]}:{ref}",  # apart:p:UUID ou apart:e:UUID
            ))
        botoes.append(InlineKeyboardButton(
            text="🔍 Andamentos", callback_data=f"aproc:{item['cnj']}",
        ))
        rows = [botoes]
        await _safe_send(bot, chat_id, _fmt_monitorado(item, i), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    # Navegação no final
    nav: list[InlineKeyboardButton] = []
    cb_root = "alistsil" if soh_silenciados else "alistg"
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀ Anteriores", callback_data=f"{cb_root}:{max(0, offset - _LISTA_PAGE)}"))
    if offset + _LISTA_PAGE < total:
        nav.append(InlineKeyboardButton(text="Próximos 10 ▶", callback_data=f"{cb_root}:{offset + _LISTA_PAGE}"))
    if nav:
        await bot.send_message(
            chat_id, "Navegação:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[nav]),
        )


def _set_notificar(cnj: str, valor: bool) -> tuple[bool, str]:
    """Atualiza flag em processos OU extras. Retorna (achou, label)."""
    from app.database import SessionLocal
    from app.models.cliente import Cliente
    from app.models.processo import Processo
    from app.models.processo_telegram_extra import ProcessoTelegramExtra

    db = SessionLocal()
    try:
        p = db.query(Processo).filter(Processo.numero_cnj == cnj).first()
        if p:
            p.notificar_telegram = valor
            cli = db.query(Cliente).filter(Cliente.id == p.cliente_id).first()
            label = cli.nome if cli else cnj
            db.commit()
            return True, label
        e = db.query(ProcessoTelegramExtra).filter(ProcessoTelegramExtra.cnj == cnj).first()
        if e:
            e.notificar = valor
            label = e.apelido or e.nome_cliente or cnj
            db.commit()
            return True, label
        return False, ""
    finally:
        db.close()


def _toggle_notificar(kind: str, ref_id: str) -> tuple[bool, str, bool]:
    """Alterna a flag pelo id (uuid). Retorna (ok, label, novo_estado)."""
    from app.database import SessionLocal
    from app.models.cliente import Cliente
    from app.models.processo import Processo
    from app.models.processo_telegram_extra import ProcessoTelegramExtra

    db = SessionLocal()
    try:
        if kind == "proc":
            p = db.query(Processo).filter(Processo.id == ref_id).first()
            if not p:
                return False, "", False
            p.notificar_telegram = not bool(getattr(p, "notificar_telegram", True))
            cli = db.query(Cliente).filter(Cliente.id == p.cliente_id).first()
            db.commit()
            return True, (cli.nome if cli else p.numero_cnj), bool(p.notificar_telegram)
        if kind == "extra":
            e = db.query(ProcessoTelegramExtra).filter(ProcessoTelegramExtra.id == ref_id).first()
            if not e:
                return False, "", False
            e.notificar = not bool(e.notificar)
            db.commit()
            return True, (e.apelido or e.nome_cliente or e.cnj), bool(e.notificar)
        return False, "", False
    finally:
        db.close()


# ── /add — cadastro de CNJ avulso (state machine em memória) ──────────────────

async def _iniciar_add(bot: Bot, chat_id: int, cnj: str) -> None:
    """Verifica se o CNJ já existe, busca no PDPJ e abre o fluxo de cadastro."""
    from app.database import SessionLocal
    from app.models.processo import Processo
    from app.models.processo_telegram_extra import ProcessoTelegramExtra
    from app.services.processo_partes_collector import fetch_resumo

    # Já está em algum dos cadastros?
    db = SessionLocal()
    try:
        if db.query(Processo).filter(Processo.numero_cnj == cnj).first():
            await bot.send_message(chat_id, f"ℹ️ `{cnj}` já está cadastrado no lexops. Use /ativar pra ligar o push.", parse_mode="Markdown")
            return
        if db.query(ProcessoTelegramExtra).filter(ProcessoTelegramExtra.cnj == cnj).first():
            await bot.send_message(chat_id, f"ℹ️ `{cnj}` já está no /lista. Use /ativar caso esteja silenciado.", parse_mode="Markdown")
            return
    finally:
        db.close()

    sess = andamentos_auth.load_session()
    if not sess:
        _pending_cnj[chat_id] = f"__addcnj__{cnj}"  # marker pra retomar após login
        await bot.send_message(chat_id, "🔐 Preciso da sessão jus.br ativa pra buscar este processo. Faça login primeiro:")
        await _send_login_link(bot, chat_id)
        return

    await bot.send_message(chat_id, f"🔍 Buscando `{cnj}` no jus.br...", parse_mode="Markdown")
    try:
        resumo = await fetch_resumo(cnj, sess["token"])
    except Exception as exc:
        logger.exception("erro fetch_resumo /add")
        await bot.send_message(chat_id, f"❌ Erro consultando jus.br: {str(exc)[:160]}")
        return
    if not resumo:
        await bot.send_message(
            chat_id,
            f"❌ Não consegui localizar `{cnj}` no jus.br. Verifique o número, ou sua sessão pode não ter acesso a esse tribunal.",
            parse_mode="Markdown",
        )
        return

    # Pre-formata pra mostrar ao usuário
    linhas = [f"🔎 Encontrei `{cnj}`. Confere:\n"]
    if resumo.get("tribunal"):
        linhas.append(f"🏛️ {resumo['tribunal']}")
    if resumo.get("vara") or resumo.get("comarca"):
        linhas.append(f"   {' · '.join(x for x in [resumo.get('vara'), resumo.get('comarca')] if x)}")
    if resumo.get("classe"):
        linhas.append(f"📂 {resumo['classe']}")
    if resumo.get("assunto"):
        linhas.append(f"   {resumo['assunto']}")
    partes_dict: dict[str, list[str]] = {}
    for p in resumo.get("partes") or []:
        partes_dict.setdefault(p["polo"], []).append(p["nome"])
    for polo in ("ATIVO", "PASSIVO", "OUTROS"):
        nomes = partes_dict.get(polo) or []
        if nomes:
            linhas.append(f"👥 {_POLO_LABEL[polo]}: {_fmt_polo(nomes)}")

    await _safe_send(bot, chat_id, "\n".join(linhas))

    # Guarda em memória e abre a primeira pergunta
    _add_state[chat_id] = {
        "step": "apelido",
        "cnj": cnj,
        "resumo": resumo,
    }
    await bot.send_message(
        chat_id,
        "Como você quer chamar esse caso internamente?\n"
        "_(Apelido livre — aparece na lista e no push. Ou /cancelar para sair.)_",
        parse_mode="Markdown",
    )


async def _continuar_add(bot: Bot, chat_id: int, texto: str) -> bool:
    """Processa o texto conforme o step ativo. Retorna True se consumiu."""
    st = _add_state.get(chat_id)
    if not st:
        return False
    txt = (texto or "").strip()
    if txt.lower() in ("/cancelar", "/cancel"):
        _add_state.pop(chat_id, None)
        await bot.send_message(chat_id, "❌ Cadastro cancelado.")
        return True

    if st["step"] == "apelido":
        if not txt:
            await bot.send_message(chat_id, "Mande um apelido (texto), ou /cancelar.")
            return True
        st["apelido"] = txt[:200]
        st["step"] = "descricao"
        await bot.send_message(
            chat_id,
            "Quer adicionar uma *descrição/objeto*? (texto livre, ou /pular)",
            parse_mode="Markdown",
        )
        return True

    if st["step"] == "descricao":
        if txt.lower() in ("/pular", "/skip"):
            st["descricao"] = None
        else:
            st["descricao"] = txt[:1000]
        st["step"] = "info"
        await bot.send_message(
            chat_id,
            "Info adicional (até 5 palavras), ou /pular.",
        )
        return True

    if st["step"] == "info":
        if txt.lower() in ("/pular", "/skip"):
            st["info_adicional"] = None
        else:
            palavras = txt.split()
            if len(palavras) > 5:
                await bot.send_message(chat_id, "Máximo 5 palavras. Tente de novo, ou /pular.")
                return True
            st["info_adicional"] = " ".join(palavras)[:120]
        await _finalizar_add(bot, chat_id, st)
        _add_state.pop(chat_id, None)
        return True
    return False


async def _finalizar_add(bot: Bot, chat_id: int, st: dict) -> None:
    """Persiste o ProcessoTelegramExtra + partes."""
    from app.database import SessionLocal
    from app.models.processo_telegram_extra import ProcessoTelegramExtra
    from app.services.processo_partes_store import salvar_partes

    resumo = st["resumo"]
    db = SessionLocal()
    try:
        extra = ProcessoTelegramExtra(
            cnj=st["cnj"],
            nome_cliente=st.get("apelido"),  # se um dia separar, ajuste aqui
            apelido=st.get("apelido"),
            descricao=st.get("descricao"),
            info_adicional=st.get("info_adicional"),
            tribunal=resumo.get("tribunal"),
            vara=resumo.get("vara"),
            comarca=resumo.get("comarca"),
            criado_por_chat_id=chat_id,
            notificar=True,
        )
        db.add(extra)
        db.flush()
        if resumo.get("partes"):
            salvar_partes(db, extra_id=extra.id, partes=resumo["partes"])
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("erro persistindo extra")
        await bot.send_message(chat_id, "❌ Falha ao salvar. Tente novamente.")
        return
    finally:
        db.close()

    await bot.send_message(
        chat_id,
        f"✅ Cadastrado! *{st.get('apelido')}* entra no push diário a partir do próximo ciclo.\n"
        "Use /lista para ver todos os monitorados.",
        parse_mode="Markdown",
    )


async def _send_partes(bot: Bot, chat_id: int, kind: str, ref_id: str) -> None:
    """Envia lista completa de partes (ATIVO/PASSIVO/OUTROS)."""
    from app.database import SessionLocal
    from app.services.processo_partes_store import listar_partes

    db = SessionLocal()
    try:
        if kind == "p":
            partes = listar_partes(db, processo_id=ref_id)
        else:
            partes = listar_partes(db, extra_id=ref_id)
    finally:
        db.close()

    if not partes:
        await bot.send_message(chat_id, "Sem partes cadastradas (faça /buscar para sincronizar do jus.br).")
        return
    linhas = ["*Todas as partes do processo:*"]
    for polo in ("ATIVO", "PASSIVO", "OUTROS"):
        nomes = [r.nome for r in partes.get(polo, [])]
        if nomes:
            linhas.append(f"\n👥 *{_POLO_LABEL[polo]}* ({len(nomes)})")
            for n in nomes:
                linhas.append(f"  • {n}")
    await _safe_send(bot, chat_id, "\n".join(linhas))


_PUSH_PAGE = 10
# Cache em memória dos andamentos carregados por chat/ref — evita re-query nas
# trocas de página e dá pé pros documentos (que precisam da URL coletada).
# (chat_id, kind, ref_id) → [andamento_objects], created_at_cache
_push_cache: dict[tuple[int, str, str], list] = {}


def _carregar_push_andamentos(kind: str, ref_id: str) -> list:
    """Busca do banco os andamentos recentes (≤ 36h) p/ exibir no push view."""
    from datetime import datetime, timedelta, timezone
    from app.database import SessionLocal
    from app.models.andamento import AndamentoProcesso
    from app.models.andamento_telegram_extra import AndamentoTelegramExtra

    cutoff = datetime.now(timezone.utc) - timedelta(hours=36)
    db = SessionLocal()
    try:
        if kind == "proc":
            rows = (
                db.query(AndamentoProcesso)
                .filter(AndamentoProcesso.processo_id == ref_id)
                .filter(AndamentoProcesso.created_at >= cutoff)
                .order_by(AndamentoProcesso.data_andamento.desc().nullslast())
                .all()
            )
        else:
            rows = (
                db.query(AndamentoTelegramExtra)
                .filter(AndamentoTelegramExtra.extra_id == ref_id)
                .filter(AndamentoTelegramExtra.created_at >= cutoff)
                .order_by(AndamentoTelegramExtra.data_andamento.desc().nullslast())
                .all()
            )
        # Destacha do session pra usar fora do db.close
        for r in rows:
            db.expunge(r)
        return rows
    finally:
        db.close()


def _push_doc_url(a) -> str | None:
    """Retorna a URL pra baixar o documento do andamento (PDPJ hrefBinario).

    Só os AndamentoTelegramExtra (avulsos) têm arquivo_url. Os AndamentoProcesso
    (escritório) já tiveram o arquivo baixado e estão em arquivo_path/drive_link.
    """
    return getattr(a, "arquivo_url", None)


def _push_tem_doc(a) -> bool:
    # AndamentoProcesso (escritório) — NÃO tem arquivo_url (model diferente!)
    if hasattr(a, "arquivo_drive_link"):
        return bool(a.arquivo_drive_link or a.arquivo_path or a.arquivo_nome)
    # AndamentoTelegramExtra (avulsos) — tem arquivo_url, sem drive_link
    return bool(getattr(a, "arquivo_url", None) or getattr(a, "arquivo_nome", None))


async def _send_push_andamentos(bot: Bot, chat_id: int, kind: str, ref_id: str, page: int = 0) -> None:
    """Mostra andamentos paginados (10/página) com botões 'Ver próximos' e
    'Quero os documentos desta página'."""
    key = (chat_id, kind, ref_id)
    rows = _push_cache.get(key)
    if rows is None or page == 0:
        rows = _carregar_push_andamentos(kind, ref_id)
        _push_cache[key] = rows

    if not rows:
        await bot.send_message(chat_id, "Sem andamentos recentes para esse processo.")
        return

    total = len(rows)
    start = page * _PUSH_PAGE
    items = rows[start: start + _PUSH_PAGE]
    if not items:
        await bot.send_message(chat_id, "Não há mais andamentos.")
        return

    linhas = [f"📋 *Andamentos {start + 1}–{start + len(items)} de {total}:*\n"]
    for i, a in enumerate(items, start + 1):
        data = a.data_andamento.strftime("%d/%m/%Y") if a.data_andamento else "—"
        tipo = f"  __{a.tipo}__\n" if getattr(a, "tipo", None) else ""
        desc = (a.descricao or "").strip()
        if len(desc) > 350:
            desc = desc[:347] + "…"
        marca = " 📎" if _push_tem_doc(a) else ""
        linhas.append(f"*{i}.* 📅 {data}{marca}\n{tipo}{desc}\n")

    botoes: list[list[InlineKeyboardButton]] = []
    # Doc da página (só se algum item da página tem)
    if any(_push_tem_doc(a) for a in items):
        botoes.append([InlineKeyboardButton(
            text="📄 Quero os documentos desta página",
            callback_data=f"apvd:{kind[0]}:{ref_id}:{page}",
        )])
    # Paginação
    remaining = total - (start + len(items))
    if remaining > 0:
        botoes.append([InlineKeyboardButton(
            text=f"↓ Ver próximos {min(remaining, _PUSH_PAGE)} ({remaining} restantes)",
            callback_data=f"apv:{kind}:{ref_id}:{page + 1}",
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=botoes) if botoes else None
    await _safe_send(bot, chat_id, "\n".join(linhas), reply_markup=kb)


async def _send_push_documentos(bot: Bot, chat_id: int, kind: str, ref_id: str, page: int) -> None:
    """Envia os documentos dos andamentos da página informada."""
    from app.services.consulta_processual.pdpj import baixar_documento_jusbr

    key = (chat_id, kind, ref_id)
    rows = _push_cache.get(key)
    if rows is None:
        rows = _carregar_push_andamentos(kind, ref_id)
        _push_cache[key] = rows

    start = page * _PUSH_PAGE
    items = rows[start: start + _PUSH_PAGE]
    docs = [(i, a) for i, a in enumerate(items) if _push_tem_doc(a)]
    if not docs:
        await bot.send_message(chat_id, "Nenhum documento nesta página.")
        return

    # Sessão jus.br — pra extras pode ser id=1 (lexops) também, ambos têm acesso.
    sess = andamentos_auth.load_session()
    if not sess:
        # tenta a sessão do lexops (id=1) como fallback
        from app.services.consulta_processual.jusbr_session import load_session as load_lexops
        sess = load_lexops()
    if not sess:
        await bot.send_message(chat_id, "❌ Sessão jus.br inativa. Use /login.")
        return

    await bot.send_message(chat_id, f"⏳ Buscando {len(docs)} documento(s)...")
    for rel_i, a in docs:
        abs_i = start + rel_i + 1
        data_str = a.data_andamento.strftime("%d/%m/%Y") if a.data_andamento else "—"
        caption = f"*{abs_i}.* 📅 {data_str}\n{(a.descricao or '')[:200]}"

        # AndamentoProcesso (escritório) — já foi baixado pelo lexops: tem
        # drive_link e/ou arquivo_path local. Não baixamos de novo do PDPJ.
        if hasattr(a, "arquivo_drive_link"):
            arquivo_nome = a.arquivo_nome or "documento.pdf"
            if a.arquivo_drive_link:
                # Manda o link Drive (clicável). É o caminho mais leve.
                await _safe_send(
                    bot, chat_id,
                    f"{caption}\n\n📎 *{arquivo_nome}*\n{a.arquivo_drive_link}",
                )
                continue
            if a.arquivo_path:
                # Documento existe local — tenta ler e enviar
                try:
                    from pathlib import Path
                    p = Path(a.arquivo_path)
                    if p.exists() and p.is_file():
                        content = p.read_bytes()
                        filename, tipo = _nome_documento(content, None, arquivo_nome, abs_i)
                        dica = {"PDF": None, "RTF": "abra no Word / Pages", "HTML": "abra no navegador"}.get(tipo)
                        cap = caption if not dica else f"{caption}\n_({tipo} — {dica})_"
                        try:
                            await bot.send_document(chat_id, document=BufferedInputFile(content, filename=filename), caption=cap, parse_mode="Markdown")
                        except TelegramBadRequest:
                            await bot.send_document(chat_id, document=BufferedInputFile(content, filename=filename), caption=cap)
                        continue
                except Exception:
                    logger.exception("Erro lendo arquivo local %s", a.arquivo_path)
            await bot.send_message(chat_id, f"⚠️ Andamento {abs_i}: documento ainda não baixado pelo lexops. Use o sync manual.")
            continue

        # AndamentoTelegramExtra (avulso) — usa hrefBinario do PDPJ
        url = _push_doc_url(a)
        if not url:
            await bot.send_message(chat_id, f"⚠️ Andamento {abs_i}: sem URL de documento.")
            continue
        try:
            result = await baixar_documento_jusbr(url, token=sess.get("token"), session_data=sess)
        except Exception as exc:
            await bot.send_message(chat_id, f"❌ Erro doc {abs_i}: {str(exc)[:120]}")
            continue
        if not result:
            await bot.send_message(chat_id, f"⚠️ Documento {abs_i} indisponível.")
            continue
        content, mimetype = result
        filename, tipo = _nome_documento(content, mimetype, a.arquivo_nome, abs_i)
        dica = {"PDF": None, "RTF": "abra no Word / Pages", "HTML": "abra no navegador"}.get(tipo)
        cap = caption if not dica else f"{caption}\n_({tipo} — {dica})_"
        try:
            await bot.send_document(chat_id, document=BufferedInputFile(content, filename=filename), caption=cap, parse_mode="Markdown")
        except TelegramBadRequest:
            await bot.send_document(chat_id, document=BufferedInputFile(content, filename=filename), caption=cap)


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

    @dp.message(Command("busca"))
    async def cmd_busca(msg: Message, command: CommandObject) -> None:
        """`/busca <cnj>` busca andamentos no jus.br. Aceita CNJ formatado OU 20
        dígitos corridos. (Listar processos cadastrados: use `/lista`.)"""
        if not _allowed(msg.from_user.id):
            return
        arg = (command.args or "").strip()
        if not arg:
            await msg.answer(
                "Use `/busca <cnj>` (formatado ou 20 dígitos).\n"
                "Pra listar todos os processos cadastrados: `/lista`.",
                parse_mode="Markdown",
            )
            return
        cnj = _extract_cnj(arg)
        if not cnj:
            await msg.answer(
                "Não reconheci como CNJ. Ex: `0001234-56.2023.8.26.0100` ou 20 dígitos corridos.",
                parse_mode="Markdown",
            )
            return
        await _run_lookup(msg.bot, msg.chat.id, cnj)

    @dp.message(Command("chatid"))
    async def cmd_chatid(msg: Message) -> None:
        # Sem _allowed: precisa funcionar em grupo recém-criado pra capturar o ID.
        chat_type = getattr(msg.chat.type, "value", msg.chat.type)
        await msg.answer(f"chat_id: {msg.chat.id}\ntype: {chat_type}")

    @dp.message(Command("menu"))
    async def cmd_menu(msg: Message) -> None:
        """Força commands no CHAT ATUAL. Em grupos, o botão flutuante azul é
        decisão do cliente do Telegram (não há API pra forçar)."""
        from aiogram.types import BotCommand, BotCommandScopeChat, MenuButtonCommands
        cmds = [BotCommand(command=c, description=d) for c, d in _BOT_COMMANDS]
        chat_type = getattr(msg.chat.type, "value", msg.chat.type)
        try:
            await msg.bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=msg.chat.id))
            if chat_type == "private":
                # set_chat_menu_button só funciona em private chats — em grupos
                # o Telegram retorna "invalid chat_id specified".
                await msg.bot.set_chat_menu_button(
                    chat_id=msg.chat.id,
                    menu_button=MenuButtonCommands(),
                )
                await msg.answer("✅ Menu + botão azul configurados.")
            else:
                await msg.answer(
                    "✅ Comandos registrados neste grupo.\n\n"
                    "*Limitação do Telegram:* o botão azul flutuante (Menu) só pode "
                    "ser forçado em DMs. Em grupos, o cliente do Telegram decide "
                    "quando mostrá-lo. Se ainda não aparecer:\n"
                    "• Force-quit o Telegram e reabra\n"
                    "• Ou abra DM com @jusbr\\_andamentos\\_bot uma vez (`/start`) — "
                    "isso pode \"acordar\" o botão no grupo também\n"
                    "• Os comandos `/...` continuam funcionando normalmente "
                    "(autocomplete ao digitar `/`)",
                    parse_mode="Markdown",
                )
        except Exception as exc:
            logger.exception("cmd_menu falhou")
            await msg.answer(f"❌ Falhou: {str(exc)[:160]}")

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

    @dp.message(Command("add"))
    async def cmd_add(msg: Message, command: CommandObject) -> None:
        if not _allowed(msg.from_user.id):
            return
        cnj = _extract_cnj(command.args or "")
        if not cnj:
            await msg.answer(
                "Use `/add <cnj>` (formatado ou 20 dígitos). Ex: `/add 0001234-56.2024.8.26.0100`.",
                parse_mode="Markdown",
            )
            return
        await _iniciar_add(msg.bot, msg.chat.id, cnj)

    @dp.message(Command("cancelar"))
    async def cmd_cancelar(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        if _add_state.pop(msg.chat.id, None):
            await msg.answer("❌ Cadastro cancelado.")
        else:
            await msg.answer("Nada em andamento pra cancelar.")

    @dp.message(Command("lista"))
    async def cmd_lista(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        await _send_lista_pagina(msg.bot, msg.chat.id, 0, soh_silenciados=False)

    @dp.message(Command("silenciados"))
    async def cmd_silenciados(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        await _send_lista_pagina(msg.bot, msg.chat.id, 0, soh_silenciados=True)

    @dp.message(Command("silenciar"))
    async def cmd_silenciar(msg: Message, command: CommandObject) -> None:
        if not _allowed(msg.from_user.id):
            return
        cnj = _extract_cnj(command.args or "")
        if not cnj:
            await msg.answer("Use `/silenciar <cnj>`.", parse_mode="Markdown")
            return
        ok, label = _set_notificar(cnj, False)
        if not ok:
            await msg.answer(f"❌ `{cnj}` não encontrado no lexops nem nos seus monitorados.", parse_mode="Markdown")
            return
        await msg.answer(f"🔕 Silenciado: *{label}* (`{cnj}`).", parse_mode="Markdown")

    @dp.message(Command("ativar"))
    async def cmd_ativar(msg: Message, command: CommandObject) -> None:
        if not _allowed(msg.from_user.id):
            return
        cnj = _extract_cnj(command.args or "")
        if not cnj:
            await msg.answer("Use `/ativar <cnj>`.", parse_mode="Markdown")
            return
        ok, label = _set_notificar(cnj, True)
        if not ok:
            await msg.answer(f"❌ `{cnj}` não encontrado. Use `/add` se for um CNJ novo.", parse_mode="Markdown")
            return
        await msg.answer(f"🔔 Reativado: *{label}* (`{cnj}`).", parse_mode="Markdown")

    @dp.message(F.text)
    async def text_handler(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        text = msg.text or ""
        chat_id = msg.chat.id

        # State machine do /add — prioridade total enquanto ativo
        if chat_id in _add_state:
            if await _continuar_add(msg.bot, chat_id, text):
                return

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
            pendente = _pending_cnj.pop(chat_id, None)
            if pendente:
                if pendente.startswith("__addcnj__"):
                    await _iniciar_add(msg.bot, chat_id, pendente.removeprefix("__addcnj__"))
                else:
                    await _run_lookup(msg.bot, chat_id, pendente)
            return

        # Texto não reconhecido. Se tem MUITOS dígitos, dica de CNJ.
        import re as _re
        n_digits = len(_re.findall(r"\d", text))
        if n_digits >= 12:
            await msg.answer(
                f"Não reconheci como CNJ ({n_digits} dígitos detectados; CNJ tem 20). "
                "Confere o número, ou tente colar formatado: `NNNNNNN-DD.AAAA.J.TT.OOOO`.",
                parse_mode="Markdown",
            )

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

    @dp.callback_query(F.data.startswith("alistg:"))
    async def cb_lista_pagina(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        offset = int(query.data.split(":", 1)[1])
        await query.answer()
        await _send_lista_pagina(query.bot, query.message.chat.id, offset, soh_silenciados=False)

    @dp.callback_query(F.data.startswith("alistsil:"))
    async def cb_silenciados_pagina(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        offset = int(query.data.split(":", 1)[1])
        await query.answer()
        await _send_lista_pagina(query.bot, query.message.chat.id, offset, soh_silenciados=True)

    @dp.callback_query(F.data.startswith("atoggle:"))
    async def cb_toggle(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        _, kind, ref_id = query.data.split(":", 2)
        ok, label, novo = _toggle_notificar(kind, ref_id)
        if not ok:
            await query.answer("Não encontrei.")
            return
        msg = f"🔔 {label}: agora notifica" if novo else f"🔕 {label}: silenciado"
        await query.answer(msg, show_alert=False)

    @dp.callback_query(F.data.startswith("apart:"))
    async def cb_partes(query: CallbackQuery) -> None:
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        _, kind, ref_id = query.data.split(":", 2)
        await query.answer()
        await _send_partes(query.bot, query.message.chat.id, kind, ref_id)

    @dp.callback_query(F.data.startswith("apv:"))
    async def cb_push_view(query: CallbackQuery) -> None:
        """Push diário: 'Ver andamentos' (paginado 10/pág)."""
        logger.info(
            "apv: chat=%s user=%s data=%r",
            query.message.chat.id if query.message else "?",
            query.from_user.id if query.from_user else "?",
            query.data,
        )
        if not _allowed(query.from_user.id):
            await query.answer("Usuário não autorizado neste bot.", show_alert=True)
            return
        try:
            parts = query.data.split(":")
            kind = parts[1]
            ref_id = parts[2]
            page = int(parts[3]) if len(parts) > 3 else 0
            await query.answer()
            await _send_push_andamentos(query.bot, query.message.chat.id, kind, ref_id, page)
        except Exception as exc:
            logger.exception("cb_push_view falhou (chat=%s)", query.message.chat.id if query.message else "?")
            try:
                await query.bot.send_message(
                    query.message.chat.id,
                    f"❌ Erro ao carregar andamentos: {str(exc)[:200]}",
                )
            except Exception:
                pass

    @dp.callback_query(F.data.startswith("apvd:"))
    async def cb_push_docs(query: CallbackQuery) -> None:
        """Push diário: documentos da página atual."""
        if not _allowed(query.from_user.id):
            await query.answer()
            return
        _, kind_short, ref_id, page_str = query.data.split(":", 3)
        kind = "proc" if kind_short == "p" else "extra"
        await query.answer("⏳ Buscando…")
        await _send_push_documentos(query.bot, query.message.chat.id, kind, ref_id, int(page_str))

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

            content, mimetype = result
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("DOC_DIAG #%d cnj=%s | %s", abs_i, cnj, _diagnostico_doc(content, mimetype, a.arquivo_nome))
            filename, tipo = _nome_documento(content, mimetype, a.arquivo_nome, abs_i)
            # Avisa quando o documento não é PDF — assim você sabe que precisa de
            # outro app pra abrir (RTF/HTML não abrem em leitor de PDF).
            _ABERTURA = {
                "PDF": None,
                "RTF": "abra no Word / Pages / qualquer editor de texto",
                "HTML": "abra no navegador",
            }
            dica = _ABERTURA.get(tipo)
            cap = caption if not dica else f"{caption}\n_({tipo} — {dica})_"
            doc = BufferedInputFile(content, filename=filename)
            try:
                await query.bot.send_document(chat_id, document=doc, caption=cap, parse_mode="Markdown")
            except TelegramBadRequest:
                doc = BufferedInputFile(content, filename=filename)
                await query.bot.send_document(chat_id, document=doc, caption=cap)

    return dp


_BOT_COMMANDS = [
    ("busca", "Buscar andamentos por CNJ (formatado ou 20 dígitos)"),
    ("lista", "Listar todos os processos monitorados"),
    ("add", "Adicionar um CNJ avulso ao monitoramento"),
    ("silenciar", "Silenciar push diário de um CNJ"),
    ("ativar", "Reativar push diário de um CNJ"),
    ("silenciados", "Ver só os processos com push desligado"),
    ("login", "Revalidar o acesso jus.br (gov.br)"),
    ("sessao", "Status da sessão jus.br"),
    ("chatid", "Mostra o id do chat atual (setup do grupo)"),
    ("help", "Ajuda completa"),
    ("cancelar", "Aborta um cadastro em andamento"),
]


async def _setup_bot_commands(bot: Bot) -> None:
    """Registra a lista de comandos + força o Menu button (botão azul flutuante).

    Em DMs o menu aparece sozinho; em grupos o Telegram só mostra o botão
    flutuante se a gente explicitar via set_chat_menu_button(MenuButtonCommands).
    Registramos commands em 3 escopos pra garantir visibilidade em qualquer chat.
    """
    from aiogram.types import (
        BotCommand,
        BotCommandScopeAllGroupChats,
        BotCommandScopeAllPrivateChats,
        BotCommandScopeDefault,
        MenuButtonCommands,
    )

    cmds = [BotCommand(command=c, description=d) for c, d in _BOT_COMMANDS]
    try:
        for scope in (BotCommandScopeDefault(), BotCommandScopeAllPrivateChats(), BotCommandScopeAllGroupChats()):
            await bot.set_my_commands(cmds, scope=scope)
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Bot commands + Menu button registrados em todos os escopos (%d cmds).", len(cmds))
    except Exception:
        logger.exception("Falha ao registrar bot commands / menu button")


async def run_polling(token: str, dispatcher: Dispatcher) -> None:
    bot = Bot(token=token)
    try:
        await _setup_bot_commands(bot)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
