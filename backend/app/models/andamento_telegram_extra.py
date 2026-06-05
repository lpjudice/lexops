"""Andamentos dos CNJs avulsos (ProcessoTelegramExtra).

Espelha o mínimo do AndamentoProcesso usado pelo bot, mas vinculado a
processos_telegram_extras (que não têm linha em `processos`). hash_unico
garante idempotência de coleta — mesmo se sincronizar 10× o mesmo CNJ,
não vira duplicado.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AndamentoTelegramExtra(Base):
    __tablename__ = "andamentos_telegram_extras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extra_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processos_telegram_extras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    data_andamento: Mapped[date | None] = mapped_column(Date)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(255))

    arquivo_nome: Mapped[str | None] = mapped_column(String(500))
    arquivo_url: Mapped[str | None] = mapped_column(Text)  # hrefBinario do PDPJ

    hash_unico: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    notificado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @staticmethod
    def calcular_hash(extra_id: str, data: str | None, descricao: str | None, documento_id: str | None = None) -> str:
        base = "|".join([extra_id, str(data or ""), (descricao or "")[:600], documento_id or ""])
        return hashlib.sha256(base.encode("utf-8")).hexdigest()
