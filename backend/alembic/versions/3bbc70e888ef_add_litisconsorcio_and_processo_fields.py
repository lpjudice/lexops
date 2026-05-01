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


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)

    # New columns for clientes
    if not _has_column(inspector, 'clientes', 'incompleto'):
        op.add_column('clientes', sa.Column('incompleto', sa.Boolean(), server_default='false', nullable=False))

    # New columns for processos
    if not _has_column(inspector, 'processos', 'serventia'):
        op.add_column('processos', sa.Column('serventia', sa.String(length=100), nullable=True))
    if not _has_column(inspector, 'processos', 'foro'):
        op.add_column('processos', sa.Column('foro', sa.String(length=100), nullable=True))
    if not _has_column(inspector, 'processos', 'sistema_juridico'):
        op.add_column('processos', sa.Column('sistema_juridico', sa.String(length=20), nullable=True))
    if not _has_column(inspector, 'processos', 'grau'):
        op.add_column('processos', sa.Column('grau', sa.String(length=20), nullable=True))
    if not _has_column(inspector, 'processos', 'grau_texto'):
        op.add_column('processos', sa.Column('grau_texto', sa.String(length=100), nullable=True))

    # Litisconsórcio association table (create only if not already present)
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
