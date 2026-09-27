"""Bot de dúvidas do cliente via WhatsApp — responde SÓ com base nos dados do
próprio processo do cliente identificado pelo número de origem.

Mesmo padrão de app.services.ia_cliente.chat_claude (cliente Anthropic direto,
guard em api_key vazia), mas com escopo bem mais restrito: nunca fornece
aconselhamento jurídico, só informa status/andamentos já registrados no
sistema e direciona qualquer outra coisa para o escritório.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.cliente import Cliente
from app.models.processo import Processo

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


def _contexto_processos(db: Session, cliente: Cliente) -> str:
    procs = (
        db.query(Processo)
        .filter(Processo.cliente_id == cliente.id, Processo.status == "ativo")
        .all()
    )
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


_SYSTEM_PROMPT = """Você é o assistente automático de WhatsApp do escritório Pimenta Júdice Advogados.
Responda SOMENTE com base nos andamentos listados abaixo — não invente informação
nem opine sobre estratégia, prazo, chance de êxito ou qualquer aconselhamento jurídico.
Se a pergunta for sobre status/andamento do processo, responda de forma objetiva e curta.
Se a pergunta exigir análise jurídica, interpretação de decisão, ou qualquer coisa fora do
que está listado, diga que vai encaminhar para o advogado responsável e não tente responder.
Nunca mencione que você é uma IA/modelo de linguagem; apresente-se como "assistente do escritório".
Respostas curtas (mensagem de WhatsApp), sem markdown.

Andamentos do(a) cliente:
{contexto}
"""


def responder_mensagem(telefone: str, texto: str) -> str:
    db = SessionLocal()
    try:
        cliente = _resolver_cliente(db, telefone)
        if not cliente:
            return _MSG_CLIENTE_NAO_IDENTIFICADO

        contexto = _contexto_processos(db, cliente)
        if not contexto:
            return _MSG_SEM_PROCESSO

        if not settings.anthropic_api_key:
            logger.warning("whatsapp_bot: ANTHROPIC_API_KEY não configurada — resposta padrão.")
            return (
                f"Olá, {cliente.nome.split()[0]}! Recebemos sua mensagem, mas o assistente "
                "automático está temporariamente indisponível. O escritório vai retornar em breve."
            )

        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resposta = client.messages.create(
            model=settings.whatsapp_claude_model,
            max_tokens=400,
            system=_SYSTEM_PROMPT.format(contexto=contexto),
            messages=[{"role": "user", "content": texto[:2000]}],
        )
        blocos_texto = [b.text for b in resposta.content if getattr(b, "type", None) == "text"]
        return "\n".join(blocos_texto).strip() or _MSG_SEM_PROCESSO
    except Exception:
        logger.exception("whatsapp_bot: erro respondendo mensagem de %s", telefone)
        return "Recebemos sua mensagem. O escritório vai retornar em breve."
    finally:
        db.close()
