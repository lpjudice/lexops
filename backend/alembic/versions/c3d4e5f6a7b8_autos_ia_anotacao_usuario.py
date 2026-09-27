"""autos_ia_anotacao_usuario

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-26 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('autos_ia_pecas', sa.Column('nota_usuario', sa.Text(), nullable=True))
    op.add_column(
        'autos_ia_pecas',
        sa.Column('keywords_usuario', postgresql.ARRAY(sa.String(length=100)), nullable=True),
    )
    op.add_column('autos_ia_pecas', sa.Column('titulo_customizado', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('autos_ia_pecas', 'titulo_customizado')
    op.drop_column('autos_ia_pecas', 'keywords_usuario')
    op.drop_column('autos_ia_pecas', 'nota_usuario')
