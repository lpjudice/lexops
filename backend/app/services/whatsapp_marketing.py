"""Envios de MARKETING pela API do WhatsApp (convite de evento) — separados do
aviso transacional (andamento/assinatura) porque a Meta cobra bem mais (≈R$ 0,32
por mensagem entregue, contra ≈R$ 0,035 de utilidade) e porque marketing sem
consentimento derruba a qualidade do número, que é o mesmo que manda os avisos
de assinatura. Regras daqui:

  - só envia pra quem tem opt-in (ConselhoContato.whatsapp_optin);
  - nunca envia pra quem pediu pra parar (WhatsappOptOut);
  - nunca reenvia um convite que já saiu, a não ser que peçam explicitamente;
  - o convite tem botões de resposta rápida: "Vou participar" / "Não poderei" /
    "Parar de receber" — a resposta atualiza o convidado e o opt-out sozinha.

Template esperado no WhatsApp Manager (MARKETING, pt_BR, parâmetros nomeados):
`convite_evento` com {{primeiro_nome}}, {{evento}}, {{data}} e 3 botões de resposta
rápida, nesta ordem: Vou participar, Não poderei, Parar de receber.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.conselho import ConselhoContato, ConselhoEvento, ConselhoEventoConvidado
from app.models.whatsapp_optout import WhatsappOptOut
from app.services import whatsapp_api

logger = logging.getLogger(__name__)

TEMPLATE_CONVITE_EVENTO = "convite_evento"
# Estimativa pra mostrar na tela (Meta, marketing Brasil, tabela de out/2026) — não é cobrança exata.
CUSTO_MARKETING_ESTIMADO_BRL = 0.3217

_PAYLOAD_PREFIXO = "evt"
_ACOES = ("sim", "nao", "parar")
# Palavras que, digitadas por quem recebeu marketing, valem como pedido de saída.
_PALAVRAS_PARAR = {"parar", "pare", "sair", "stop", "cancelar", "descadastrar", "nao quero receber", "não quero receber"}


def telefone8(numero: str | None) -> str:
    """Últimos 8 dígitos — ignora DDI/DDD/nono dígito, igual ao bot de clientes."""
    digitos = re.sub(r"\D", "", numero or "")
    return digitos[-8:] if len(digitos) >= 8 else ""


def esta_optout(db: Session, numero: str | None) -> bool:
    t8 = telefone8(numero)
    return bool(t8) and db.query(WhatsappOptOut.id).filter(WhatsappOptOut.telefone8 == t8).first() is not None


def registrar_optout(db: Session, numero: str | None, origem: str) -> None:
    t8 = telefone8(numero)
    if not t8:
        return
    if not db.query(WhatsappOptOut.id).filter(WhatsappOptOut.telefone8 == t8).first():
        db.add(WhatsappOptOut(telefone8=t8, origem=origem))
    # Cancela também o opt-in dos contatos com esse número.
    for c in db.query(ConselhoContato).filter(ConselhoContato.whatsapp_optin.is_(True)).all():
        if telefone8(c.whatsapp) == t8:
            c.whatsapp_optin = False
    db.commit()


def eh_pedido_de_parar(texto: str) -> bool:
    return (texto or "").strip().lower().rstrip(".!") in _PALAVRAS_PARAR


def eh_contato_do_conselho_sem_ser_cliente(db: Session, numero: str) -> bool:
    """Convidado respondendo por texto: não é cliente, então o bot de processos
    não pode responder (diria "não localizei seu cadastro"). Fica sem resposta automática."""
    from app.services.whatsapp_bot import _resolver_cliente

    t8 = telefone8(numero)
    if not t8 or _resolver_cliente(db, numero):
        return False
    return any(telefone8(c.whatsapp) == t8 for c in db.query(ConselhoContato).filter(ConselhoContato.whatsapp.isnot(None)).all())


def classificar_convidados(db: Session, evento: ConselhoEvento, reenviar: bool = False) -> dict:
    """Separa os convidados do evento em quem recebe e quem fica de fora (e por quê)."""
    resultado: dict = {"enviar": [], "sem_whatsapp": [], "sem_optin": [], "optout": [], "ja_enviado": []}
    for cv in evento.convidados:
        c = cv.contato
        if not telefone8(c.whatsapp):
            resultado["sem_whatsapp"].append(cv)
        elif esta_optout(db, c.whatsapp):
            resultado["optout"].append(cv)
        elif not c.whatsapp_optin:
            resultado["sem_optin"].append(cv)
        elif cv.convite_whatsapp_em and not reenviar:
            resultado["ja_enviado"].append(cv)
        else:
            resultado["enviar"].append(cv)
    return resultado


def _data_para_texto(evento: ConselhoEvento) -> str:
    return evento.data.strftime("%d/%m/%Y") if evento.data else "data a confirmar"


def _parametros_convite(primeiro_nome: str, evento_nome: str, data_txt: str) -> dict[str, str]:
    return {"primeiro_nome": primeiro_nome.strip() or "convidado", "evento": evento_nome.strip(), "data": data_txt}


def enviar_teste(telefone: str, evento: ConselhoEvento) -> dict | None:
    """Manda UM convite de teste (sem registrar nada no convidado) — pra conferir
    texto e botões no próprio celular antes do disparo real."""
    return whatsapp_api.send_template_message(
        to=telefone,
        template_name=TEMPLATE_CONVITE_EVENTO,
        parametros=_parametros_convite("Teste", evento.nome, _data_para_texto(evento)),
        botoes_resposta_payload=[f"{_PAYLOAD_PREFIXO}:teste:{a}" for a in _ACOES],
    )


def enviar_convites_em_lote(evento_id: uuid.UUID, convidado_ids: list[uuid.UUID], pausa_s: float = 0.15) -> dict:
    """Envia o convite a cada convidado (roda em background, com sessão própria).
    Para no primeiro erro de template inexistente/não aprovado — repetir só geraria
    N falhas iguais. Retorna o resumo (também vai pro log)."""
    from app.database import SessionLocal

    db = SessionLocal()
    enviados = falhas = 0
    try:
        evento = db.get(ConselhoEvento, evento_id)
        if not evento:
            return {"enviados": 0, "falhas": 0, "erro": "evento não encontrado"}
        data_txt = _data_para_texto(evento)
        for cv in db.query(ConselhoEventoConvidado).filter(ConselhoEventoConvidado.id.in_(convidado_ids)).all():
            c = cv.contato
            # Rechecagem na hora do envio: opt-out pode ter chegado desde o clique.
            if not c.whatsapp_optin or esta_optout(db, c.whatsapp):
                continue
            try:
                resp = whatsapp_api.send_template_message(
                    to=c.whatsapp,
                    template_name=TEMPLATE_CONVITE_EVENTO,
                    parametros=_parametros_convite(c.primeiro_nome, evento.nome, data_txt),
                    botoes_resposta_payload=[f"{_PAYLOAD_PREFIXO}:{cv.id}:{a}" for a in _ACOES],
                )
            except Exception as e:  # nunca derruba o lote por causa de uma pessoa
                logger.exception("convite_whatsapp: erro inesperado com %s", c.primeiro_nome)
                resp = {"erro": {"message": str(e)[:200]}}
            msg_id = whatsapp_api.id_da_mensagem(resp)
            if msg_id:
                cv.convite_whatsapp_em = datetime.now(timezone.utc)
                cv.convite_whatsapp_msg_id = msg_id
                cv.convite_whatsapp_status = "enviado"
                cv.convite_whatsapp_erro = None
                enviados += 1
            else:
                erro = (resp or {}).get("erro") if isinstance(resp, dict) else None
                cv.convite_whatsapp_status = "falhou"
                cv.convite_whatsapp_erro = (str(erro) if erro else "sem resposta da Meta")[:500]
                falhas += 1
                codigo = (erro or {}).get("error", {}).get("code") if isinstance(erro, dict) else None
                if codigo in (132000, 132001, 132005, 132012, 132015, 132016):  # template ausente/pausado/parâmetros
                    db.commit()
                    logger.error("convite_whatsapp: template indisponível (%s) — lote interrompido", codigo)
                    break
            db.commit()
            time.sleep(pausa_s)
    except Exception:
        db.rollback()
        logger.exception("convite_whatsapp: erro no lote")
    finally:
        db.close()
    logger.info("convite_whatsapp: lote do evento %s — %d enviado(s), %d falha(s)", evento_id, enviados, falhas)
    return {"enviados": enviados, "falhas": falhas}


def tratar_resposta_botao(db: Session, telefone: str, payload: str) -> str | None:
    """Resposta a um botão do convite. Devolve o texto de confirmação a enviar de
    volta (dentro da janela de 24h aberta pelo clique), ou None se o payload não for nosso."""
    partes = (payload or "").split(":")
    if len(partes) != 3 or partes[0] != _PAYLOAD_PREFIXO or partes[2] not in _ACOES:
        return None
    _, alvo, acao = partes
    # Convite de TESTE nunca grava nada — nem o "Parar de receber" (senão testar o botão
    # tiraria o próprio número de quem testa da lista de marketing).
    if alvo == "teste":
        return f"Teste recebido: o botão \"{ {'sim': 'Vou participar', 'nao': 'Não poderei', 'parar': 'Parar de receber'}[acao] }\" funcionou. Nada foi registrado."
    if acao == "parar":
        registrar_optout(db, telefone, origem="botao")
        return "Combinado, você não receberá mais convites por WhatsApp. Obrigado!"
    try:
        cv = db.get(ConselhoEventoConvidado, uuid.UUID(alvo))
    except ValueError:
        return None
    if not cv:
        return None
    if acao == "sim":
        cv.presenca_confirmada, cv.recusou = True, False
        resposta = "Presença confirmada, obrigado!"
    else:
        cv.presenca_confirmada, cv.recusou = False, True
        resposta = "Sem problemas, obrigado por avisar. Esperamos você em uma próxima oportunidade."
    db.commit()
    return resposta


def atualizar_status_entrega(db: Session, msg_id: str, status: str, erro: str | None = None) -> None:
    """Status de entrega da Meta (sent/delivered/read/failed) -> convidado do convite."""
    if not msg_id:
        return
    cv = db.query(ConselhoEventoConvidado).filter(ConselhoEventoConvidado.convite_whatsapp_msg_id == msg_id).first()
    if not cv:
        return
    mapa = {"sent": "enviado", "delivered": "entregue", "read": "lido", "failed": "falhou"}
    novo = mapa.get(status)
    if not novo:
        return
    # Nunca "volta" de lido/entregue pra enviado (webhooks chegam fora de ordem).
    ordem = {"enviado": 1, "entregue": 2, "lido": 3, "falhou": 3}
    if ordem.get(cv.convite_whatsapp_status or "", 0) > ordem[novo]:
        return
    cv.convite_whatsapp_status = novo
    if novo == "falhou":
        cv.convite_whatsapp_erro = (erro or "falha de entrega")[:500]
    db.commit()
