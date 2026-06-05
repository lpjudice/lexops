"""CNJs adicionados via /add no @jusbr_andamentos_bot.

Processos avulsos que NÃO estão na carteira do escritório (pessoais, de família,
etc). Ficam num cadastro próprio para não poluir a lista da firma — entram no
push diário do bot mas não aparecem nas buscas regulares do lexops.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProcessoTelegramExtra(Base):
    __tablename__ = "processos_telegram_extras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cnj: Mapped[str] = mapped_column(String(25), unique=True, nullable=False)

    nome_cliente: Mapped[str | None] = mapped_column(String(255))
    apelido: Mapped[str | None] = mapped_column(String(255))
    descricao: Mapped[str | None] = mapped_column(Text)
    info_adicional: Mapped[str | None] = mapped_column(String(120))

    tribunal: Mapped[str | None] = mapped_column(String(20))
    vara: Mapped[str | None] = mapped_column(String(255))
    comarca: Mapped[str | None] = mapped_column(String(255))

    notificar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    criado_por_chat_id: Mapped[int | None] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    partes: Mapped[list["ProcessoParte"]] = relationship(  # noqa: F821
        "ProcessoParte",
        back_populates="extra",
        cascade="all, delete-orphan",
    )
