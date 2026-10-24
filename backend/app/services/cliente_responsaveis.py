"""Responsáveis do contrato/procuração → responsáveis do CLIENTE.

Quem o usuário escolhe como responsável num contrato ou numa procuração passa a constar
também no cadastro do cliente (Cliente.responsaveis_ids), e é o cadastro do cliente que
define quem recebe os recados do assistente de WhatsApp (e-mail/Telegram).

Só SOMA: tirar alguém do contrato não tira do cliente (a pessoa pode ser responsável do
cliente por outro motivo), e o usuário edita a lista direto na página do cliente. Se uma
pessoa removida do cliente ainda estiver num contrato, ela volta na próxima vez que esse
contrato for salvo com ela selecionada.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.contrato import Contrato

logger = logging.getLogger(__name__)


def _ids_validos(brutos) -> list[str]:
    ids: list[str] = []
    for b in brutos or []:
        try:
            s = str(uuid.UUID(str(b)))
        except ValueError:
            continue
        if s not in ids:
            ids.append(s)
    return ids


def carregar_responsaveis_do_contrato(db: Session, contrato: Contrato) -> bool:
    """Soma os responsáveis do contrato aos do cliente. True se mudou algo (o commit é de quem chama)."""
    novos = _ids_validos(contrato.responsaveis_ids)
    if not novos:
        return False
    cliente = db.get(Cliente, contrato.cliente_id)
    if not cliente:
        return False
    atuais = _ids_validos(cliente.responsaveis_ids)
    faltando = [i for i in novos if i not in atuais]
    if not faltando:
        return False
    cliente.responsaveis_ids = atuais + faltando  # lista nova: o JSONB só detecta a mudança assim
    logger.info("cliente %s: +%d responsável(is) vindos do contrato %s", cliente.id, len(faltando), contrato.id)
    return True
