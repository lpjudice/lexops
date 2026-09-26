"""Busca por tema (full-text) e por data/tipo entre as peças de um caso."""
import uuid
from datetime import date

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.autos_ia import AutosIAPeca

TSVECTOR_EXPR = func.to_tsvector(
    "portuguese",
    func.coalesce(AutosIAPeca.titulo, "")
    .concat(" ")
    .concat(func.coalesce(AutosIAPeca.titulo_customizado, ""))
    .concat(" ")
    .concat(func.coalesce(AutosIAPeca.resumo, ""))
    .concat(" ")
    .concat(func.coalesce(AutosIAPeca.texto_md, ""))
    .concat(" ")
    .concat(func.coalesce(func.array_to_string(AutosIAPeca.keywords, " "), ""))
    .concat(" ")
    .concat(func.coalesce(func.array_to_string(AutosIAPeca.keywords_usuario, " "), ""))
    .concat(" ")
    .concat(func.coalesce(AutosIAPeca.nota_usuario, "")),
)


def buscar_pecas(
    db: Session,
    caso_id: uuid.UUID,
    query: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tipo: str | None = None,
    incluir_anexos: bool = False,
    offset: int = 0,
    limite: int = 100,
) -> list[AutosIAPeca]:
    """`offset`/`limite` paginam o resultado — essencial num processo com centenas
    de peças; sem paginação, um caso grande simplesmente não cabia na tela e a
    maior parte ficava invisível (nem aparecia nem era possível "ver mais")."""
    q = db.query(AutosIAPeca).filter(AutosIAPeca.caso_id == caso_id)
    if not incluir_anexos:
        q = q.filter(AutosIAPeca.peca_pai_id.is_(None))
    if tipo:
        q = q.filter(AutosIAPeca.tipo == tipo)
    if data_inicio:
        q = q.filter(AutosIAPeca.data_peca >= data_inicio)
    if data_fim:
        q = q.filter(AutosIAPeca.data_peca <= data_fim)

    if query and query.strip():
        termo = query.strip()
        tsquery = func.websearch_to_tsquery("portuguese", termo)
        # ID processual (ex.: "Evento 45", protocolos com ponto/hífen) não
        # tokeniza bem pelo full-text — casa também por substring direta,
        # senão uma busca pelo ID exato de uma peça citada em outra não acha.
        q = q.filter(or_(
            TSVECTOR_EXPR.op("@@")(tsquery),
            AutosIAPeca.id_processual.ilike(f"%{termo}%"),
        ))
        q = q.order_by(func.ts_rank(TSVECTOR_EXPR, tsquery).desc())
    else:
        # Mais recentes primeiro — como um advogado abriria os autos pra ver o
        # que aconteceu por último; página costuma seguir a ordem cronológica
        # de importação, então é a melhor proxy disponível sem custar uma
        # junção por data em toda busca sem filtro de texto.
        q = q.order_by(AutosIAPeca.pagina_inicio.desc())

    return q.offset(offset).limit(limite).all()
