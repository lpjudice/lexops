"""autos_ia_estrutura_grupo: empresas do grupo, participações societárias e relação de créditos (planilha)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-10-26 10:00:00.000000

Idempotente (IF NOT EXISTS); tabelas novas, sem backfill.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, Sequence[str], None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_entidades (
            id UUID PRIMARY KEY,
            caso_id UUID NOT NULL REFERENCES autos_ia_casos(id) ON DELETE CASCADE,
            cnpj VARCHAR(14) NOT NULL,
            nome VARCHAR(255) NOT NULL,
            nivel VARCHAR(40),
            descricao TEXT,
            origem VARCHAR(20) NOT NULL DEFAULT 'organograma',
            criado_em TIMESTAMPTZ DEFAULT now(),
            atualizado_em TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_autos_ia_entidade_caso_cnpj UNIQUE (caso_id, cnpj)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_participacoes (
            id UUID PRIMARY KEY,
            caso_id UUID NOT NULL REFERENCES autos_ia_casos(id) ON DELETE CASCADE,
            pai_cnpj VARCHAR(14) NOT NULL,
            filho_cnpj VARCHAR(14) NOT NULL,
            pct NUMERIC(7,4),
            tracejado BOOLEAN NOT NULL DEFAULT false,
            origem VARCHAR(20) NOT NULL DEFAULT 'organograma',
            status VARCHAR(20) NOT NULL DEFAULT 'extraido',
            nota TEXT,
            criado_em TIMESTAMPTZ DEFAULT now(),
            atualizado_em TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_autos_ia_participacao UNIQUE (caso_id, pai_cnpj, filho_cnpj)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_credito_lotes (
            id UUID PRIMARY KEY,
            caso_id UUID NOT NULL REFERENCES autos_ia_casos(id) ON DELETE CASCADE,
            nome_arquivo VARCHAR(255),
            total_linhas INTEGER NOT NULL DEFAULT 0,
            total_centavos BIGINT NOT NULL DEFAULT 0,
            ativo BOOLEAN NOT NULL DEFAULT true,
            notas TEXT,
            importado_em TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autos_ia_creditos (
            id UUID PRIMARY KEY,
            lote_id UUID NOT NULL REFERENCES autos_ia_credito_lotes(id) ON DELETE CASCADE,
            caso_id UUID NOT NULL REFERENCES autos_ia_casos(id) ON DELETE CASCADE,
            linha INTEGER,
            devedor_cnpj VARCHAR(14),
            devedor_nome VARCHAR(255),
            credor_cnpj VARCHAR(14),
            credor_nome VARCHAR(255),
            credor_endereco TEXT,
            credor_email VARCHAR(255),
            natureza VARCHAR(400),
            classe VARCHAR(60),
            valor_centavos BIGINT NOT NULL DEFAULT 0,
            data_base DATE,
            vencimento DATE,
            coobrigados TEXT,
            pagina_pdf INTEGER,
            categoria VARCHAR(80),
            subcategoria VARCHAR(160)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_entidades_caso ON autos_ia_entidades (caso_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_participacoes_caso ON autos_ia_participacoes (caso_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_credito_lotes_caso ON autos_ia_credito_lotes (caso_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_creditos_lote ON autos_ia_creditos (lote_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_autos_ia_creditos_caso_dev ON autos_ia_creditos (caso_id, devedor_cnpj)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS autos_ia_creditos")
    op.execute("DROP TABLE IF EXISTS autos_ia_credito_lotes")
    op.execute("DROP TABLE IF EXISTS autos_ia_participacoes")
    op.execute("DROP TABLE IF EXISTS autos_ia_entidades")
