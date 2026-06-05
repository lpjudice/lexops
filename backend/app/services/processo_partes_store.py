"""Persistência de partes do processo (ProcessoParte).

Idempotente: ao salvar, apaga todas as partes anteriores do mesmo dono
(processo_id OU extra_id) e regrava — assim refletir mudanças no jus.br
não duplica linhas.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.processo_parte import ProcessoParte

logger = logging.getLogger(__name__)


def salvar_partes(
    db: Session,
    *,
    processo_id: uuid.UUID | None = None,
    extra_id: uuid.UUID | None = None,
    partes: list[dict],
) -> int:
    """Apaga e regrava as partes. Exatamente um dos *_id deve ser informado."""
    if (processo_id is None) == (extra_id is None):
        raise ValueError("Informe processo_id OU extra_id, não ambos.")

    q = db.query(ProcessoParte)
    if processo_id is not None:
        q = q.filter(ProcessoParte.processo_id == processo_id)
    else:
        q = q.filter(ProcessoParte.extra_id == extra_id)
    q.delete(synchronize_session=False)

    for ordem, p in enumerate(partes):
        nome = (p.get("nome") or "").strip()
        if not nome:
            continue
        db.add(ProcessoParte(
            processo_id=processo_id,
            extra_id=extra_id,
            polo=p.get("polo") or "OUTROS",
            nome=nome[:500],
            tipo_pessoa=(p.get("tipo_pessoa") or None),
            documento=(p.get("documento") or None),
            ordem=ordem,
        ))
    db.flush()
    return sum(1 for p in partes if (p.get("nome") or "").strip())


def listar_partes(
    db: Session,
    *,
    processo_id: uuid.UUID | None = None,
    extra_id: uuid.UUID | None = None,
) -> dict[str, list[ProcessoParte]]:
    """Retorna dict {polo: [partes ordenadas]}."""
    q = db.query(ProcessoParte)
    if processo_id is not None:
        q = q.filter(ProcessoParte.processo_id == processo_id)
    elif extra_id is not None:
        q = q.filter(ProcessoParte.extra_id == extra_id)
    else:
        return {}
    rows = q.order_by(ProcessoParte.polo, ProcessoParte.ordem).all()
    out: dict[str, list[ProcessoParte]] = {}
    for r in rows:
        out.setdefault(r.polo, []).append(r)
    return out
