"""autos_ia_fatos: banco de fatos com evidência (valores, e depois determinações, posições, saldos)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-25 12:00:00.000000

Cada fato aponta para a peça de origem e guarda o trecho — nada é "verdade" sem fonte clicável.
`status`: extraido (da IA) | validado (confirmado/editado por pessoa) | rejeitado.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente (IF NOT EXISTS). Colunas novas em autos_ia_pecas são nullable, sem default e
    # sem backfill (só metadado no Postgres).
    op.execute("ALTER TABLE autos_ia_pecas ADD COLUMN IF NOT EXISTS fatos_valores_hash VARCHAR(64)")
    op.execute("ALTER TABLE autos_ia_pecas ADD COLUMN IF NOT EXISTS fatos_valores_em TIMESTAMPTZ")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_fatos (
            id UUID PRIMARY KEY,
            caso_id UUID NOT NULL REFERENCES autos_ia_casos(id) ON DELETE CASCADE,
            peca_id UUID NOT NULL REFERENCES autos_ia_pecas(id) ON DELETE CASCADE,
            tipo VARCHAR(30) NOT NULL,
            tema VARCHAR(60),
            sujeito VARCHAR(255),
            sujeito_canonico VARCHAR(255),
            natureza VARCHAR(40),
            fonte_citada VARCHAR(255),
            valor_centavos BIGINT,
            data_ref VARCHAR(10),
            rotulo_original VARCHAR(120),
            trecho TEXT,
            pos INTEGER NOT NULL DEFAULT 0,
            confianca REAL,
            origem VARCHAR(20) NOT NULL DEFAULT 'ia',
            status VARCHAR(20) NOT NULL DEFAULT 'extraido',
            nota TEXT,
            dados JSONB,
            criado_em TIMESTAMPTZ DEFAULT now(),
            atualizado_em TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_autos_ia_fato_peca_pos UNIQUE (peca_id, tipo, pos)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_fatos_caso_tipo ON autos_ia_fatos (caso_id, tipo)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_fatos_valor ON autos_ia_fatos (caso_id, valor_centavos)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS autos_ia_fatos")
    op.execute("ALTER TABLE autos_ia_pecas DROP COLUMN IF EXISTS fatos_valores_em")
    op.execute("ALTER TABLE autos_ia_pecas DROP COLUMN IF EXISTS fatos_valores_hash")
