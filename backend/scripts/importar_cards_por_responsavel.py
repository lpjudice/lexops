"""Copia tarefas do módulo "Tarefas" para "Tarefas Cards" filtrando por responsável.

- NÃO apaga nada do módulo original.
- Agrupa/preserva o projeto (projeto_id) de cada tarefa.
- Idempotente: pula se já existe um card com mesmo (titulo, projeto_id, responsavel).

Uso (rodar a partir de backend/, com o mesmo DATABASE_URL do ambiente que tem os dados):

    ./.venv/bin/python scripts/importar_cards_por_responsavel.py --responsavel monielly --dry-run
    ./.venv/bin/python scripts/importar_cards_por_responsavel.py --responsavel monielly

`--responsavel` é um trecho case-insensitive (ILIKE %trecho%).
"""

import argparse
import sys

from sqlalchemy import func

# Importa o app completo para registrar TODOS os mappers do SQLAlchemy
# (relacionamentos cruzados como Anotacao->Reuniao exigem todos os models carregados).
import app.main  # noqa: F401
from app.database import SessionLocal
from app.models.tarefa import Tarefa
from app.models.tarefa_card import TarefaCard
from app.models.tarefa_projeto import TarefaProjeto


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--responsavel", default="monielly", help="trecho do nome do responsável (ILIKE)")
    parser.add_argument("--dry-run", action="store_true", help="apenas lista, sem gravar")
    args = parser.parse_args()

    padrao = f"%{args.responsavel.strip()}%"
    db = SessionLocal()
    try:
        tarefas = (
            db.query(Tarefa)
            .filter(Tarefa.responsavel.ilike(padrao))
            .order_by(Tarefa.projeto_id, Tarefa.created_at)
            .all()
        )

        if not tarefas:
            print(f"Nenhuma tarefa com responsável ~ '{args.responsavel}'.")
            return 0

        # Nomes de projeto para exibição
        projetos = {p.id: p.nome for p in db.query(TarefaProjeto).all()}

        criados = 0
        pulados = 0
        por_projeto: dict[str, int] = {}

        for t in tarefas:
            proj_nome = projetos.get(t.projeto_id, "Sem projeto") if t.projeto_id else "Sem projeto"

            # Idempotência: já existe card equivalente?
            existe = (
                db.query(TarefaCard)
                .filter(
                    func.lower(TarefaCard.titulo) == (t.titulo or "").lower(),
                    TarefaCard.projeto_id.is_(t.projeto_id) if t.projeto_id is None else TarefaCard.projeto_id == t.projeto_id,
                    TarefaCard.responsavel.ilike(padrao),
                )
                .first()
            )
            if existe:
                pulados += 1
                continue

            por_projeto[proj_nome] = por_projeto.get(proj_nome, 0) + 1

            if not args.dry_run:
                card = TarefaCard(
                    projeto_id=t.projeto_id,
                    cliente_id=t.cliente_id,
                    processo_id=t.processo_id,
                    criado_por_id=t.criado_por_id,
                    titulo=t.titulo,
                    descricao=t.descricao,
                    responsavel=t.responsavel,
                    responsavel_email=t.responsavel_email,
                    status=t.status or "pendente",
                    data_limite=t.data_limite,
                    confidencial=bool(t.confidencial),
                    usuarios_com_acesso=list(t.usuarios_com_acesso or []),
                )
                db.add(card)
                criados += 1

        if not args.dry_run:
            db.commit()

        print(f"Responsável ~ '{args.responsavel}': {len(tarefas)} tarefa(s) encontradas.")
        print("Por projeto (a copiar):")
        for nome, n in sorted(por_projeto.items()):
            print(f"  - {nome}: {n}")
        if args.dry_run:
            total = sum(por_projeto.values())
            print(f"\n[DRY-RUN] {total} card(s) seriam criados, {pulados} já existiam. Nada foi gravado.")
        else:
            print(f"\n✅ {criados} card(s) criados, {pulados} já existiam (pulados).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
