"""Alerta de novo andamento/documento do Autos IA — Telegram + e-mail.

Roda logo depois de cada sincronização agendada do caso (7h10, 13h10 e 19h10 BRT,
ver scheduler._sync_autos_ia_processos). Nesse ponto as peças novas já foram
importadas E resumidas (importar_andamentos_pendentes só retorna depois do
resumo), então o alerta já sai com "quem protocolou" e o resumo curto.

- Telegram: 1 mensagem por processo no MESMO bot/grupo do push diário de
  andamentos (andamentos_push), com o botão "Ver andamentos" que já existe
  (callback `apv:proc:<processo_id>`) — de lá sai a opção de baixar os documentos,
  exatamente como no push das 19h. Andamentos que o push das 19h já avisou não
  são repetidos (e os avisados aqui não são repetidos pelo push das 19h).
- E-mail: lista dos documentos protocolados, agrupados por protocolo (petição +
  anexos), com resumo de ~2 linhas por protocolo.

Controle de "já alertei": AutosIAPeca.alerta_telegram_em / alerta_email_em, um por
canal. Um canal que falha continua pendente e é tentado de novo na próxima
rodada, sem reenviar o que o outro canal já mandou. A migração marca todo o
histórico como já alertado, e peças de andamentos com data antiga (> 14 dias)
também são só marcadas, sem envio — importação em lote não pode virar spam.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, defer

from app.config import settings
from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIAPeca
from app.models.cliente import Cliente
from app.models.processo import Processo

logger = logging.getLogger(__name__)

_BRT = ZoneInfo("America/Sao_Paulo")
# Mesma regra do push diário: andamento com data mais antiga que isso é histórico
# retroativo (ex.: backfill de um caso novo) — só marca como alertado, não envia.
JANELA_DIAS = 14
MAX_RESUMO_CHARS = 260
MAX_ANEXOS_EMAIL = 6
MAX_GRUPOS_TELEGRAM = 6

NOME_TIPO = {
    "peticao": "Petição", "decisao": "Decisão", "despacho": "Despacho", "certidao": "Certidão",
    "oficio": "Ofício", "recurso": "Recurso", "documento": "Documento", "outro": "Outro",
}
# Mesma paleta do grafo/lista de documentos do Autos IA.
COR_TIPO = {
    "peticao": "#2a78d6", "decisao": "#eb6834", "despacho": "#1baf7a", "certidao": "#eda100",
    "oficio": "#e87ba4", "recurso": "#008300", "documento": "#4a3aa7", "outro": "#e34948",
}
_DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


# ── Modelo (snapshot sem vínculo com a sessão do banco) ──────────────────────

@dataclass
class ItemPeca:
    id: object
    tipo: str
    titulo: str
    autor: str | None
    data: date | None
    hora: str | None  # "HH:MM" em Brasília
    resumo: str
    lida: bool
    drive_link: str | None
    arquivo_nome: str | None
    andamento_id: object
    andamento_notificado: bool
    ordem: int = 0  # pagina_inicio, pra manter a ordem dos autos dentro do protocolo


@dataclass
class Grupo:
    principal: ItemPeca
    anexos: list[ItemPeca] = field(default_factory=list)

    @property
    def total_docs(self) -> int:
        return 1 + len(self.anexos)


@dataclass
class AlertaCaso:
    caso_id: object
    caso_nome: str
    processo_id: object
    cliente: str | None
    cnj: str | None
    local: str  # "TJES · 1ª Vara · Vitória"
    materia: str | None
    grupos: list[Grupo]
    teste: bool = False

    @property
    def total_docs(self) -> int:
        return sum(g.total_docs for g in self.grupos)

    @property
    def total_decisoes(self) -> int:
        return sum(1 for g in self.grupos if g.principal.tipo == "decisao")


# ── Utilidades de texto ──────────────────────────────────────────────────────

def _limpar_markdown(texto: str) -> str:
    texto = re.sub(r"[*_`#>]+", " ", texto or "")
    return re.sub(r"\s+", " ", texto).strip()


def resumo_curto(texto: str | None, max_chars: int = MAX_RESUMO_CHARS) -> str:
    """Até 2 frases do resumo, limitado a ~260 caracteres (≈ 2 linhas no e-mail),
    cortando em fronteira de palavra."""
    limpo = _limpar_markdown(texto or "")
    if not limpo:
        return ""
    frases = re.split(r"(?<=[.!?])\s+", limpo)
    saida = " ".join(frases[:2])
    if len(saida) <= max_chars:
        return saida
    corte = saida[:max_chars].rsplit(" ", 1)[0].rstrip(",;:- ")
    return corte + "…"


def _hora_brt(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_BRT).strftime("%H:%M")


def _data_extenso(d: date | None) -> str:
    if not d:
        return "Sem data"
    return f"{_DIAS_SEMANA[d.weekday()].capitalize()}, {d.strftime('%d/%m/%Y')}"


def _url_app(caso_id) -> str | None:
    base = (settings.frontend_url or "").rstrip("/")
    if not base.startswith("https://"):
        base = "https://lexops.fly.dev"  # frontend_url local/dev não serve de link num e-mail/Telegram
    return f"{base}/autos-ia/{caso_id}"


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _md(s: str | None) -> str:
    """Escapa o que o Markdown legado do Telegram interpreta (descrições/resumos
    de peça têm `_`, `*` e crases soltos o tempo todo)."""
    return re.sub(r"([_*`\[])", r"\\\1", s or "")


# ── Coleta ───────────────────────────────────────────────────────────────────

def _item(peca: AutosIAPeca, andamento: AndamentoProcesso) -> ItemPeca:
    lida = peca.status == "resumida" and not peca.erro_mensagem
    resumo = resumo_curto(peca.resumo) if lida else ""
    if not resumo:
        # Sem leitura/resumo: cai pra descrição do andamento — melhor que linha vazia.
        resumo = resumo_curto(andamento.descricao)
    return ItemPeca(
        id=peca.id,
        tipo=peca.tipo if peca.tipo in NOME_TIPO else "outro",
        titulo=(peca.titulo_customizado or peca.titulo or "Documento").strip(),
        autor=peca.autor,
        data=andamento.data_andamento or peca.data_peca,
        hora=_hora_brt(andamento.protocolado_em),
        resumo=resumo,
        lida=lida,
        drive_link=andamento.arquivo_drive_link,
        arquivo_nome=andamento.arquivo_nome,
        andamento_id=andamento.id,
        andamento_notificado=bool(andamento.notificado),
        ordem=peca.pagina_inicio or 0,
    )


def _pares_do_caso(db: Session, caso_id):
    return (
        db.query(AutosIAPeca, AndamentoProcesso)
        .options(defer(AutosIAPeca.texto_md))
        .join(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
        .filter(AutosIAPeca.caso_id == caso_id)
    )


def _montar_alerta(db: Session, caso: AutosIACaso, pares: list[tuple[AutosIAPeca, AndamentoProcesso]], teste: bool = False) -> AlertaCaso | None:
    """Agrupa as peças por protocolo (petição + anexos), como na aba Documentos."""
    if not pares:
        return None
    por_id = {p.id: (p, a) for p, a in pares}

    # Principal de cada peça. Se só um ANEXO é novo e o pai não está na lista,
    # busca o pai pra ter o cabeçalho do protocolo.
    pais_faltando = {p.peca_pai_id for p, _ in pares if p.peca_pai_id and p.peca_pai_id not in por_id}
    pais: dict = {}
    if pais_faltando:
        for p, a in _pares_do_caso(db, caso.id).filter(AutosIAPeca.id.in_(pais_faltando)).all():
            pais[p.id] = (p, a)

    grupos: dict = {}
    for peca, andamento in pares:
        raiz_id = peca.peca_pai_id or peca.id
        if raiz_id not in grupos:
            raiz = por_id.get(raiz_id) or pais.get(raiz_id)
            if raiz is None:  # pai sem andamento/ausente: trata a própria peça como principal
                raiz_id = peca.id
                raiz = (peca, andamento)
            grupos[raiz_id] = Grupo(principal=_item(*raiz))
        grupo = grupos[raiz_id]
        if peca.id != grupo.principal.id:
            grupo.anexos.append(_item(peca, andamento))

    for g in grupos.values():
        g.anexos.sort(key=lambda i: i.ordem)

    ordenados = sorted(
        grupos.values(),
        key=lambda g: (g.principal.data or date.min, g.principal.hora or "", g.principal.ordem),
        reverse=True,  # mais novo primeiro, como a aba Documentos
    )

    processo = db.query(Processo).filter(Processo.id == caso.processo_id).first() if caso.processo_id else None
    cliente = None
    if processo is not None and processo.cliente_id:
        cliente = db.query(Cliente.nome).filter(Cliente.id == processo.cliente_id).scalar()
    local = " · ".join(x for x in [
        getattr(processo, "tribunal", None) or "", getattr(processo, "vara", None) or "", getattr(processo, "comarca", None) or "",
    ] if x)
    return AlertaCaso(
        caso_id=caso.id, caso_nome=caso.nome, processo_id=caso.processo_id, cliente=cliente,
        cnj=getattr(processo, "numero_cnj", None) or caso.numero_processo, local=local,
        materia=getattr(processo, "materia", None), grupos=ordenados, teste=teste,
    )


# ── Telegram ─────────────────────────────────────────────────────────────────

def montar_texto_telegram(alerta: AlertaCaso) -> str:
    n_prot = len(alerta.grupos)
    cab = "🧪 *TESTE — Autos IA*" if alerta.teste else "🆕 *Autos IA — novo andamento*"
    linhas = [cab]
    linhas.append(f"⚖️ *{_md(alerta.cliente or alerta.caso_nome)}*")
    if alerta.cnj:
        linhas.append(f"📋 `{alerta.cnj}`")
    if alerta.local:
        linhas.append(f"🏛️ {_md(alerta.local)}")
    resumo_qtd = f"📨 {alerta.total_docs} documento(s) em {n_prot} protocolo(s)"
    if alerta.total_decisoes:
        resumo_qtd += f" · ⚠️ {alerta.total_decisoes} decisão(ões)"
    linhas.append(resumo_qtd)
    linhas.append("")

    for g in alerta.grupos[:MAX_GRUPOS_TELEGRAM]:
        p = g.principal
        quando = (p.data.strftime("%d/%m") if p.data else "—") + (f" {p.hora}" if p.hora else "")
        quem = f" · {_md(p.autor)}" if p.autor else ""
        extra = f" (+{len(g.anexos)} anexo(s))" if g.anexos else ""
        linhas.append(f"• *{quando}* — {NOME_TIPO.get(p.tipo, 'Outro')}{quem}{extra}")
        linhas.append(f"  {_md(p.titulo[:120])}")
        if p.resumo:
            linhas.append(f"  _{_md(resumo_curto(p.resumo, 150))}_")
    restantes = len(alerta.grupos) - MAX_GRUPOS_TELEGRAM
    if restantes > 0:
        linhas.append(f"… e mais {restantes} protocolo(s) — veja no botão abaixo.")
    return "\n".join(linhas)[:3900]


async def _enviar_telegram_async(alerta: AlertaCaso) -> bool:
    chat_raw = (settings.andamentos_push_chat_id or "").strip()
    token = settings.andamentos_bot_token
    if not chat_raw or not token:
        logger.warning("Autos IA alerta: Telegram não configurado (chat/token) — pulando.")
        return False
    from aiogram import Bot
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    texto = montar_texto_telegram(alerta)
    botoes = [[InlineKeyboardButton(
        text=f"📋 Ver andamentos e baixar documentos ({alerta.total_docs})",
        callback_data=f"apv:proc:{alerta.processo_id}",  # fluxo que já existe no bot (documentos via Drive)
    )]]
    url = _url_app(alerta.caso_id)
    if url:
        botoes.append([InlineKeyboardButton(text="🔗 Abrir no Autos IA", url=url)])
    kb = InlineKeyboardMarkup(inline_keyboard=botoes)

    bot = Bot(token=token)
    try:
        try:
            await bot.send_message(int(chat_raw), texto, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            # Algum caractere ainda quebrou o Markdown: reenvia em texto puro em vez de perder o alerta.
            await bot.send_message(int(chat_raw), texto.replace("\\", "").replace("*", "").replace("`", ""), reply_markup=kb)
        return True
    finally:
        await bot.session.close()


def enviar_telegram(alerta: AlertaCaso) -> bool:
    try:
        return asyncio.run(_enviar_telegram_async(alerta))
    except Exception:
        logger.exception("Autos IA alerta: falha ao enviar Telegram (caso %s)", alerta.caso_id)
        return False


# ── E-mail ───────────────────────────────────────────────────────────────────

def _badge(tipo: str) -> str:
    cor = COR_TIPO.get(tipo, "#6b7280")
    return (
        f'<span style="display:inline-block;background:{cor};color:#ffffff;font-size:10px;font-weight:700;'
        f'letter-spacing:.4px;text-transform:uppercase;padding:2px 8px;border-radius:10px;">{_esc(NOME_TIPO.get(tipo, "Outro"))}</span>'
    )


def _bloco_grupo(g: Grupo) -> str:
    p = g.principal
    cor = COR_TIPO.get(p.tipo, "#6b7280")
    hora = f'<span style="font-size:12px;font-weight:700;color:#374151;">{_esc(p.hora)}</span> &nbsp;' if p.hora else ""
    quem = f'<span style="font-size:12px;color:#4b5563;">{_esc(p.autor)}</span>' if p.autor else ""
    resumo = p.resumo or "(sem resumo — documento ainda não lido)"
    cor_resumo = "#374151" if p.resumo else "#9ca3af"
    nota_nao_lida = (
        ' <span style="color:#b45309;font-size:11px;">(texto do andamento — documento ainda não lido pela IA)</span>'
        if p.resumo and not p.lida else ""
    )
    link_principal = (
        f'&nbsp;<a href="{_esc(p.drive_link)}" style="color:{cor};font-size:12px;font-weight:700;text-decoration:none;">abrir ↗</a>'
        if p.drive_link else ""
    )
    linhas_anexos = ""
    if g.anexos:
        itens = []
        for a in g.anexos[:MAX_ANEXOS_EMAIL]:
            nome = _esc((a.titulo or a.arquivo_nome or "Documento")[:90])
            link = (
                f'<a href="{_esc(a.drive_link)}" style="color:#2a78d6;text-decoration:none;">{nome} ↗</a>'
                if a.drive_link else nome
            )
            itens.append(f'<tr><td style="padding:3px 0;font-size:12px;color:#374151;line-height:1.4;">📎 {link}</td></tr>')
        if len(g.anexos) > MAX_ANEXOS_EMAIL:
            itens.append(
                f'<tr><td style="padding:3px 0;font-size:12px;color:#6b7280;">+ {len(g.anexos) - MAX_ANEXOS_EMAIL} '
                f'outro(s) documento(s) deste protocolo</td></tr>'
            )
        linhas_anexos = (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;'
            'border-top:1px solid #e5e7eb;padding-top:6px;">'
            f'<tr><td style="padding:6px 0 2px;font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;'
            f'letter-spacing:.4px;">{len(g.anexos)} anexo(s)</td></tr>' + "".join(itens) + "</table>"
        )
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 10px;background:#ffffff;border:1px solid #e5e7eb;border-left:4px solid {cor};border-radius:8px;">
  <tr><td style="padding:12px 14px;">
    <div style="margin-bottom:4px;">{hora}{_badge(p.tipo)} &nbsp;{quem}</div>
    <div style="font-size:14px;font-weight:700;color:#111827;line-height:1.35;">{_esc(p.titulo[:160])}{link_principal}</div>
    <div style="font-size:13px;color:{cor_resumo};line-height:1.45;margin-top:4px;">{_esc(p.resumo or resumo)}{nota_nao_lida}</div>
    {linhas_anexos}
  </td></tr>
</table>"""


def montar_email(alerta: AlertaCaso) -> tuple[str, str]:
    """(assunto, html). Layout em tabelas com CSS inline — é o que os clientes de
    e-mail renderizam de forma confiável (Gmail/Outlook/Apple Mail)."""
    n_prot = len(alerta.grupos)
    prefixo = "[TESTE] " if alerta.teste else ""
    assunto = f"{prefixo}Autos IA · {alerta.total_docs} novo(s) documento(s) — {alerta.cliente or alerta.caso_nome}"
    if alerta.total_decisoes:
        assunto += f" · {alerta.total_decisoes} decisão(ões)"

    por_dia: dict = {}
    for g in alerta.grupos:
        por_dia.setdefault(g.principal.data, []).append(g)
    secoes = []
    for dia, grupos in por_dia.items():
        secoes.append(
            f'<div style="font-size:12px;font-weight:700;color:#1f4e4f;text-transform:uppercase;letter-spacing:.5px;'
            f'margin:18px 0 8px;">{_esc(_data_extenso(dia))}</div>' + "".join(_bloco_grupo(g) for g in grupos)
        )

    chips = [f"<b>{alerta.total_docs}</b> documento(s)", f"<b>{n_prot}</b> protocolo(s)"]
    if alerta.total_decisoes:
        chips.append(f'<b style="color:#eb6834;">{alerta.total_decisoes}</b> decisão(ões)')
    chips_html = " &nbsp;·&nbsp; ".join(chips)
    url = _url_app(alerta.caso_id)
    botao = (
        f'<a href="{_esc(url)}" style="display:inline-block;background:#377E7F;color:#ffffff;font-size:13px;font-weight:700;'
        f'text-decoration:none;padding:10px 18px;border-radius:8px;">Abrir no Autos IA</a>'
    ) if url else ""
    faixa_teste = (
        '<div style="background:#fef3c7;color:#92400e;font-size:12px;font-weight:700;padding:8px 14px;text-align:center;">'
        "E-MAIL DE TESTE — com as últimas peças do caso; nada foi marcado como enviado.</div>"
    ) if alerta.teste else ""
    local = f'<div style="font-size:12px;color:#cfe3e3;margin-top:2px;">{_esc(alerta.local)}</div>' if alerta.local else ""
    cnj = f'<div style="font-size:12px;color:#cfe3e3;margin-top:6px;font-family:Consolas,Menlo,monospace;">{_esc(alerta.cnj)}</div>' if alerta.cnj else ""
    materia = f'<div style="font-size:12px;color:#cfe3e3;margin-top:2px;">{_esc((alerta.materia or "")[:200])}</div>' if alerta.materia else ""

    corpo = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#eef1f1;font-family:Arial,Helvetica,sans-serif;color:#1f2933;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{_esc(f"{alerta.total_docs} documento(s) novo(s) em {alerta.caso_nome}")}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f1;">
<tr><td align="center" style="padding:22px 10px;">
  <table role="presentation" width="680" cellpadding="0" cellspacing="0" style="width:100%;max-width:680px;">
    <tr><td style="background:#1f4e4f;border-radius:12px 12px 0 0;padding:20px 22px;">
      <div style="font-size:11px;font-weight:700;letter-spacing:1px;color:#9fd0cf;text-transform:uppercase;">Autos IA · novo andamento</div>
      <div style="font-size:20px;font-weight:700;color:#ffffff;margin-top:6px;line-height:1.25;">{_esc(alerta.cliente or alerta.caso_nome)}</div>
      {cnj}{local}{materia}
    </td></tr>
    <tr><td style="background:#f8fafa;padding:0;">{faixa_teste}</td></tr>
    <tr><td style="background:#f8fafa;padding:16px 22px 6px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="font-size:13px;color:#374151;">{chips_html}</td>
        <td align="right">{botao}</td>
      </tr></table>
      {"".join(secoes)}
    </td></tr>
    <tr><td style="background:#f8fafa;border-radius:0 0 12px 12px;padding:14px 22px 20px;">
      <div style="font-size:11px;color:#9ca3af;line-height:1.5;border-top:1px solid #e5e7eb;padding-top:12px;">
        Gerado automaticamente pelo Gestor Jurídico após a sincronização do jus.br. Os resumos são feitos por IA —
        confira o documento antes de se basear neles. Os links abrem o arquivo no Google Drive.
      </div>
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""
    return assunto, corpo


def enviar_email(alerta: AlertaCaso) -> bool:
    destino = (settings.autos_ia_alerta_email or "").strip()
    if not destino:
        logger.warning("Autos IA alerta: e-mail de destino não configurado — pulando.")
        return False
    try:
        from app.services.email_service import _send_via_gmail_oauth
        assunto, corpo = montar_email(alerta)
        _send_via_gmail_oauth(destino, assunto, corpo)
        return True
    except Exception:
        logger.exception("Autos IA alerta: falha ao enviar e-mail (caso %s)", alerta.caso_id)
        return False


# ── Orquestração ─────────────────────────────────────────────────────────────

def _marcar(peca_ids: list, *, telegram: bool = False, email: bool = False, andamentos_notificados: list | None = None) -> None:
    """Grava os controles numa sessão curta e própria (a de leitura pode ter ficado
    parada durante o envio de rede)."""
    if not peca_ids and not andamentos_notificados:
        return
    agora = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        if peca_ids:
            campos = {}
            if telegram:
                campos[AutosIAPeca.alerta_telegram_em] = agora
            if email:
                campos[AutosIAPeca.alerta_email_em] = agora
            if campos:
                db.query(AutosIAPeca).filter(AutosIAPeca.id.in_(peca_ids)).update(campos, synchronize_session=False)
        if andamentos_notificados:
            # Evita o push das 19h repetir no Telegram o que este alerta já avisou.
            db.query(AndamentoProcesso).filter(AndamentoProcesso.id.in_(andamentos_notificados)).update(
                {AndamentoProcesso.notificado: True}, synchronize_session=False
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Autos IA alerta: falha ao gravar controle de envio")
    finally:
        db.close()


def enviar_alertas_pos_sync(caso_id) -> dict:
    """Ponto de entrada do agendador. Nunca lança. Retorna um resumo (pra log/teste)."""
    resumo = {"telegram": 0, "email": 0, "silenciadas": 0}
    if not settings.autos_ia_alerta_ativo:
        return resumo
    try:
        db = SessionLocal()
        try:
            caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
            if not caso or not caso.processo_id:
                return resumo
            corte = date.today() - timedelta(days=JANELA_DIAS)

            def _pendentes(coluna):
                return _pares_do_caso(db, caso.id).filter(coluna.is_(None)).all()

            # Peças sem andamento de origem (upload manual) nunca alertam — e as de
            # data antiga só são marcadas (importação retroativa, não "novidade").
            sem_origem = [
                p.id for p in db.query(AutosIAPeca).options(defer(AutosIAPeca.texto_md)).filter(
                    AutosIAPeca.caso_id == caso.id, AutosIAPeca.andamento_id.is_(None),
                    (AutosIAPeca.alerta_telegram_em.is_(None)) | (AutosIAPeca.alerta_email_em.is_(None)),
                ).all()
            ]
            pend_email = _pendentes(AutosIAPeca.alerta_email_em)
            pend_tel = _pendentes(AutosIAPeca.alerta_telegram_em)

            def _recente(par):
                a = par[1]
                ref = a.data_andamento or (a.protocolado_em.date() if a.protocolado_em else None)
                return ref is None or ref >= corte

            antigas_email = [p.id for p, a in pend_email if not _recente((p, a))]
            antigas_tel = [p.id for p, a in pend_tel if not _recente((p, a))]
            email_recentes = [par for par in pend_email if _recente(par)]
            tel_recentes = [par for par in pend_tel if _recente(par)]
            # Telegram: o que o push das 19h já avisou não repete.
            tel_ja_avisadas = [p.id for p, a in tel_recentes if a.notificado]
            tel_novas = [par for par in tel_recentes if not par[1].notificado]

            alerta_email = _montar_alerta(db, caso, email_recentes)
            alerta_tel = _montar_alerta(db, caso, tel_novas)
        finally:
            db.close()

        _marcar(sem_origem, telegram=True, email=True)
        _marcar(antigas_email, email=True)
        _marcar(antigas_tel, telegram=True)
        _marcar(tel_ja_avisadas, telegram=True)
        resumo["silenciadas"] = len(sem_origem) + len(antigas_email) + len(antigas_tel)

        if alerta_email:
            if enviar_email(alerta_email):
                _marcar([p.id for p, _ in email_recentes], email=True)
                resumo["email"] = alerta_email.total_docs
        if alerta_tel:
            if enviar_telegram(alerta_tel):
                _marcar(
                    [p.id for p, _ in tel_novas], telegram=True,
                    andamentos_notificados=list({a.id for _, a in tel_novas}),
                )
                resumo["telegram"] = alerta_tel.total_docs
        if resumo["email"] or resumo["telegram"]:
            logger.info("Autos IA alerta caso %s: e-mail=%s doc(s), telegram=%s doc(s)", caso_id, resumo["email"], resumo["telegram"])
    except Exception:
        logger.exception("Autos IA alerta: falha inesperada (caso %s) — a sincronização não é afetada", caso_id)
    return resumo


def enviar_alerta_teste(db: Session, caso: AutosIACaso, ultimas: int = 5) -> dict:
    """Manda um alerta (e-mail + Telegram) com os `ultimas` protocolos mais recentes do
    caso, só pra conferir o visual e a entrega. Não altera nenhum controle de envio."""
    pares = (
        _pares_do_caso(db, caso.id)
        .filter(AutosIAPeca.peca_pai_id.is_(None))
        .order_by(AndamentoProcesso.data_andamento.desc().nullslast(), AndamentoProcesso.protocolado_em.desc().nullslast())
        .limit(max(1, min(ultimas, 15)))
        .all()
    )
    ids_principais = [p.id for p, _ in pares]
    if ids_principais:
        anexos = (
            _pares_do_caso(db, caso.id).filter(AutosIAPeca.peca_pai_id.in_(ids_principais)).all()
        )
        pares = pares + anexos
    alerta = _montar_alerta(db, caso, pares, teste=True)
    if not alerta:
        return {"enviado": False, "motivo": "O caso ainda não tem peças vindas do jus.br."}
    ok_email = enviar_email(alerta)
    ok_tel = enviar_telegram(alerta)
    return {"enviado": ok_email or ok_tel, "email": ok_email, "telegram": ok_tel, "documentos": alerta.total_docs, "protocolos": len(alerta.grupos)}
