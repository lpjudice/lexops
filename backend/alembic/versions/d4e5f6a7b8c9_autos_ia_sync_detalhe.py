"""autos_ia_sync_detalhe

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-26 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('autos_ia_casos', sa.Column('sync_detalhe', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('autos_ia_casos', 'sync_detalhe')
