import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Anotacao(Base):
    __tablename__ = "anotacoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False
    )
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id"), nullable=True
    )
    # Link back to the source meeting (when created via confirmar-acoes)
    reuniao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reunioes.id", ondelete="SET NULL"), nullable=True
    )

    tipo: Mapped[str] = mapped_column(
        Enum("reuniao", "ligacao", "whatsapp", "email", "documento", "anamnese", "reuniao_todo", "outro", name="tipo_anotacao"),
        nullable=False,
        default="outro",
    )
    data_evento: Mapped[date] = mapped_column(Date, nullable=False)
    titulo: Mapped[str | None] = mapped_column(String(255))
    texto: Mapped[str] = mapped_column(Text, nullable=False)

    # Inherits confidentiality from the source meeting; also settable manually
    confidencial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="anotacoes")  # noqa: F821
    processo: Mapped["Processo | None"] = relationship("Processo")  # noqa: F821
    reuniao: Mapped["Reuniao | None"] = relationship("Reuniao", foreign_keys=[reuniao_id])  # noqa: F821
