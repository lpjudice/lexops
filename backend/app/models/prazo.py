import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Prazo(Base):
    __tablename__ = "prazos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    processo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id"), nullable=False
    )

    tipo: Mapped[str] = mapped_column(
        Enum(
            "contestacao",
            "recurso",
            "contrarrazoes",
            "manifestacao",
            "audiencia",
            "pericia",
            "outro",
            name="tipo_prazo",
        ),
        nullable=False,
    )
    descricao: Mapped[str | None] = mapped_column(Text)

    # Origem do prazo
    data_publicacao: Mapped[date] = mapped_column(Date, nullable=False)
    dias_prazo: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo_contagem: Mapped[str] = mapped_column(
        Enum("uteis", "corridos", name="tipo_contagem_prazo"),
        nullable=False,
        default="uteis",
    )

    # Resultados do cálculo
    data_limite: Mapped[date | None] = mapped_column(Date)           # com feriados
    data_limite_sem_feriado: Mapped[date | None] = mapped_column(Date)  # sem feriados

    status: Mapped[str] = mapped_column(
        Enum("pendente", "cumprido", "perdido", name="status_prazo"),
        nullable=False,
        default="pendente",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    processo: Mapped["Processo"] = relationship("Processo", back_populates="prazos")  # noqa: F821
    peca_necessaria: Mapped[str | None] = mapped_column(String(100))
    responsavel: Mapped[str | None] = mapped_column(String(100))
    google_event_id: Mapped[str | None] = mapped_column(String(255))
    # Criado automaticamente pelo gestor jurídico (Despacho), sem clique humano.
    criado_automaticamente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
