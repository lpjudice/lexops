"""Detecção de clientes com nome parecido, para alertar antes de cadastrar um
2º registro que gerasse (via google_drive._resolver_pasta_cliente) confusão de
qual pasta usar no Drive. Não bloqueia o cadastro — só avisa o operador, que
confirma se é a mesma pessoa/empresa ou uma diferente."""
import re
import unicodedata
import uuid
from difflib import SequenceMatcher

from sqlalchemy import text
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


def _chave_grupo(ids: list[str]) -> str:
    """Chave estável de um grupo de duplicidade, independente da ordem."""
    return ",".join(sorted(ids))


def escanear_duplicados_cadastro(db: Session, limiar: float = LIMIAR_SIMILARIDADE) -> list[dict]:
    """Varre TODA a tabela `clientes` e agrupa linhas com nome igual/parecido
    (mesma comparação de `encontrar_similares`, mas O(n²) sobre a base toda —
    usado só na tela de revisão manual de duplicidades, não em toda criação).
    Omite grupos que o Lucas já revisou e confirmou como pessoas diferentes
    (`dispensar_duplicata`).
    Retorna: [{chave, membros: [{id, nome, tipo, drive_folder_id, created_at}], similaridade}]"""
    dispensadas = {
        row[0] for row in db.execute(text("SELECT chave FROM cliente_duplicata_dispensada")).fetchall()
    }

    linhas = db.execute(
        text("SELECT id::text, nome, tipo, drive_folder_id, created_at FROM clientes ORDER BY nome")
    ).fetchall()
    normalizados = [(cid, nome, tipo, fid, criado, _normalizar(nome)) for cid, nome, tipo, fid, criado in linhas]

    vistos: set[str] = set()
    grupos: list[dict] = []
    for i, (cid, nome, tipo, fid, criado, n1) in enumerate(normalizados):
        if cid in vistos or not n1:
            continue
        membros = [{
            "id": cid, "nome": nome, "tipo": tipo, "drive_folder_id": fid,
            "created_at": criado.isoformat() if criado else None,
        }]
        pior_score = 1.0
        for cid2, nome2, tipo2, fid2, criado2, n2 in normalizados[i + 1:]:
            if cid2 in vistos or not n2:
                continue
            score = 1.0 if n1 == n2 else SequenceMatcher(None, n1, n2).ratio()
            if score >= limiar:
                membros.append({
                    "id": cid2, "nome": nome2, "tipo": tipo2, "drive_folder_id": fid2,
                    "created_at": criado2.isoformat() if criado2 else None,
                })
                pior_score = min(pior_score, score)
        if len(membros) > 1:
            chave = _chave_grupo([m["id"] for m in membros])
            for m in membros:
                vistos.add(m["id"])
            if chave in dispensadas:
                continue
            grupos.append({"chave": chave, "membros": membros, "similaridade": round(pior_score, 3)})
    return grupos


def dispensar_duplicata(ids: list[str], db: Session) -> None:
    """Marca um grupo como revisado e confirmado como pessoas/empresas
    DIFERENTES — some do alerta até a lista de membros do grupo mudar."""
    chave = _chave_grupo([str(i) for i in ids])
    db.execute(
        text("INSERT INTO cliente_duplicata_dispensada (chave) VALUES (:c) ON CONFLICT DO NOTHING"),
        {"c": chave},
    )
    db.commit()
