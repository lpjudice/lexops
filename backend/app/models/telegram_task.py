import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TelegramTaskBatch(Base):
    """Um lote de tarefas enviado de uma só vez pelo Telegram."""
    __tablename__ = "telegram_task_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ativo")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TelegramTaskItem(Base):
    """Uma tarefa individual dentro de um lote, com metadados de inferência."""
    __tablename__ = "telegram_task_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("telegram_task_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    tarefa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo_original: Mapped[str] = mapped_column(String(500), nullable=False)
    titulo_normalizado: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    cliente_inferido_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True)
    cliente_inferido_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cliente_inferencia_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicada_de_tarefa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="SET NULL"), nullable=True)
    duplicada_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramChatSession(Base):
    """Estado da conversa de um chat_id com o bot de Tarefas."""
    __tablename__ = "telegram_task_sessions"

    chat_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    current_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("telegram_task_batches.id", ondelete="SET NULL"), nullable=True)
    pending_action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
