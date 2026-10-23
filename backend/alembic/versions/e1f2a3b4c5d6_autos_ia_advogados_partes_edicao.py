"""autos_ia: edição manual da relação advogados × partes

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-23 14:00:00.000000

- autos_ia_advogados_nomes: nome de exibição por OAB (vale para todos os casos).
- autos_ia_parte_advogados: vínculos advogado ↔ parte de um caso feitos/ajustados à mão
  (advogado adicionado, principal da parte, vínculo removido).
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente (IF NOT EXISTS): funciona também onde o create_all já criou as tabelas.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_advogados_nomes (
            oab VARCHAR(40) PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            atualizado_em TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_parte_advogados (
            id UUID PRIMARY KEY,
            caso_id UUID NOT NULL REFERENCES autos_ia_casos(id) ON DELETE CASCADE,
            parte_chave VARCHAR(255) NOT NULL,
            adv_ref VARCHAR(120) NOT NULL,
            nome VARCHAR(255),
            oab VARCHAR(40),
            manual BOOLEAN NOT NULL DEFAULT false,
            principal BOOLEAN NOT NULL DEFAULT false,
            oculto BOOLEAN NOT NULL DEFAULT false,
            criado_em TIMESTAMPTZ DEFAULT now(),
            atualizado_em TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_autos_ia_parte_adv UNIQUE (caso_id, parte_chave, adv_ref)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_parte_adv_caso ON autos_ia_parte_advogados (caso_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS autos_ia_parte_advogados")
    op.execute("DROP TABLE IF EXISTS autos_ia_advogados_nomes")
