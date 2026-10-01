"""autos_ia_peca_advogado_responsavel

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-01 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Coluna nullable e sem default: só metadado no Postgres, não reescreve a tabela.
    op.add_column(
        'autos_ia_pecas',
        sa.Column('advogado_responsavel', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('autos_ia_pecas', 'advogado_responsavel')
