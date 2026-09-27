"""whatsapp_notificacao

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-27 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'andamentos_processo',
        sa.Column('notificado_whatsapp', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('andamentos_processo', 'notificado_whatsapp', server_default=None)
    op.add_column(
        'processos',
        sa.Column('notificar_whatsapp', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('processos', 'notificar_whatsapp', server_default=None)


def downgrade() -> None:
    op.drop_column('processos', 'notificar_whatsapp')
    op.drop_column('andamentos_processo', 'notificado_whatsapp')
