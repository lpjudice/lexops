"""honorario_exito_conta_financeiro

Revision ID: 78046b9666da
Revises: b5c6d7e8f9a0
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '78046b9666da'
down_revision: Union[str, Sequence[str], None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'honorarios',
        sa.Column('exito_conta_financeiro', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column('honorarios', 'exito_conta_financeiro', server_default=None)


def downgrade() -> None:
    op.drop_column('honorarios', 'exito_conta_financeiro')
