import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PedidoVoz(Base):
    """Pedido de alteração feito por ligação de voz (Bland.ai), pendente de
    aprovação pelo Telegram antes de ser implementado."""
    __tablename__ = "pedidos_voz"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    telefone: Mapped[str] = mapped_column(String(30), nullable=False)
    # em_chamada -> aguardando_aprovacao -> aprovado | rejeitado
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="em_chamada")
    transcricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumo_pedido: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
