"""autos_ia_sync_pular_atual

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-27 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'autos_ia_casos',
        sa.Column('sync_pular_atual', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('autos_ia_casos', 'sync_pular_atual', server_default=None)


def downgrade() -> None:
    op.drop_column('autos_ia_casos', 'sync_pular_atual')
