"""autos_ia_vinculo_processo_e_anexos

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('autos_ia_casos', sa.Column('processo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('processos.id'), nullable=True))
    op.add_column('autos_ia_casos', sa.Column('sync_jusbr_ativo', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('autos_ia_casos', sa.Column('ultima_sincronizacao_em', sa.DateTime(timezone=True), nullable=True))
    op.add_column('autos_ia_casos', sa.Column('ultimo_sync_status', sa.String(length=20), nullable=True))
    op.add_column('autos_ia_casos', sa.Column('ultimo_sync_mensagem', sa.Text(), nullable=True))
    op.create_index('ix_autos_ia_casos_processo_id', 'autos_ia_casos', ['processo_id'])

    op.add_column('autos_ia_pecas', sa.Column('andamento_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('andamentos_processo.id'), nullable=True))
    op.add_column('autos_ia_pecas', sa.Column('peca_pai_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('autos_ia_pecas.id'), nullable=True))
    op.create_index('ix_autos_ia_pecas_andamento_id', 'autos_ia_pecas', ['andamento_id'], unique=True)
    op.create_index('ix_autos_ia_pecas_peca_pai_id', 'autos_ia_pecas', ['peca_pai_id'])


def downgrade() -> None:
    op.drop_index('ix_autos_ia_pecas_peca_pai_id', table_name='autos_ia_pecas')
    op.drop_index('ix_autos_ia_pecas_andamento_id', table_name='autos_ia_pecas')
    op.drop_column('autos_ia_pecas', 'peca_pai_id')
    op.drop_column('autos_ia_pecas', 'andamento_id')

    op.drop_index('ix_autos_ia_casos_processo_id', table_name='autos_ia_casos')
    op.drop_column('autos_ia_casos', 'ultimo_sync_mensagem')
    op.drop_column('autos_ia_casos', 'ultimo_sync_status')
    op.drop_column('autos_ia_casos', 'ultima_sincronizacao_em')
    op.drop_column('autos_ia_casos', 'sync_jusbr_ativo')
    op.drop_column('autos_ia_casos', 'processo_id')
