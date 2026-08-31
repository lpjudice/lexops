"""Lembrete diário de prazos — e-mail + Telegram, todo dia até o prazo ser tratado.

Regra de quem recebe: o responsável do prazo e os responsáveis das tarefas
ligadas a ele, com cópia obrigatória para `COPIA_OBRIGATORIA`. Se ninguém tiver
e-mail cadastrado, o lembrete ainda sai — só para a cópia obrigatória —, porque
prazo sem dono é justamente o que mais precisa aparecer.

Um prazo só sai do radar quando recebe tratamento (cumprido / perdido /
ignorado / nada a fazer). Vencido e ainda pendente continua sendo cobrado, com
o rótulo VENCIDO, que é o mesmo critério do vermelho na aba Ativo da tela de
Prazos — as duas coisas têm que contar a mesma história.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.cliente import Cliente
from app.models.prazo import Prazo
from app.models.processo import Processo
from app.models.publicacao import Publicacao
from app.models.responsavel import Responsavel
from app.models.tarefa import Tarefa
from app.models.usuario import Usuario

logger = logging.getLogger(__name__)

COPIA_OBRIGATORIA = "pj@pimentajudice.com.br"
STATUS_ATIVOS = ("pendente",)


# ── Destinatários ────────────────────────────────────────────────────────────

def _email_por_nome(db: Session, nome: str | None) -> str | None:
    if not nome or not nome.strip():
        return None
    alvo = nome.strip().lower()
    resp = (
        db.query(Responsavel)
        .filter(Responsavel.email.isnot(None))
        .all()
    )
    for r in resp:
        if r.nome and r.nome.strip().lower() == alvo:
            return r.email
    for u in db.query(Usuario).filter(Usuario.email.isnot(None)).all():
        if u.nome and u.nome.strip().lower() == alvo:
            return u.email
    return None


def destinatarios(db: Session, prazo: Prazo, tarefas: list[Tarefa]) -> list[str]:
    """E-mails de todo mundo vinculado ao prazo, sem a cópia obrigatória."""
    emails: list[str] = []

    def _add(valor: str | None) -> None:
        if not valor:
            return
        limpo = valor.strip().lower()
        if limpo and limpo != COPIA_OBRIGATORIA.lower() and limpo not in emails:
            emails.append(limpo)

    if prazo.responsavel_id:
        resp = db.query(Responsavel).filter(Responsavel.id == prazo.responsavel_id).first()
        if resp:
            _add(resp.email)
    _add(_email_por_nome(db, prazo.responsavel))

    for t in tarefas:
        _add(t.responsavel_email)
        if t.responsavel_id:
            resp = db.query(Responsavel).filter(Responsavel.id == t.responsavel_id).first()
            if resp:
                _add(resp.email)
        else:
            _add(_email_por_nome(db, t.responsavel))

    return emails


# ── Conteúdo ─────────────────────────────────────────────────────────────────

def _dias_restantes(data_limite: date | None, hoje: date) -> int | None:
    if not data_limite:
        return None
    return (data_limite - hoje).days


def _rotulo_prazo(dias: int | None) -> str:
    if dias is None:
        return "sem data limite"
    if dias < 0:
        return f"VENCIDO há {abs(dias)} dia(s)"
    if dias == 0:
        return "VENCE HOJE"
    if dias == 1:
        return "vence amanhã"
    return f"faltam {dias} dias"


def _materia(prazo: Prazo, processo: Processo | None) -> str:
    """Assunto curto do e-mail: o que o Lucas precisa ler na caixa de entrada."""
    for candidato in (
        processo.materia if processo else None,
        prazo.peca_necessaria,
        prazo.tipo,
    ):
        if candidato and str(candidato).strip():
            return str(candidato).strip()
    return "Prazo processual"


def assunto(prazo: Prazo, processo: Processo | None, cliente: Cliente | None, dias: int | None) -> str:
    nome = (cliente.nome if cliente else None) or "Cliente não vinculado"
    return f"[PRAZO] {nome} — {_materia(prazo, processo)} ({_rotulo_prazo(dias)})"


def _linha(rotulo: str, valor: str | None) -> str:
    if not valor:
        return ""
    return (
        f'<tr><td style="padding:4px 12px 4px 0;color:#6b7280;white-space:nowrap;vertical-align:top">{html.escape(rotulo)}</td>'
        f'<td style="padding:4px 0;color:#111827">{html.escape(str(valor))}</td></tr>'
    )


def _br(d: date | None) -> str | None:
    return d.strftime("%d/%m/%Y") if d else None


# Rótulos como aparecem no corpo do diário. Regex própria (e não o parser do
# router diario2) de propósito: importar de lá arrastaria httpx e a árvore
# inteira de deps do router pra dentro de um job de e-mail, e uma falha de
# import sumiria com as datas sem ninguém perceber. São duas linhas de texto —
# ler aqui é mais barato e mais robusto que o acoplamento.
_RE_DISPONIBILIZACAO = re.compile(
    r"Data\s+de\s+Disponibiliza(?:ç|c)[aã]o\s*:?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)
_RE_PUBLICACAO = re.compile(
    r"Data\s+de\s+Publica(?:ç|c)[aã]o\s*:?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)


def datas_do_diario(pub: Publicacao | None) -> tuple[str | None, str | None]:
    """(disponibilização, publicação) como vêm escritas no corpo do diário.

    O Lucas confere a contagem do prazo por essas duas datas, e elas não são
    colunas do banco: vivem no texto da publicação.
    """
    if pub is None:
        return None, None

    texto = pub.texto_completo or pub.texto_resumo or ""
    m_disp = _RE_DISPONIBILIZACAO.search(texto)
    m_publ = _RE_PUBLICACAO.search(texto)

    disp = m_disp.group(1) if m_disp else None
    publ = m_publ.group(1) if m_publ else None

    # A coluna manda mais que o texto: no DJEN não há rótulo de data no corpo,
    # e é ela que o cálculo do prazo usa de fato.
    if not disp and getattr(pub, "data_disponibilizacao", None):
        disp = _br(pub.data_disponibilizacao)

    # Sem a data no texto, cai pra coluna do banco — que é a que o sistema
    # usou de fato pra contar. Rotulada como tal pra não passar por citação
    # literal do diário.
    if not publ and pub.data_publicacao:
        publ = f"{_br(pub.data_publicacao)} (registro do sistema)"
    return disp, publ


def corpo_html(
    prazo: Prazo,
    processo: Processo | None,
    cliente: Cliente | None,
    pub: Publicacao | None,
    tarefas: list[Tarefa],
    dias: int | None,
) -> str:
    vencido = dias is not None and dias < 0
    cor = "#b91c1c" if (dias is not None and dias <= 2) else "#0d9488"
    frontend = (settings.frontend_url or "").rstrip("/")
    link = f"{frontend}/prazos?destaque={prazo.id}" if frontend else ""

    detalhes_prazo = "".join([
        _linha("Cliente", cliente.nome if cliente else "não vinculado"),
        _linha("Processo", processo.numero_cnj if processo else None),
        _linha("Matéria", processo.materia if processo else None),
        _linha("Vara / Comarca", " — ".join(x for x in [
            (processo.vara if processo else None),
            (processo.comarca if processo else None),
        ] if x) or None),
        _linha("Tipo", prazo.tipo),
        _linha("Peça necessária", prazo.peca_necessaria),
        _linha("Publicação (base da contagem)", _br(prazo.data_publicacao)),
        _linha("Contagem", f"{prazo.dias_prazo} dia(s) {prazo.tipo_contagem}"),
        _linha("Data limite", _br(prazo.data_limite)),
        _linha("Limite sem feriado", _br(prazo.data_limite_sem_feriado)),
        _linha("Responsável", prazo.responsavel or "sem responsável definido"),
        _linha("Descrição", prazo.descricao),
    ])

    if pub is not None:
        origem = "Recorte Digital OAB" if pub.fonte == "gmail" else "Diário Oficial"
        disp_txt, publ_txt = datas_do_diario(pub)
        detalhes_pub = "".join([
            _linha("Origem", origem),
            # As duas datas do diário vêm primeiro: é por elas que se confere
            # se a contagem do prazo partiu do dia certo.
            _linha("Disponibilização no diário", disp_txt or "não informada no texto"),
            _linha("Publicação no diário", publ_txt or "não informada no texto"),
            _linha("Tribunal", pub.tribunal),
            _linha("Vara", pub.vara),
            _linha("Tipo de ato", pub.tipo_ato),
            _linha("CNJ publicado", pub.numero_cnj),
        ])
        texto = (pub.texto_completo or pub.texto_resumo or "").strip()
        if len(texto) > 4000:
            texto = texto[:4000] + "…"
        bloco_pub = f"""
        <h3 style="margin:24px 0 8px;font-size:14px;color:#111827">Publicação que gerou o prazo</h3>
        <table style="border-collapse:collapse;font-size:13px">{detalhes_pub}</table>
        {f'<div style="margin-top:10px;padding:12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;white-space:pre-wrap;color:#334155">{html.escape(texto)}</div>' if texto else ''}
        {f'<p style="margin-top:8px;font-size:12px"><a href="{html.escape(pub.url_fonte)}" style="color:#0d9488">Abrir a publicação na fonte</a></p>' if pub.url_fonte else ''}
        """
    else:
        bloco_pub = (
            '<p style="margin-top:24px;font-size:13px;color:#6b7280">'
            "Prazo cadastrado manualmente — sem publicação de origem.</p>"
        )

    if tarefas:
        itens = "".join(
            f"<li>{html.escape(t.titulo)}"
            f"{f' — {html.escape(t.responsavel)}' if t.responsavel else ''}"
            f' <span style="color:#6b7280">({html.escape(t.status)})</span></li>'
            for t in tarefas
        )
        bloco_tarefas = f"""
        <h3 style="margin:24px 0 8px;font-size:14px;color:#111827">Tarefas vinculadas</h3>
        <ul style="margin:0;padding-left:18px;font-size:13px;color:#111827">{itens}</ul>
        """
    else:
        bloco_tarefas = ""

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8" /></head>
<body style="margin:0;padding:24px;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
  <div style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:10px;padding:24px">
    <div style="border-left:4px solid {cor};padding-left:12px;margin-bottom:20px">
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:{cor};font-weight:700">
        {'Prazo vencido sem tratamento' if vencido else 'Lembrete de prazo'}
      </div>
      <div style="font-size:20px;font-weight:700;color:#111827;margin-top:4px">
        {html.escape((cliente.nome if cliente else 'Cliente não vinculado'))}
      </div>
      <div style="font-size:14px;color:#374151;margin-top:2px">
        {html.escape(_materia(prazo, processo))} — <strong style="color:{cor}">{_rotulo_prazo(dias)}</strong>
      </div>
    </div>

    <h3 style="margin:0 0 8px;font-size:14px;color:#111827">Detalhes do prazo</h3>
    <table style="border-collapse:collapse;font-size:13px">{detalhes_prazo}</table>

    {bloco_tarefas}
    {bloco_pub}

    {f'<p style="margin-top:24px"><a href="{html.escape(link)}" style="background:#0d9488;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:600">Abrir na tela de Prazos</a></p>' if link else ''}

    <p style="margin-top:24px;font-size:11px;color:#9ca3af">
      Este lembrete é enviado todos os dias até o prazo receber tratamento
      (cumprido, perdido, ignorado ou nada a fazer) na tela de Prazos.
    </p>
  </div>
</body></html>"""


def texto_telegram(
    prazo: Prazo,
    processo: Processo | None,
    cliente: Cliente | None,
    dias: int | None,
    pub: Publicacao | None = None,
) -> str:
    nome = (cliente.nome if cliente else None) or "Cliente não vinculado"
    icone = "🔴" if (dias is not None and dias < 0) else "🟠" if (dias is not None and dias <= 2) else "🟡"
    linhas = [
        f"{icone} *{nome}* — {_materia(prazo, processo)}",
        f"⏳ {_rotulo_prazo(dias)} · limite {_br(prazo.data_limite) or '—'}",
    ]
    # Disp./Pub. do diário: é o que permite conferir a contagem sem abrir o
    # sistema. Só entra quando veio de publicação — prazo manual não tem.
    disp_txt, publ_txt = datas_do_diario(pub)
    if disp_txt or publ_txt:
        linhas.append(f"🗞 Disp. {disp_txt or '—'} · Pub. {publ_txt or '—'}")
    linhas.append(f"📆 Contagem a partir de {_br(prazo.data_publicacao)} · {prazo.dias_prazo}d {prazo.tipo_contagem}")
    if processo and processo.numero_cnj:
        linhas.append(f"⚖️ {processo.numero_cnj}")
    if prazo.peca_necessaria:
        linhas.append(f"📄 {prazo.peca_necessaria}")
    linhas.append(f"👤 {prazo.responsavel or 'sem responsável'}")
    return "\n".join(linhas)


# ── Envio ────────────────────────────────────────────────────────────────────

def _enviar_email(para: list[str], assunto_msg: str, html_msg: str) -> None:
    from app.services.email_service import _send_via_gmail_oauth

    # Sem responsável com e-mail, a cópia obrigatória vira o destinatário —
    # senão o lembrete simplesmente não sai.
    if para:
        _send_via_gmail_oauth(para[0], assunto_msg, html_msg, cc=para[1:] + [COPIA_OBRIGATORIA])
    else:
        _send_via_gmail_oauth(COPIA_OBRIGATORIA, assunto_msg, html_msg)


def _enviar_telegram(mensagens: list[str]) -> bool:
    """Um único post no grupo do @jusbr_andamentos_bot com todos os prazos do dia."""
    chat_id_raw = (settings.andamentos_push_chat_id or "").strip()
    token = (settings.andamentos_bot_token or "").strip()
    if not chat_id_raw or not token:
        logger.info("Lembrete de prazos: Telegram não configurado — pulando envio.")
        return False
    if not mensagens:
        return False

    import httpx

    hoje_br = date.today().strftime("%d/%m/%Y")
    corpo = f"⏰ *Prazos em aberto — {hoje_br}*\n\n" + "\n\n".join(mensagens)
    payload = {"chat_id": chat_id_raw, "text": corpo, "parse_mode": "Markdown"}
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=20.0
        )
        if not resp.json().get("ok"):
            # Markdown quebra com nome de cliente que tenha _ ou * — reenvia cru.
            payload.pop("parse_mode", None)
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=20.0
            )
        return bool(resp.json().get("ok"))
    except Exception as exc:
        logger.warning("Lembrete de prazos: falha ao enviar Telegram: %s", exc)
        return False


def enviar_lembretes(db: Session, *, hoje: date | None = None, forcar: bool = False) -> dict:
    """Roda a varredura do dia. `forcar` ignora o controle de 1 envio por dia."""
    hoje = hoje or date.today()
    agora = datetime.now(timezone.utc)

    prazos = (
        db.query(Prazo)
        .filter(Prazo.status.in_(STATUS_ATIVOS))
        .filter(Prazo.data_limite.isnot(None))
        .order_by(Prazo.data_limite.asc())
        .all()
    )

    enviados = 0
    pulados = 0
    erros = 0
    mensagens_telegram: list[str] = []

    for prazo in prazos:
        if not forcar and prazo.ultimo_lembrete_em is not None:
            ultimo = prazo.ultimo_lembrete_em
            if ultimo.tzinfo is None:
                ultimo = ultimo.replace(tzinfo=timezone.utc)
            if ultimo.date() == hoje:
                pulados += 1
                continue

        dias = _dias_restantes(prazo.data_limite, hoje)
        processo = db.query(Processo).filter(Processo.id == prazo.processo_id).first()
        cliente = (
            db.query(Cliente).filter(Cliente.id == processo.cliente_id).first()
            if processo else None
        )
        pub = db.query(Publicacao).filter(Publicacao.prazo_id == prazo.id).first()
        tarefas = db.query(Tarefa).filter(Tarefa.prazo_id == prazo.id).all()

        # O Telegram não depende do e-mail: se o Gmail estiver fora do ar, o
        # aviso ainda tem que chegar por algum canal.
        mensagens_telegram.append(texto_telegram(prazo, processo, cliente, dias, pub))

        try:
            _enviar_email(
                destinatarios(db, prazo, tarefas),
                assunto(prazo, processo, cliente, dias),
                corpo_html(prazo, processo, cliente, pub, tarefas, dias),
            )
            prazo.ultimo_lembrete_em = agora
            db.commit()
            enviados += 1
        except Exception as exc:
            db.rollback()
            erros += 1
            logger.warning("Lembrete de prazos: falha no prazo %s: %s", prazo.id, exc)

    telegram_ok = _enviar_telegram(mensagens_telegram)

    return {
        "data": hoje.isoformat(),
        "prazos_ativos": len(prazos),
        "emails_enviados": enviados,
        "pulados_hoje": pulados,
        "erros": erros,
        "telegram_enviado": telegram_ok,
    }
