import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmailCliente(Base):
    __tablename__ = "emails_cliente"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Deduplication key — same Gmail message can appear in multiple accounts
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Which account fetched this email: "master" or str(usuario_id)
    conta_google: Mapped[str] = mapped_column(String(36), nullable=False)
    # Human-readable email address of the account
    conta_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    remetente: Mapped[str | None] = mapped_column(String(500), nullable=True)
    destinatarios: Mapped[str | None] = mapped_column(Text, nullable=True)
    assunto: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lido: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Privacidade: por padrão todo email puxado é visível a todos os usuários.
    # Quando privado=True, só quem marcou (privado_por) e super-admins enxergam.
    privado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    privado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cliente: Mapped["Cliente"] = relationship("Cliente")  # noqa: F821
