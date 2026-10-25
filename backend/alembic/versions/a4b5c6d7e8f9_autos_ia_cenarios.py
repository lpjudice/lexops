"""autos_ia_cenarios: cenários de recuperação (planilha editável de ativos × passivos com % de realização)

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
Create Date: 2026-10-25 14:00:00.000000

Idempotente (IF NOT EXISTS); tabela nova, sem backfill.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_cenarios (
            id UUID PRIMARY KEY,
            caso_id UUID NOT NULL REFERENCES autos_ia_casos(id) ON DELETE CASCADE,
            nome VARCHAR(160) NOT NULL,
            notas TEXT,
            linhas JSONB NOT NULL DEFAULT '[]'::jsonb,
            criado_em TIMESTAMPTZ DEFAULT now(),
            atualizado_em TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_cenarios_caso ON autos_ia_cenarios (caso_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS autos_ia_cenarios")
