import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Reuniao(Base):
    __tablename__ = "reunioes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True)
    processo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("processos.id", ondelete="SET NULL"), nullable=True)

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    data_reuniao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duracao_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    google_meet_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Drive file references
    drive_transcricao_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    drive_notas_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    drive_tldr_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    transcricao_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumo_ia: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON list of suggested actions (tipo, aprovada, campos específicos por tipo)
    acoes_sugeridas: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)

    # pendente | em_revisao | processada
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pendente")
    # drive_auto | manual
    fonte: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cliente: Mapped["Cliente"] = relationship("Cliente", foreign_keys=[cliente_id])  # noqa: F821
    processo: Mapped["Processo"] = relationship("Processo", foreign_keys=[processo_id])  # noqa: F821
