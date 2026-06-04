"""Telegram bot for process lookup + Playwright viewer endpoints.

Bot: @jusbr_andamentos_bot — long polling, independent of the reembolsos webhook bot.
Viewer: /api/andamentos/viewer/{token} — mobile screenshot UI for gov.br login.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from app.config import settings
from app.services.browser_manager import BrowserManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/andamentos", tags=["andamentos-bot"])

_VIEWER_HTML = (Path(__file__).parent.parent / "static" / "viewer.html").read_text()
_API_BASE = "/api/andamentos"  # full public path (nginx adds /api/ prefix)
_PAGE_SIZE = 5
_CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

# Singleton — injected at startup from main.py
_browser: Optional[BrowserManager] = None


def set_browser_manager(mgr: BrowserManager) -> None:
    global _browser
    _browser = mgr


def get_browser_manager() -> BrowserManager:
    assert _browser is not None, "BrowserManager not initialised"
    return _browser


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


async def _run_lookup(bot: Bot, chat_id: int, cnj: str) -> None:
    from app.services.consulta_processual.jusbr_session import load_session
    from app.services.consulta_processual.pdpj import buscar_via_pdpj
    from app.services.consulta_processual.cnj import inferir_tribunal_pelo_cnj

    tribunal = inferir_tribunal_pelo_cnj(cnj)
    if not tribunal:
        await bot.send_message(chat_id, f"❌ Tribunal não identificado para o CNJ `{cnj}`.", parse_mode="Markdown")
        return

    sess = load_session()
    mgr = get_browser_manager()

    if not sess:
        await bot.send_message(chat_id, "🔐 Sessão jus.br inativa. Gerando QR code de login gov.br...")
        mgr.reset_auth_event()
        await mgr.navigate_to_portal()

        viewer_token, _ = mgr.create_viewer_token()
        link = f"https://lexops.fly.dev/api/andamentos/viewer/{viewer_token}"
        await bot.send_message(
            chat_id,
            f"📱 *Login gov.br via QR code*\n\n"
            f"1. Abra este link no celular:\n{link}\n\n"
            f"2. Abra o *app gov.br* e use o leitor de QR code\n"
            f"3. Aprove o login com sua biometria\n\n"
            f"_Sem senha, sem captcha. O bot continua sozinho após a aprovação. Expira em 10 min._",
            parse_mode="Markdown",
        )
        try:
            await mgr.wait_for_auth(timeout_seconds=600)
        except TimeoutError:
            await bot.send_message(chat_id, "⏰ Timeout. Envie o CNJ novamente para tentar.")
            return
        await bot.send_message(chat_id, "✅ Autenticado! Buscando andamentos...")
        sess = load_session()
        if not sess:
            await bot.send_message(chat_id, "❌ Sessão não encontrada após login. Tente novamente.")
            return
    else:
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
        from app.services.consulta_processual.jusbr_session import session_status
        st = session_status()
        if st["active"]:
            await msg.answer(f"✅ Sessão ativa\nExpira: {st['expires_at']}\nRefresh: {'sim' if st['has_refresh_token'] else 'não'}")
        else:
            await msg.answer("❌ Sem sessão ativa. Envie um CNJ para iniciar autenticação.")

    @dp.message(Command("resetar"))
    async def cmd_resetar(msg: Message) -> None:
        if not _allowed(msg.from_user.id):
            return
        from app.services.consulta_processual.jusbr_session import clear_session
        clear_session()
        await get_browser_manager().reset_session()
        await msg.answer("🗑️ Sessão jus.br limpa.")

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
        m = _CNJ_RE.search(msg.text or "")
        if m:
            await _run_lookup(msg.bot, msg.chat.id, m.group(0))

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

        from app.services.consulta_processual.jusbr_session import load_session
        from app.services.consulta_processual.pdpj import baixar_documento_jusbr
        sess = load_session()

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


# ── FastAPI viewer endpoints (QR-code login) ──────────────────────────────────

_QR_VIEWER_HTML = """<!DOCTYPE html>
<html lang="pt-BR"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Login gov.br — LexOps</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#0d0d0d;color:#e0e0e0;font-family:-apple-system,sans-serif;
       min-height:100dvh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;text-align:center}
  h2{font-size:20px;margin-bottom:8px}
  p{font-size:14px;color:#aaa;margin-bottom:20px;max-width:340px;line-height:1.5}
  #qrbox{background:#fff;border-radius:16px;padding:20px;display:inline-block;min-width:264px;min-height:264px;
         display:flex;align-items:center;justify-content:center}
  #qrbox img{width:224px;height:224px;display:block}
  .spinner{width:40px;height:40px;border:4px solid #333;border-top-color:#2563eb;border-radius:50%;animation:spin 1s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  #status{margin-top:20px;font-size:14px;color:#888}
  .ok{color:#22c55e!important;font-weight:600}
  .steps{margin-top:24px;font-size:13px;color:#777;text-align:left;max-width:320px}
  .steps li{margin:6px 0}
</style></head><body>
  <h2>🏛️ Login gov.br</h2>
  <p>Abra o <strong>app gov.br</strong> no celular, toque no leitor de QR code e aponte para a imagem abaixo.</p>
  <div id="qrbox"><div class="spinner"></div></div>
  <div id="status">Gerando QR code…</div>
  <ol class="steps">
    <li>1. Abra o app <strong>gov.br</strong></li>
    <li>2. Toque no ícone de <strong>QR code</strong></li>
    <li>3. Aponte para o código e aprove com biometria</li>
  </ol>
<script>
  const TOKEN='__VIEWER_TOKEN__', API='__API_BASE__';
  const qrbox=document.getElementById('qrbox'), status=document.getElementById('status');
  let done=false;
  async function poll(){
    if(done) return;
    try{
      const s=await (await fetch(`${API}/auth-status?token=${TOKEN}`)).json();
      if(s.authenticated){
        done=true;
        qrbox.innerHTML='<div style="font-size:64px">✅</div>';
        status.innerHTML='<span class="ok">Login concluído! Voltando ao Telegram…</span>';
        return;
      }
      // refresh QR image
      const r=await fetch(`${API}/qr.png?token=${TOKEN}&t=${Date.now()}`);
      if(r.ok){
        const blob=await r.blob();
        qrbox.innerHTML=`<img src="${URL.createObjectURL(blob)}" alt="QR code"/>`;
        status.textContent='Aguardando aprovação no app gov.br…';
      }
    }catch(e){}
    setTimeout(poll, 2000);
  }
  poll();
</script>
</body></html>"""


@router.get("/viewer/{token}", response_class=HTMLResponse)
async def viewer(token: str):
    if not get_browser_manager().verify_token(token):
        raise HTTPException(status_code=403, detail="Link expirado ou inválido.")
    html = _QR_VIEWER_HTML.replace("__VIEWER_TOKEN__", token).replace("__API_BASE__", _API_BASE)
    return HTMLResponse(html)


@router.get("/qr.png")
async def qr_png(token: str = Query(...)):
    if not get_browser_manager().verify_token(token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    png = get_browser_manager().get_qr_png()
    if not png:
        raise HTTPException(status_code=404, detail="QR ainda não disponível.")
    return Response(content=png, media_type="image/png")


@router.get("/auth-status")
async def auth_status(token: str = Query(...)):
    if not get_browser_manager().verify_token(token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    return {"authenticated": get_browser_manager().auth_event.is_set()}


@router.get("/screenshot.png")
async def screenshot(token: str = Query(...)):
    if not get_browser_manager().verify_token(token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    try:
        png = await get_browser_manager().screenshot_png()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return Response(content=png, media_type="image/png")


class _XY(BaseModel):
    x: int
    y: int
    token: str


class _Text(BaseModel):
    text: str
    token: str


class _Key(BaseModel):
    key: str
    token: str


@router.post("/click")
async def click(p: _XY):
    if not get_browser_manager().verify_token(p.token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    await get_browser_manager().click(p.x, p.y)
    return {"ok": True}


@router.post("/type")
async def type_text(p: _Text):
    if not get_browser_manager().verify_token(p.token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    await get_browser_manager().type_text(p.text)
    return {"ok": True}


@router.post("/key")
async def press_key(p: _Key):
    if not get_browser_manager().verify_token(p.token):
        raise HTTPException(status_code=403, detail="Token inválido.")
    await get_browser_manager().press_key(p.key)
    return {"ok": True}
