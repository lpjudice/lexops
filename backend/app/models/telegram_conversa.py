"""Estado da conversa do bot de Reembolsos no Telegram.

Uma linha por chat (grupo ou DM). Guarda o passo atual da máquina de
estados (`state`) e o rascunho da despesa em andamento (`data`, JSONB).
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TelegramConversa(Base):
    __tablename__ = "telegram_conversas"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="idle")
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TelegramDoc(Base):
    """Todo comprovante recebido pelo bot, para reconciliação (/pendentes).

    status: 'pendente' (recebido, ainda não virou despesa) | 'catalogado' | 'descartado'.
    """
    __tablename__ = "telegram_docs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_id: Mapped[str] = mapped_column(String(400), nullable=False)
    file_unique_id: Mapped[str | None] = mapped_column(String(200))
    filename: Mapped[str | None] = mapped_column(String(500))
    mime: Mapped[str | None] = mapped_column(String(100))
    valor_detectado: Mapped[float | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
