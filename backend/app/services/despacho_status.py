"""Enriquece publicações (do Diário Oficial ou do Recorte Digital OAB) com o
que já foi feito no Despacho — pra quem lê a publicação pelo menu de origem
enxergar, sem precisar abrir o Despacho, se ela já foi tratada e o que saiu
disso (prazo, card macro, tarefas, peça).

Segue o mesmo padrão usado em `prazos.py` (`tarefas_vinculadas`): atributos
transientes atribuídos direto no objeto ORM antes de serializar, sem
persistir nada.
"""
import json

from sqlalchemy.orm import Session

from app.models.prazo import Prazo
from app.models.publicacao import Publicacao
from app.models.tarefa_card import TarefaCard, TarefaCardSubtask


def enriquecer_status_despacho(db: Session, pubs: list[Publicacao]) -> None:
    if not pubs:
        return

    prazo_ids = [p.prazo_id for p in pubs if p.prazo_id]
    prazos_por_id = {}
    if prazo_ids:
        for prazo in db.query(Prazo).filter(Prazo.id.in_(prazo_ids)).all():
            prazos_por_id[prazo.id] = prazo

    card_ids = [p.tarefa_card_id for p in pubs if p.tarefa_card_id]
    cards_por_id = {}
    subtasks_por_card: dict = {}
    if card_ids:
        for card in db.query(TarefaCard).filter(TarefaCard.id.in_(card_ids)).all():
            cards_por_id[card.id] = card
        for st in db.query(TarefaCardSubtask).filter(TarefaCardSubtask.card_id.in_(card_ids)).order_by(TarefaCardSubtask.ordem).all():
            subtasks_por_card.setdefault(st.card_id, []).append({"texto": st.texto, "concluida": st.concluida})

    for pub in pubs:
        # Nunca passou pelo Despacho — não polui a resposta com nada.
        if not pub.despacho_tratada and not pub.vinculo_confirmado and not pub.sugestao_acao:
            pub.despacho_status = None
            continue

        prazo = prazos_por_id.get(pub.prazo_id) if pub.prazo_id else None
        card = cards_por_id.get(pub.tarefa_card_id) if pub.tarefa_card_id else None

        pub.despacho_status = {
            "tratada": pub.despacho_tratada,
            "rejeitada": pub.rejeitada,
            "disposicao": pub.disposicao,
            # Campos de edição vêm junto: o Diário Oficial e o Recorte Digital
            # alteram o prazo direto pelo PATCH /prazos/{id}, e sem eles a tela
            # não teria como pré-preencher o formulário.
            "prazo": {
                "id": str(prazo.id),
                "tipo": prazo.tipo,
                "data_limite": prazo.data_limite.isoformat() if prazo.data_limite else None,
                "status": prazo.status,
                "peca_necessaria": prazo.peca_necessaria,
                "descricao": prazo.descricao,
                "data_publicacao": prazo.data_publicacao.isoformat() if prazo.data_publicacao else None,
                "dias_prazo": prazo.dias_prazo,
                "tipo_contagem": prazo.tipo_contagem,
                "responsavel": prazo.responsavel,
            } if prazo else None,
            "tarefa_card": {
                "id": str(card.id),
                "titulo": card.titulo,
                "status": card.status,
                "subtasks": subtasks_por_card.get(card.id, []),
            } if card else None,
            "tarefas": json.loads(pub.tarefas_criadas) if pub.tarefas_criadas else [],
            "peca_doc_url": pub.peca_doc_url,
        }
