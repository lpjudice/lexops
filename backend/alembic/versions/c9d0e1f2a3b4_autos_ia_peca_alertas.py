"""autos_ia_alertas (controle por andamento + configuração)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente (IF NOT EXISTS): funciona também onde o create_all já criou a tabela
    # nova (ambiente local/teste) — o que ele não faz é adicionar colunas a tabela existente.
    #
    # Colunas nullable, sem default e sem backfill: só metadado no Postgres (instantâneo,
    # não reescreve a tabela). O histórico anterior fica fora dos alertas pelo marco
    # `inicio_alertas_em` abaixo — nenhuma linha antiga precisa ser tocada.
    op.execute("ALTER TABLE andamentos_processo ADD COLUMN IF NOT EXISTS alerta_autos_ia_telegram_em TIMESTAMPTZ")
    op.execute("ALTER TABLE andamentos_processo ADD COLUMN IF NOT EXISTS alerta_autos_ia_email_em TIMESTAMPTZ")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_alerta_config (
            id INTEGER PRIMARY KEY,
            ativo BOOLEAN NOT NULL DEFAULT true,
            emails_extras JSONB NOT NULL DEFAULT '[]'::jsonb,
            inicio_alertas_em TIMESTAMPTZ NOT NULL DEFAULT now(),
            atualizado_em TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    # Linha única: só andamentos criados a partir de agora entram nos alertas.
    op.execute("INSERT INTO autos_ia_alerta_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS autos_ia_alerta_config")
    op.execute("ALTER TABLE andamentos_processo DROP COLUMN IF EXISTS alerta_autos_ia_email_em")
    op.execute("ALTER TABLE andamentos_processo DROP COLUMN IF EXISTS alerta_autos_ia_telegram_em")
