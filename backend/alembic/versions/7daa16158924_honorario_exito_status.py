"""honorario_exito_status

Revision ID: 7daa16158924
Revises: 78046b9666da
Create Date: 2026-10-27 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7daa16158924'
down_revision: Union[str, Sequence[str], None] = '78046b9666da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'honorarios',
        sa.Column('exito_status', sa.String(length=20), nullable=False, server_default='estimado'),
    )
    op.alter_column('honorarios', 'exito_status', server_default=None)


def downgrade() -> None:
    op.drop_column('honorarios', 'exito_status')
