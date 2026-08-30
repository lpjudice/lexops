"""Persistência de partes do processo (ProcessoParte).

Idempotente: ao salvar, apaga todas as partes anteriores do mesmo dono
(processo_id OU extra_id) e regrava — assim refletir mudanças no jus.br
não duplica linhas.
"""
from __future__ import annotations

import logging
import unicodedata
import uuid
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.processo_parte import ProcessoParte

if TYPE_CHECKING:
    from app.models.processo import Processo

logger = logging.getLogger(__name__)

# Papel processual (processos.polo) → polo ATIVO/PASSIVO das partes vindas do
# PDPJ, usado como fallback quando o nome do cliente não bate com nenhuma parte.
_PAPEL_POLO = {
    "autor": "ATIVO", "embargante": "ATIVO", "apelante": "ATIVO",
    "agravante": "ATIVO", "recorrente": "ATIVO", "opoente": "ATIVO",
    "reu": "PASSIVO", "embargado": "PASSIVO", "apelado": "PASSIVO",
    "agravado": "PASSIVO", "recorrido": "PASSIVO",
}


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento e sem pontuação — para comparar nomes de partes."""
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in base.lower() if c.isalnum() or c.isspace()).strip()


def _juntar_nomes(nomes: list[str]) -> str:
    if len(nomes) == 1:
        return nomes[0]
    if len(nomes) == 2:
        return f"{nomes[0]} e {nomes[1]}"
    return f"{nomes[0]} e outros"


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


def identificar_cliente_e_contraria(
    db: Session, processo: "Processo"
) -> tuple[str | None, str | None]:
    """Retorna (nome do cliente no processo, nome da parte contrária).

    As partes só existem quando o processo já foi sincronizado pelo jus.br/PDPJ;
    processo cadastrado à mão e nunca sincronizado devolve (cliente, None).

    Descobre de que lado está o cliente em duas etapas: primeiro pelo nome
    (mais confiável que o cadastro, que costuma estar desatualizado), depois
    pelo papel processual registrado em `processo.polo`.
    """
    cliente_nome = processo.cliente.nome if processo.cliente else None

    partes = listar_partes(db, processo_id=processo.id)
    if not partes:
        return cliente_nome, None

    polo_cliente: str | None = None
    if cliente_nome:
        alvo = _normalizar(cliente_nome)
        for polo, lista in partes.items():
            if any(alvo and alvo in _normalizar(p.nome) for p in lista):
                polo_cliente = polo
                break
    if polo_cliente is None and processo.polo:
        polo_cliente = _PAPEL_POLO.get(processo.polo)
    if polo_cliente not in ("ATIVO", "PASSIVO"):
        return cliente_nome, None

    oposto = "PASSIVO" if polo_cliente == "ATIVO" else "ATIVO"
    contrarias = partes.get(oposto) or []
    if not contrarias:
        return cliente_nome, None

    return cliente_nome, _juntar_nomes([p.nome for p in contrarias])
