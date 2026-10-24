"""Bot de dúvidas do cliente via WhatsApp — responde SÓ com base nos dados do
próprio processo do cliente identificado pelo número de origem.

Mesmo padrão de app.services.ia_cliente.chat_claude (cliente Anthropic direto,
guard em api_key vazia), mas com escopo bem mais restrito: nunca fornece
aconselhamento jurídico, só informa status/andamentos já registrados no
sistema e direciona qualquer outra coisa para o escritório.

O que o bot enxerga (e SÓ isso): processos ATIVOS do cliente identificado —
como cliente principal ou como litisconsorte — e os últimos andamentos de cada
um. Não acessa financeiro, contratos, documentos nem processos de outro cliente.
DECISÃO DO LUCAS (25/10/2026): o bot NUNCA terá acesso a financeiro — não adicionar consultas a
Honorario/Parcela/Recebivel aqui, nem no contexto do modelo, sob nenhum pretexto.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.cliente import Cliente
from app.models.processo import Processo, processo_clientes
from app.models.whatsapp_bot import WhatsappBotMensagem

logger = logging.getLogger(__name__)

_MSG_CLIENTE_NAO_IDENTIFICADO = (
    "Olá! Não consegui localizar seu cadastro pelo número que você está usando. "
    "Entre em contato com o escritório para atualizarmos seu WhatsApp cadastrado."
)
_MSG_SEM_PROCESSO = (
    "Olá! Localizei seu cadastro, mas não encontrei processo ativo vinculado. "
    "Fale com o escritório para mais detalhes."
)

_ULTIMOS_ANDAMENTOS_POR_PROCESSO = 5
# Memória da conversa: as últimas mensagens dentro desta janela vão junto pro modelo
# (é o que faz "1" funcionar depois de uma lista numerada). Passou disso, esquece.
_MEMORIA_MAX_MENSAGENS = 10
_MEMORIA_JANELA = timedelta(minutes=45)
_MEMORIA_RETENCAO = timedelta(hours=24)

# Número CNJ com ou sem pontuação: NNNNNNN-DD.AAAA.J.TR.OOOO (20 dígitos)
_RE_CNJ = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")


def _apenas_digitos(numero: str) -> str:
    return re.sub(r"\D", "", numero or "")


def _resolver_cliente(db: Session, telefone: str) -> Cliente | None:
    """Casa pelos últimos 8 dígitos (robusto a DDI/DDD/9º dígito divergentes
    entre o que o WhatsApp manda e o que está cadastrado)."""
    alvo = _apenas_digitos(telefone)[-8:]
    if not alvo:
        return None
    candidatos = db.query(Cliente).filter(
        (Cliente.whatsapp.isnot(None)) | (Cliente.telefone.isnot(None))
    ).all()
    for c in candidatos:
        for campo in (c.whatsapp, c.telefone):
            if campo and _apenas_digitos(campo)[-8:] == alvo:
                return c
    return None


def _processos_do_cliente(db: Session, cliente: Cliente) -> list[Processo]:
    """Processos ativos em que o cliente é o principal OU litisconsorte
    (tabela processo_clientes)."""
    ids_litisconsorcio = select(processo_clientes.c.processo_id).where(
        processo_clientes.c.cliente_id == cliente.id
    )
    return (
        db.query(Processo)
        .filter(
            Processo.status == "ativo",
            or_(Processo.cliente_id == cliente.id, Processo.id.in_(ids_litisconsorcio)),
        )
        .order_by(Processo.numero_cnj)
        .all()
    )


def _contexto_processos(db: Session, procs: list[Processo]) -> str:
    if not procs:
        return ""
    blocos = []
    for p in procs:
        andamentos = (
            db.query(AndamentoProcesso)
            .filter(AndamentoProcesso.processo_id == p.id)
            .order_by(AndamentoProcesso.data_andamento.desc().nullslast())
            .limit(_ULTIMOS_ANDAMENTOS_POR_PROCESSO)
            .all()
        )
        linhas = [f"Processo {p.numero_cnj} — {p.materia or 'sem matéria cadastrada'} ({p.tribunal or '—'})"]
        for a in andamentos:
            data = a.data_andamento.strftime("%d/%m/%Y") if a.data_andamento else "—"
            linhas.append(f"  - {data}: {(a.descricao or '').strip()[:300]}")
        blocos.append("\n".join(linhas))
    return "\n\n".join(blocos)


def _formatar_cnj(digitos: str) -> str:
    return f"{digitos[:7]}-{digitos[7:9]}.{digitos[9:13]}.{digitos[13]}.{digitos[14:16]}.{digitos[16:]}"


def _cnjs_citados(texto: str) -> list[str]:
    """Números de processo (20 dígitos) mencionados na mensagem, sem repetir."""
    vistos: list[str] = []
    for m in _RE_CNJ.findall(texto or ""):
        d = _apenas_digitos(m)
        if len(d) == 20 and d not in vistos:
            vistos.append(d)
    return vistos


def _historico(db: Session, telefone8: str) -> list[dict]:
    """Mensagens recentes da conversa no formato da API, alternando user/assistant
    (junta seguidas do mesmo papel e garante que começa com user)."""
    desde = datetime.now(timezone.utc) - _MEMORIA_JANELA
    linhas = (
        db.query(WhatsappBotMensagem)
        .filter(WhatsappBotMensagem.telefone8 == telefone8, WhatsappBotMensagem.created_at >= desde)
        .order_by(WhatsappBotMensagem.created_at.desc())
        .limit(_MEMORIA_MAX_MENSAGENS)
        .all()
    )
    msgs: list[dict] = []
    for l in reversed(linhas):
        if msgs and msgs[-1]["role"] == l.papel:
            msgs[-1]["content"] += "\n" + l.texto
        else:
            msgs.append({"role": l.papel, "content": l.texto})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def _lembrar(db: Session, telefone8: str, pergunta: str, resposta: str) -> None:
    db.add(WhatsappBotMensagem(telefone8=telefone8, papel="user", texto=pergunta[:2000]))
    db.add(WhatsappBotMensagem(telefone8=telefone8, papel="assistant", texto=resposta[:2000]))
    # Faxina: conversa de mais de um dia não serve pra nada.
    db.query(WhatsappBotMensagem).filter(
        WhatsappBotMensagem.created_at < datetime.now(timezone.utc) - _MEMORIA_RETENCAO
    ).delete(synchronize_session=False)
    db.commit()


_SYSTEM_PROMPT = """Você é o assistente automático de WhatsApp do escritório Pimenta Júdice Advogados.
Responda SOMENTE com base nos andamentos listados abaixo — não invente informação
nem opine sobre estratégia, prazo, chance de êxito ou qualquer aconselhamento jurídico.
Se a pergunta for sobre status/andamento do processo, responda de forma objetiva e curta.
Se a pergunta exigir análise jurídica, interpretação de decisão, ou qualquer coisa fora do
que está listado, diga que isso precisa ser tratado diretamente com o escritório — telefone
(27) 3345-5501 ou e-mail pj@pimentajudice.com.br — e não tente responder. NUNCA prometa
"anotar", "encaminhar" ou que alguém vai entrar em contato: você não consegue acionar ninguém.
Você não tem acesso a informações financeiras, contratos nem documentos: se perguntarem,
diga que isso é tratado direto com o escritório, com o mesmo telefone e e-mail.
Nunca mencione que você é uma IA/modelo de linguagem; apresente-se como "assistente do escritório".
Respostas curtas (mensagem de WhatsApp), sem markdown.

Se o cliente tiver mais de um processo e não disser qual, liste-os NUMERADOS (1., 2., ...) com o
número do processo e a matéria, e pergunte qual ele quer. Se a próxima mensagem do cliente for
só um número, é a escolha do item dessa lista: responda sobre aquele processo.

Andamentos do(a) cliente:
{contexto}
"""


def responder_mensagem(telefone: str, texto: str) -> str:
    db = SessionLocal()
    try:
        cliente = _resolver_cliente(db, telefone)
        if not cliente:
            return _MSG_CLIENTE_NAO_IDENTIFICADO

        procs = _processos_do_cliente(db, cliente)
        if not procs:
            return _MSG_SEM_PROCESSO

        # Número de processo que não é do cliente: resposta direta e clara (sem
        # passar pelo modelo, que só dizia "não existe" ou "não cadastrado").
        meus = {_apenas_digitos(p.numero_cnj) for p in procs}
        citados = _cnjs_citados(texto)
        de_outros = [c for c in citados if c not in meus]
        if de_outros and not any(c in meus for c in citados):
            lista = ", ".join(_formatar_cnj(c) for c in de_outros[:3])
            plural = len(de_outros) > 1
            return (
                f"O{'s processos' if plural else ' processo'} {lista} não {'estão vinculados' if plural else 'está vinculado'} "
                "ao seu cadastro, por isso não posso informar dados dele. "
                "Se você acredita que deveria estar, fale com o escritório."
            )

        if not settings.anthropic_api_key:
            logger.warning("whatsapp_bot: ANTHROPIC_API_KEY não configurada — resposta padrão.")
            return (
                f"Olá, {cliente.nome.split()[0]}! Recebemos sua mensagem, mas o assistente "
                "automático está temporariamente indisponível. O escritório vai retornar em breve."
            )

        telefone8 = _apenas_digitos(telefone)[-8:]
        mensagens = _historico(db, telefone8) + [{"role": "user", "content": texto[:2000]}]
        # Se ficou user+user (resposta anterior não foi gravada), junta.
        compactadas: list[dict] = []
        for m in mensagens:
            if compactadas and compactadas[-1]["role"] == m["role"]:
                compactadas[-1]["content"] += "\n" + m["content"]
            else:
                compactadas.append(dict(m))

        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resposta = client.messages.create(
            model=settings.whatsapp_claude_model,
            max_tokens=400,
            system=_SYSTEM_PROMPT.format(contexto=_contexto_processos(db, procs)),
            messages=compactadas,
        )
        blocos_texto = [b.text for b in resposta.content if getattr(b, "type", None) == "text"]
        # WhatsApp usa *negrito* com um asterisco; o modelo às vezes manda **markdown**.
        final = ("\n".join(blocos_texto).strip() or _MSG_SEM_PROCESSO).replace("**", "*")
        # Mistura de números: o modelo responde sobre os do cliente; avisamos dos demais.
        if de_outros:
            final += "\n\nObs.: " + ", ".join(_formatar_cnj(c) for c in de_outros[:3]) + " não está(ão) vinculado(s) ao seu cadastro."
        _lembrar(db, telefone8, texto, final)
        return final
    except Exception:
        db.rollback()
        logger.exception("whatsapp_bot: erro respondendo mensagem de %s", telefone)
        return "Recebemos sua mensagem. O escritório vai retornar em breve."
    finally:
        db.close()
