"""add_responsavel_prazo_and_contrato_orfao

Revision ID: b4c5d6e7f8a9
Revises: 3bbc70e888ef
Create Date: 2026-04-23 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = '3bbc70e888ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    prazo_cols = {col["name"] for col in inspector.get_columns('prazos')}
    honorario_cols = {col["name"] for col in inspector.get_columns('honorarios')}

    if 'responsavel' not in prazo_cols:
        op.add_column('prazos', sa.Column('responsavel', sa.String(length=100), nullable=True))
    if 'contrato_orfao' not in honorario_cols:
        op.add_column('honorarios', sa.Column('contrato_orfao', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('honorarios', 'contrato_orfao')
    op.drop_column('prazos', 'responsavel')
