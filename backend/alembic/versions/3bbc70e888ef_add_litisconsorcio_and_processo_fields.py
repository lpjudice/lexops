"""add_litisconsorcio_and_processo_fields

Revision ID: 3bbc70e888ef
Revises: 
Create Date: 2026-04-23 01:10:06.252484

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3bbc70e888ef'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # New columns for clientes
    op.add_column('clientes', sa.Column('incompleto', sa.Boolean(), server_default='false', nullable=False))

    # New columns for processos
    op.add_column('processos', sa.Column('serventia', sa.String(length=100), nullable=True))
    op.add_column('processos', sa.Column('foro', sa.String(length=100), nullable=True))
    op.add_column('processos', sa.Column('sistema_juridico', sa.String(length=20), nullable=True))
    op.add_column('processos', sa.Column('grau', sa.String(length=20), nullable=True))
    op.add_column('processos', sa.Column('grau_texto', sa.String(length=100), nullable=True))

    # Litisconsórcio association table (create only if not already present)
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'processo_clientes' not in inspector.get_table_names():
        op.create_table(
            'processo_clientes',
            sa.Column('processo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('processos.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('polo', sa.String(length=50), nullable=True),
            sa.Column('principal', sa.Boolean(), nullable=True, default=False),
        )


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'processo_clientes' in inspector.get_table_names():
        op.drop_table('processo_clientes')
    op.drop_column('processos', 'grau_texto')
    op.drop_column('processos', 'grau')
    op.drop_column('processos', 'sistema_juridico')
    op.drop_column('processos', 'foro')
    op.drop_column('processos', 'serventia')
    op.drop_column('clientes', 'incompleto')
