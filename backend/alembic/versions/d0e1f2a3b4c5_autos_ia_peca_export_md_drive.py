"""autos_ia_pecas: controle da exportação .md (resumo + inteiro teor) para o Drive

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente (IF NOT EXISTS) e só metadado no Postgres: colunas nullable, sem default
    # e sem backfill — não reescreve a tabela. Peças já existentes ficam "ainda não exportadas".
    op.execute("ALTER TABLE autos_ia_pecas ADD COLUMN IF NOT EXISTS md_drive_file_id VARCHAR(100)")
    op.execute("ALTER TABLE autos_ia_pecas ADD COLUMN IF NOT EXISTS md_hash VARCHAR(64)")
    op.execute("ALTER TABLE autos_ia_pecas ADD COLUMN IF NOT EXISTS md_exportado_em TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE autos_ia_pecas DROP COLUMN IF EXISTS md_exportado_em")
    op.execute("ALTER TABLE autos_ia_pecas DROP COLUMN IF EXISTS md_hash")
    op.execute("ALTER TABLE autos_ia_pecas DROP COLUMN IF EXISTS md_drive_file_id")
