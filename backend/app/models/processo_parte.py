"""Partes do processo coletadas via PDPJ (polo ativo / passivo / outros).

Vinculadas a processos do escritório OU a processos_telegram_extras (CNJs
avulsos adicionados via /add no bot). Exatamente UMA das FKs deve estar
preenchida — garantido por CHECK constraint no banco.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProcessoParte(Base):
    __tablename__ = "processo_partes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id", ondelete="CASCADE"), nullable=True
    )
    extra_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos_telegram_extras.id", ondelete="CASCADE"), nullable=True
    )

    polo: Mapped[str] = mapped_column(String(20), nullable=False)  # ATIVO / PASSIVO / OUTROS
    nome: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_pessoa: Mapped[str | None] = mapped_column(String(20))  # FISICA / JURIDICA
    documento: Mapped[str | None] = mapped_column(String(50))
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    extra: Mapped["ProcessoTelegramExtra | None"] = relationship(  # noqa: F821
        "ProcessoTelegramExtra", back_populates="partes"
    )
