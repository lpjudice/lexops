import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MemoriaEstrategica(Base):
    """Histórico append-only da estratégia de um cliente e/ou processo.

    Cada edição cria uma nova linha; a versão atual é a mais recente por
    (cliente_id, processo_id) ordenada por created_at.
    """

    __tablename__ = "memorias_estrategicas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True
    )
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id", ondelete="CASCADE"), nullable=True
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    autor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
