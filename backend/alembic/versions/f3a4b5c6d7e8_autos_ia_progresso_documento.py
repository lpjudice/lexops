"""autos_ia_progresso_documento

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('autos_ia_documentos', sa.Column('etapa', sa.String(length=30), nullable=True))
    op.add_column('autos_ia_documentos', sa.Column('paginas_processadas', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('autos_ia_documentos', sa.Column('pecas_resumidas', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('autos_ia_documentos', 'pecas_resumidas')
    op.drop_column('autos_ia_documentos', 'paginas_processadas')
    op.drop_column('autos_ia_documentos', 'etapa')
