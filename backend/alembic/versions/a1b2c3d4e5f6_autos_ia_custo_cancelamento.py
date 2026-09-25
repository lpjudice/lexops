"""autos_ia_custo_cancelamento

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-09-25 08:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Custo real (USD) acumulado a partir do `usage` de cada chamada de IA ──
    op.add_column('autos_ia_casos', sa.Column('custo_usd_total', sa.Float(), nullable=False, server_default='0'))
    op.add_column('autos_ia_documentos', sa.Column('custo_usd', sa.Float(), nullable=False, server_default='0'))
    op.add_column('autos_ia_pecas', sa.Column('custo_usd', sa.Float(), nullable=False, server_default='0'))

    # ── Progresso estruturado + cancelamento da sincronização jus.br/Drive ──
    op.add_column('autos_ia_casos', sa.Column('sync_etapa', sa.String(length=20), nullable=True))
    op.add_column('autos_ia_casos', sa.Column('sync_total_itens', sa.Integer(), nullable=True))
    op.add_column('autos_ia_casos', sa.Column('sync_itens_processados', sa.Integer(), nullable=True))
    op.add_column('autos_ia_casos', sa.Column('sync_iniciado_em', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'autos_ia_casos',
        sa.Column('sync_cancelar', sa.Boolean(), nullable=False, server_default='false'),
    )

    # ── Cancelamento do upload/processamento manual de bloco ──
    op.add_column(
        'autos_ia_documentos',
        sa.Column('cancelar', sa.Boolean(), nullable=False, server_default='false'),
    )

    # ── FKs com ON DELETE CASCADE — sem isso, apagar um caso que já tem peças com
    # referências no grafo falha com violação de FK (autos_ia_referencias aponta
    # pra autos_ia_pecas dos dois lados, origem e destino). Recria as constraints
    # existentes (nomes padrão do Postgres pra FK inline sem nome explícito). ──
    op.drop_constraint('autos_ia_documentos_caso_id_fkey', 'autos_ia_documentos', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_documentos_caso_id_fkey', 'autos_ia_documentos', 'autos_ia_casos',
        ['caso_id'], ['id'], ondelete='CASCADE',
    )

    op.drop_constraint('autos_ia_pecas_caso_id_fkey', 'autos_ia_pecas', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_pecas_caso_id_fkey', 'autos_ia_pecas', 'autos_ia_casos',
        ['caso_id'], ['id'], ondelete='CASCADE',
    )

    op.drop_constraint('autos_ia_pecas_documento_id_fkey', 'autos_ia_pecas', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_pecas_documento_id_fkey', 'autos_ia_pecas', 'autos_ia_documentos',
        ['documento_id'], ['id'], ondelete='CASCADE',
    )

    op.drop_constraint('autos_ia_pecas_peca_pai_id_fkey', 'autos_ia_pecas', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_pecas_peca_pai_id_fkey', 'autos_ia_pecas', 'autos_ia_pecas',
        ['peca_pai_id'], ['id'], ondelete='CASCADE',
    )

    op.drop_constraint('autos_ia_referencias_caso_id_fkey', 'autos_ia_referencias', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_referencias_caso_id_fkey', 'autos_ia_referencias', 'autos_ia_casos',
        ['caso_id'], ['id'], ondelete='CASCADE',
    )

    op.drop_constraint('autos_ia_referencias_peca_origem_id_fkey', 'autos_ia_referencias', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_referencias_peca_origem_id_fkey', 'autos_ia_referencias', 'autos_ia_pecas',
        ['peca_origem_id'], ['id'], ondelete='CASCADE',
    )

    op.drop_constraint('autos_ia_referencias_peca_destino_id_fkey', 'autos_ia_referencias', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_referencias_peca_destino_id_fkey', 'autos_ia_referencias', 'autos_ia_pecas',
        ['peca_destino_id'], ['id'], ondelete='CASCADE',
    )

    op.drop_constraint('autos_ia_faq_caso_id_fkey', 'autos_ia_faq', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_faq_caso_id_fkey', 'autos_ia_faq', 'autos_ia_casos',
        ['caso_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('autos_ia_faq_caso_id_fkey', 'autos_ia_faq', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_faq_caso_id_fkey', 'autos_ia_faq', 'autos_ia_casos', ['caso_id'], ['id'],
    )

    op.drop_constraint('autos_ia_referencias_peca_destino_id_fkey', 'autos_ia_referencias', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_referencias_peca_destino_id_fkey', 'autos_ia_referencias', 'autos_ia_pecas',
        ['peca_destino_id'], ['id'],
    )

    op.drop_constraint('autos_ia_referencias_peca_origem_id_fkey', 'autos_ia_referencias', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_referencias_peca_origem_id_fkey', 'autos_ia_referencias', 'autos_ia_pecas',
        ['peca_origem_id'], ['id'],
    )

    op.drop_constraint('autos_ia_referencias_caso_id_fkey', 'autos_ia_referencias', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_referencias_caso_id_fkey', 'autos_ia_referencias', 'autos_ia_casos', ['caso_id'], ['id'],
    )

    op.drop_constraint('autos_ia_pecas_peca_pai_id_fkey', 'autos_ia_pecas', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_pecas_peca_pai_id_fkey', 'autos_ia_pecas', 'autos_ia_pecas', ['peca_pai_id'], ['id'],
    )

    op.drop_constraint('autos_ia_pecas_documento_id_fkey', 'autos_ia_pecas', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_pecas_documento_id_fkey', 'autos_ia_pecas', 'autos_ia_documentos', ['documento_id'], ['id'],
    )

    op.drop_constraint('autos_ia_pecas_caso_id_fkey', 'autos_ia_pecas', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_pecas_caso_id_fkey', 'autos_ia_pecas', 'autos_ia_casos', ['caso_id'], ['id'],
    )

    op.drop_constraint('autos_ia_documentos_caso_id_fkey', 'autos_ia_documentos', type_='foreignkey')
    op.create_foreign_key(
        'autos_ia_documentos_caso_id_fkey', 'autos_ia_documentos', 'autos_ia_casos', ['caso_id'], ['id'],
    )

    op.drop_column('autos_ia_documentos', 'cancelar')

    op.drop_column('autos_ia_casos', 'sync_cancelar')
    op.drop_column('autos_ia_casos', 'sync_iniciado_em')
    op.drop_column('autos_ia_casos', 'sync_itens_processados')
    op.drop_column('autos_ia_casos', 'sync_total_itens')
    op.drop_column('autos_ia_casos', 'sync_etapa')

    op.drop_column('autos_ia_pecas', 'custo_usd')
    op.drop_column('autos_ia_documentos', 'custo_usd')
    op.drop_column('autos_ia_casos', 'custo_usd_total')
