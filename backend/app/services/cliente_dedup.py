"""Detecção de clientes com nome parecido, para alertar antes de cadastrar um
2º registro que gerasse (via google_drive._resolver_pasta_cliente) confusão de
qual pasta usar no Drive. Não bloqueia o cadastro — só avisa o operador, que
confirma se é a mesma pessoa/empresa ou uma diferente."""
import re
import unicodedata
import uuid
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.cliente import Cliente

LIMIAR_SIMILARIDADE = 0.84


def _normalizar(nome: str) -> str:
    """trim + espaços colapsados + minúsculas + sem acento — mesma base de
    comparação usada em google_drive._normalizar_nome_busca, mas também
    removendo acentuação (para pegar "Joao"/"João")."""
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento).strip().casefold()


def encontrar_similares(
    nome: str, db: Session, excluir_id: uuid.UUID | None = None,
    limiar: float = LIMIAR_SIMILARIDADE,
) -> list[dict]:
    """Retorna clientes existentes com nome igual ou parecido ao informado,
    ordenados do mais parecido para o menos. Cada item: {id, nome, tipo,
    similaridade} (similaridade 0-1; 1.0 = idêntico após normalização)."""
    alvo = _normalizar(nome)
    if not alvo:
        return []

    query = db.query(Cliente.id, Cliente.nome, Cliente.tipo)
    if excluir_id is not None:
        query = query.filter(Cliente.id != excluir_id)

    achados: list[dict] = []
    for cid, nome_existente, tipo in query.all():
        candidato = _normalizar(nome_existente)
        if not candidato:
            continue
        if candidato == alvo:
            score = 1.0
        else:
            score = SequenceMatcher(None, alvo, candidato).ratio()
        if score >= limiar:
            achados.append({
                "id": str(cid),
                "nome": nome_existente,
                "tipo": tipo,
                "similaridade": round(score, 3),
            })

    achados.sort(key=lambda a: a["similaridade"], reverse=True)
    return achados
