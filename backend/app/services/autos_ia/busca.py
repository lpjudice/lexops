"""Busca por tema (full-text) e por data/tipo entre as peças de um caso."""
import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.autos_ia import AutosIAPeca

TSVECTOR_EXPR = func.to_tsvector(
    "portuguese",
    func.coalesce(AutosIAPeca.titulo, "")
    .concat(" ")
    .concat(func.coalesce(AutosIAPeca.resumo, ""))
    .concat(" ")
    .concat(func.coalesce(AutosIAPeca.texto_md, "")),
)


def buscar_pecas(
    db: Session,
    caso_id: uuid.UUID,
    query: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tipo: str | None = None,
    limite: int = 200,
) -> list[AutosIAPeca]:
    q = db.query(AutosIAPeca).filter(AutosIAPeca.caso_id == caso_id)
    if tipo:
        q = q.filter(AutosIAPeca.tipo == tipo)
    if data_inicio:
        q = q.filter(AutosIAPeca.data_peca >= data_inicio)
    if data_fim:
        q = q.filter(AutosIAPeca.data_peca <= data_fim)

    if query and query.strip():
        tsquery = func.websearch_to_tsquery("portuguese", query.strip())
        q = q.filter(TSVECTOR_EXPR.op("@@")(tsquery))
        q = q.order_by(func.ts_rank(TSVECTOR_EXPR, tsquery).desc())
    else:
        q = q.order_by(AutosIAPeca.pagina_inicio.asc())

    return q.limit(limite).all()
