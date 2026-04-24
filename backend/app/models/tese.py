import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tese(Base):
    __tablename__ = "teses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=True
    )
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id"), nullable=True
    )

    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    texto_input: Mapped[str] = mapped_column(Text, nullable=False)

    resposta_claude: Mapped[str | None] = mapped_column(Text)
    resposta_gpt: Mapped[str | None] = mapped_column(Text)
    resposta_gemini: Mapped[str | None] = mapped_column(Text)

    modelo_ativo: Mapped[str] = mapped_column(
        Enum("claude", "gpt", "gemini", name="modelo_ia"),
        nullable=False,
        default="claude",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente")  # noqa: F821
    processo: Mapped["Processo | None"] = relationship("Processo")  # noqa: F821
