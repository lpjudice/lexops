"""Mescla manualmente 2+ linhas de `clientes` que são a MESMA pessoa/empresa
cadastrada em duplicidade (nome igual/quase-igual). SEMPRE disparado por ação
humana explícita (botão "Mesclar" na tela de revisão) — nunca automático,
por decisão do Lucas: mesclar errado é mais arriscado que deixar duplicado.

Reatribui todas as referências (processos, contratos, tarefas, reembolsos,
etc.) da(s) linha(s) extra para a linha canônica, mescla a pasta do Drive se
os dois já tiverem pastas diferentes, e só então apaga as linhas extras.
"""
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Tabelas com FK simples (coluna própria com PK `id`) apontando para clientes.id.
# Levantado via information_schema em produção — atualizar se um novo módulo
# ganhar uma FK para `clientes`.
_FK_SIMPLES: list[tuple[str, str]] = [
    ("anotacoes", "cliente_id"),
    ("cliente_cadastro_links", "cliente_id"),
    ("cliente_cadastro_submissoes", "cliente_id_alvo"),
    ("contratos", "cliente_id"),
    ("conversas_ia", "cliente_id"),
    ("emails_cliente", "cliente_id"),
    ("honorarios", "cliente_id"),
    ("memorias_estrategicas", "cliente_id"),
    ("patrimonio_bens", "cliente_id"),
    ("precedentcheck_analises", "cliente_id"),
    ("processos", "cliente_id"),
    ("reembolsos", "cliente_id"),
    ("reunioes", "cliente_id"),
    ("tarefa_cards", "cliente_id"),
    ("tarefas", "cliente_id"),
    ("telegram_task_items", "cliente_inferido_id"),
    ("teses", "cliente_id"),
]

# Tabelas associativas com PK composta (cliente_id, outra_coluna) — não têm
# `id` próprio, então um conflito de unicidade precisa ser resolvido linha a
# linha (se o vínculo já existir para o cliente canônico, descarta o da extra).
_FK_ASSOCIATIVAS: list[tuple[str, str]] = [
    ("processo_clientes", "processo_id"),
    ("user_clientes", "usuario_id"),
]


def _mover_fk_simples(db: Session, tabela: str, coluna: str, extra_id: str, canonical_id: str) -> int:
    try:
        with db.begin_nested():
            r = db.execute(
                text(f"UPDATE {tabela} SET {coluna} = :c WHERE {coluna} = :e"),
                {"c": canonical_id, "e": extra_id},
            )
            return r.rowcount
    except IntegrityError:
        # Conflito de unicidade (ex.: índice único que inclua cliente_id):
        # resolve linha a linha, descartando a da extra quando colidir.
        movidos = 0
        linhas = db.execute(
            text(f"SELECT id FROM {tabela} WHERE {coluna} = :e"), {"e": extra_id}
        ).fetchall()
        for (rid,) in linhas:
            try:
                with db.begin_nested():
                    db.execute(text(f"UPDATE {tabela} SET {coluna} = :c WHERE id = :rid"),
                               {"c": canonical_id, "rid": rid})
                movidos += 1
            except IntegrityError:
                with db.begin_nested():
                    db.execute(text(f"DELETE FROM {tabela} WHERE id = :rid"), {"rid": rid})
        return movidos


def _mover_fk_associativa(db: Session, tabela: str, outra_coluna: str, extra_id: str, canonical_id: str) -> int:
    linhas = db.execute(
        text(f"SELECT {outra_coluna} FROM {tabela} WHERE cliente_id = :e"), {"e": extra_id}
    ).fetchall()
    total = 0
    for (outro_val,) in linhas:
        existe = db.execute(
            text(f"SELECT 1 FROM {tabela} WHERE cliente_id = :c AND {outra_coluna} = :o"),
            {"c": canonical_id, "o": outro_val},
        ).first()
        if existe:
            db.execute(
                text(f"DELETE FROM {tabela} WHERE cliente_id = :e AND {outra_coluna} = :o"),
                {"e": extra_id, "o": outro_val},
            )
        else:
            db.execute(
                text(f"UPDATE {tabela} SET cliente_id = :c WHERE cliente_id = :e AND {outra_coluna} = :o"),
                {"c": canonical_id, "e": extra_id, "o": outro_val},
            )
        total += 1
    return total


def mesclar_clientes(ids: list[uuid.UUID | str], canonical_id: uuid.UUID | str, db: Session) -> dict:
    """Mescla as linhas de `ids` na linha `canonical_id`: move tudo que
    referenciava as extras (processos, contratos, tarefas, etc.), mescla as
    pastas do Drive se forem diferentes, e apaga as linhas extras.
    Nunca perde arquivo: a mesclagem de pasta (drive_folder_heal.mesclar_cluster)
    só joga pasta na lixeira depois de confirmar que ficou vazia."""
    canonical_id = str(canonical_id)
    extras = [str(i) for i in ids if str(i) != canonical_id]
    if not extras:
        return {"ok": False, "erro": "nada_para_mesclar"}

    canon_existe = db.execute(text("SELECT 1 FROM clientes WHERE id = :c"), {"c": canonical_id}).first()
    if not canon_existe:
        return {"ok": False, "erro": "cliente_canonico_nao_encontrado"}

    movidos: dict[str, int] = {}
    for tabela, coluna in _FK_SIMPLES:
        total = sum(_mover_fk_simples(db, tabela, coluna, extra, canonical_id) for extra in extras)
        if total:
            movidos[f"{tabela}.{coluna}"] = total
    for tabela, outra_coluna in _FK_ASSOCIATIVAS:
        total = sum(_mover_fk_associativa(db, tabela, outra_coluna, extra, canonical_id) for extra in extras)
        if total:
            movidos[f"{tabela}.cliente_id"] = total

    # Pastas do Drive: se alguma linha (extra ou canônica) tiver pasta própria
    # diferente da canônica, mescla o conteúdo pra dentro da canônica.
    todos_ids = [canonical_id, *extras]
    folder_rows = db.execute(
        text("SELECT DISTINCT drive_folder_id FROM clientes "
             "WHERE id::text = ANY(:ids) AND drive_folder_id IS NOT NULL"),
        {"ids": todos_ids},
    ).fetchall()
    folder_ids = [row[0] for row in folder_rows]
    drive_resultado = None
    if len(folder_ids) > 1:
        from app.services import drive_folder_heal as heal
        canon_folder_row = db.execute(
            text("SELECT drive_folder_id FROM clientes WHERE id = :c"), {"c": canonical_id}
        ).first()
        canon_folder = canon_folder_row[0] if canon_folder_row else None
        drive_resultado = heal.mesclar_cluster(folder_ids, canon_folder)
        if drive_resultado.get("ok"):
            db.execute(
                text("UPDATE clientes SET drive_folder_id = :f WHERE id::text = ANY(:ids)"),
                {"f": drive_resultado["canonical_id"], "ids": todos_ids},
            )
    elif len(folder_ids) == 1:
        # Só uma das linhas tinha pasta — garante que a canônica fique com ela.
        db.execute(
            text("UPDATE clientes SET drive_folder_id = :f WHERE id = :c AND drive_folder_id IS NULL"),
            {"f": folder_ids[0], "c": canonical_id},
        )

    db.execute(text("DELETE FROM clientes WHERE id::text = ANY(:ids)"), {"ids": extras})
    db.commit()

    logger.info("Clientes mesclados: extras=%s -> canonical=%s (linhas_movidas=%s)",
                extras, canonical_id, movidos)
    return {
        "ok": True,
        "canonical_id": canonical_id,
        "removidos": extras,
        "linhas_movidas": movidos,
        "drive": drive_resultado,
    }
