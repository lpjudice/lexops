"""add_autos_ia_tables

Revision ID: d1e2f3a4b5c6
Revises: b4c5d6e7f8a9
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'autos_ia_casos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('nome', sa.String(length=255), nullable=False),
        sa.Column('numero_processo', sa.String(length=50), nullable=True),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ativo'),
        sa.Column('total_paginas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('buffer_incompleto', sa.Text(), nullable=True),
        sa.Column('buffer_pagina_inicio', sa.Integer(), nullable=True),
        sa.Column('criado_por_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'autos_ia_documentos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('caso_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('autos_ia_casos.id'), nullable=False),
        sa.Column('nome_arquivo', sa.String(length=500), nullable=False),
        sa.Column('caminho_arquivo', sa.String(length=1000), nullable=False),
        sa.Column('pagina_inicio', sa.Integer(), nullable=False),
        sa.Column('pagina_fim', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pendente'),
        sa.Column('erro_mensagem', sa.Text(), nullable=True),
        sa.Column('pecas_geradas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('paginas_ocr', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_autos_ia_documentos_caso_id', 'autos_ia_documentos', ['caso_id'])

    op.create_table(
        'autos_ia_pecas',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('caso_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('autos_ia_casos.id'), nullable=False),
        sa.Column('documento_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('autos_ia_documentos.id'), nullable=True),
        sa.Column('tipo', sa.String(length=50), nullable=False, server_default='outro'),
        sa.Column('titulo', sa.String(length=500), nullable=False),
        sa.Column('autor', sa.String(length=255), nullable=True),
        sa.Column('data_peca', sa.Date(), nullable=True),
        sa.Column('id_processual', sa.String(length=100), nullable=True),
        sa.Column('pagina_inicio', sa.Integer(), nullable=False),
        sa.Column('pagina_fim', sa.Integer(), nullable=False),
        sa.Column('texto_md', sa.Text(), nullable=False),
        sa.Column('resumo', sa.Text(), nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.String(length=100)), nullable=True),
        sa.Column('ids_mencionados', postgresql.ARRAY(sa.String(length=100)), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pendente_resumo'),
        sa.Column('erro_mensagem', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_autos_ia_pecas_caso_id', 'autos_ia_pecas', ['caso_id'])
    op.create_index('ix_autos_ia_pecas_id_processual', 'autos_ia_pecas', ['id_processual'])
    op.create_index('ix_autos_ia_pecas_data_peca', 'autos_ia_pecas', ['data_peca'])
    op.execute(
        "CREATE INDEX ix_autos_ia_pecas_fts ON autos_ia_pecas "
        "USING gin (to_tsvector('portuguese', "
        "coalesce(titulo, '') || ' ' || coalesce(resumo, '') || ' ' || coalesce(texto_md, '')))"
    )

    op.create_table(
        'autos_ia_referencias',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('caso_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('autos_ia_casos.id'), nullable=False),
        sa.Column('peca_origem_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('autos_ia_pecas.id'), nullable=False),
        sa.Column('peca_destino_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('autos_ia_pecas.id'), nullable=True),
        sa.Column('id_mencionado', sa.String(length=100), nullable=False),
        sa.Column('contexto', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_autos_ia_referencias_caso_id', 'autos_ia_referencias', ['caso_id'])
    op.create_index('ix_autos_ia_referencias_peca_origem_id', 'autos_ia_referencias', ['peca_origem_id'])
    op.create_index('ix_autos_ia_referencias_id_mencionado', 'autos_ia_referencias', ['id_mencionado'])

    op.create_table(
        'autos_ia_faq',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('caso_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('autos_ia_casos.id'), nullable=False),
        sa.Column('pergunta', sa.Text(), nullable=False),
        sa.Column('resposta', sa.Text(), nullable=True),
        sa.Column('pecas_relacionadas', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pendente'),
        sa.Column('erro_mensagem', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_autos_ia_faq_caso_id', 'autos_ia_faq', ['caso_id'])


def downgrade() -> None:
    op.drop_table('autos_ia_faq')
    op.drop_table('autos_ia_referencias')
    op.execute('DROP INDEX IF EXISTS ix_autos_ia_pecas_fts')
    op.drop_table('autos_ia_pecas')
    op.drop_table('autos_ia_documentos')
    op.drop_table('autos_ia_casos')
