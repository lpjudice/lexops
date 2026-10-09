"""autos_ia_peca_alertas

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('autos_ia_pecas', sa.Column('alerta_telegram_em', sa.DateTime(timezone=True), nullable=True))
    op.add_column('autos_ia_pecas', sa.Column('alerta_email_em', sa.DateTime(timezone=True), nullable=True))
    # Tudo que já existe hoje conta como "já alertado": o alerta é só do que
    # chegar DEPOIS desta migração — senão o primeiro disparo despejaria o
    # histórico inteiro (centenas de peças) no Telegram e no e-mail.
    op.execute(
        "UPDATE autos_ia_pecas SET alerta_telegram_em = now(), alerta_email_em = now() "
        "WHERE alerta_telegram_em IS NULL OR alerta_email_em IS NULL"
    )


def downgrade() -> None:
    op.drop_column('autos_ia_pecas', 'alerta_email_em')
    op.drop_column('autos_ia_pecas', 'alerta_telegram_em')
