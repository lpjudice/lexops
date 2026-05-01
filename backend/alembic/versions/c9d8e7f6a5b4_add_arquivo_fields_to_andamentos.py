"""add_arquivo_fields_to_andamentos

Revision ID: c9d8e7f6a5b4
Revises: b4c5d6e7f8a9
Create Date: 2026-04-30 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    cols = {col["name"] for col in inspector.get_columns("andamentos_processo")}

    if "arquivo_nome" not in cols:
        op.add_column("andamentos_processo", sa.Column("arquivo_nome", sa.String(length=255), nullable=True))
    if "arquivo_path" not in cols:
        op.add_column("andamentos_processo", sa.Column("arquivo_path", sa.String(length=500), nullable=True))
    if "arquivo_drive_link" not in cols:
        op.add_column("andamentos_processo", sa.Column("arquivo_drive_link", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("andamentos_processo", "arquivo_drive_link")
    op.drop_column("andamentos_processo", "arquivo_path")
    op.drop_column("andamentos_processo", "arquivo_nome")
