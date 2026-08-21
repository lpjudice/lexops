"""Tratamento "Nada a fazer" — ponto único usado pelo Diário Oficial, pelo
Recorte Digital OAB, pelo Despacho e pela tela de Prazos.

Motivação: uma publicação pode ser nossa, já lida e entendida, e ainda assim
não pedir providência nenhuma (sentença favorável em que não cabe embargo, por
exemplo). Antes disso só havia "rejeitar" (que quer dizer *não é nosso*), então
esses casos ficavam eternamente pendentes.

Marcar "nada a fazer" faz três coisas de uma vez, e é por isso que mora aqui e
não dentro de um router: a publicação é fechada, o prazo dela vai para o status
`nada_a_fazer` (aparecendo na aba própria em Prazos) e as tarefas que tinham
sido criadas automaticamente por causa daquela publicação viram `cancelado` —
elas não vão ser feitas, e deixá-las abertas seria mentira na lista de tarefas.

Como Publicacao.prazo_id é o único vínculo entre os dois lados, a operação é
simétrica: dá pra entrar por qualquer um dos menus e o outro reflete.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.models.prazo import Prazo
from app.models.processo import Processo
from app.models.publicacao import Publicacao
from app.models.tarefa import Tarefa
from app.models.tarefa_card import TarefaCard

logger = logging.getLogger(__name__)

DISPOSICAO = "nada_a_fazer"
STATUS_PRAZO = "nada_a_fazer"


def publicacao_do_prazo(db: Session, prazo_id: uuid.UUID) -> Publicacao | None:
    """Volta da tela de Prazos para a publicação que gerou o prazo."""
    return db.query(Publicacao).filter(Publicacao.prazo_id == prazo_id).first()


def _cancelar_tarefas(db: Session, pub: Publicacao | None, prazo: Prazo | None) -> int:
    """Cancela as tarefas geradas por aquela publicação/prazo.

    Duas fontes, porque nem toda tarefa criada no Despacho ganha `prazo_id`
    (quando a aprovação não cria prazo, as tarefas só ficam registradas no JSON
    `tarefas_criadas` da publicação).
    """
    ids: set[uuid.UUID] = set()

    if prazo is not None:
        for (tid,) in db.query(Tarefa.id).filter(Tarefa.prazo_id == prazo.id).all():
            ids.add(tid)

    if pub is not None and pub.tarefas_criadas:
        try:
            for item in json.loads(pub.tarefas_criadas):
                try:
                    ids.add(uuid.UUID(str(item.get("id"))))
                except (ValueError, TypeError, AttributeError):
                    continue
        except (ValueError, TypeError):
            logger.warning("Publicação %s com tarefas_criadas inválido", pub.id if pub else "?")

    if not ids:
        return 0

    canceladas = 0
    for tarefa in db.query(Tarefa).filter(Tarefa.id.in_(ids)).all():
        # Tarefa já concluída fica como está — foi feita de verdade, e
        # reescrever isso apagaria histórico real de trabalho.
        if tarefa.status in ("concluido", "cancelado"):
            continue
        tarefa.status = "cancelado"
        canceladas += 1

    if prazo is not None:
        card = (
            db.query(TarefaCard)
            .filter(TarefaCard.id == pub.tarefa_card_id)
            .first()
            if pub is not None and pub.tarefa_card_id
            else None
        )
        if card is not None and card.status not in ("concluido", "cancelado"):
            card.status = "cancelado"

    return canceladas


def _criar_prazo_placeholder(db: Session, pub: Publicacao) -> Prazo | None:
    """Publicação sem prazo: cria um registro só pra ela existir na aba
    "Nada a fazer" da tela de Prazos, que é onde o usuário procura o histórico
    de tratamento. Sem processo vinculado não dá — prazos.processo_id é NOT NULL.
    """
    if not pub.processo_id:
        return None
    processo = db.query(Processo).filter(Processo.id == pub.processo_id).first()
    if not processo:
        return None

    prazo = Prazo(
        processo_id=processo.id,
        tipo="outro",
        descricao=pub.texto_resumo,
        data_publicacao=pub.data_publicacao,
        dias_prazo=0,
        tipo_contagem="uteis",
        # Sem contagem a fazer: o "limite" é a própria publicação, só pra a
        # listagem ordenada por data_limite não jogar o item pro fim.
        data_limite=pub.data_publicacao,
        data_limite_sem_feriado=pub.data_publicacao,
        status=STATUS_PRAZO,
    )
    db.add(prazo)
    db.flush()
    pub.prazo_id = prazo.id
    return prazo


def marcar_nada_a_fazer(db: Session, pub: Publicacao, *, commit: bool = True) -> dict:
    """Entrada pelos menus de publicação (Diário Oficial / Recorte / Despacho)."""
    prazo = db.query(Prazo).filter(Prazo.id == pub.prazo_id).first() if pub.prazo_id else None
    if prazo is None:
        prazo = _criar_prazo_placeholder(db, pub)
    else:
        prazo.status = STATUS_PRAZO

    canceladas = _cancelar_tarefas(db, pub, prazo)

    pub.despacho_tratada = True
    pub.disposicao = DISPOSICAO
    pub.lida = True

    if commit:
        db.commit()

    return {
        "publicacao_id": str(pub.id),
        "prazo_id": str(prazo.id) if prazo else None,
        "tarefas_canceladas": canceladas,
        # Sem processo vinculado não dá pra criar o espelho em Prazos; o menu de
        # origem mostra o aviso em vez de fingir que ficou tudo certo.
        "aviso": (
            None if prazo
            else "Publicação marcada como 'nada a fazer', mas sem processo vinculado "
                 "ela não aparece na aba Nada a fazer da tela de Prazos. "
                 "Vincule um processo para espelhar lá."
        ),
    }


def aplicar_status_prazo(db: Session, prazo: Prazo, novo_status: str) -> None:
    """Entrada pela tela de Prazos — propaga o status de volta pra publicação.

    Só mexe em `disposicao` quando ela é (ou passa a ser) "nada_a_fazer": um
    prazo marcado como cumprido não deve apagar um "não é nosso" registrado
    antes no Despacho.
    """
    pub = publicacao_do_prazo(db, prazo.id)

    if novo_status == STATUS_PRAZO:
        if pub is not None:
            _cancelar_tarefas(db, pub, prazo)
            pub.despacho_tratada = True
            pub.disposicao = DISPOSICAO
            pub.lida = True
        else:
            _cancelar_tarefas(db, None, prazo)
        return

    # Saiu de "nada a fazer" — devolve a publicação ao fluxo normal.
    if pub is not None and pub.disposicao == DISPOSICAO:
        pub.disposicao = None
        if novo_status == "pendente":
            pub.despacho_tratada = False
