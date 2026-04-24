import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Honorario(Base):
    __tablename__ = "honorarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False
    )
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id"), nullable=True
    )

    descricao: Mapped[str] = mapped_column(String(500), nullable=False)

    tipo: Mapped[str] = mapped_column(
        Enum("fixo", "percentual", "exito", name="tipo_honorario"),
        nullable=False,
        default="fixo",
    )

    valor_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    status: Mapped[str] = mapped_column(
        Enum("pendente", "parcial", "pago", "cancelado", name="status_honorario"),
        nullable=False,
        default="pendente",
    )

    data_contrato: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text)
    # Campos para honorários de êxito (projeção)
    valor_causa: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    percentual_exito: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    data_estimada_sentenca: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Vinculação ao contrato + status de assinatura
    contrato_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    pendente_assinatura: Mapped[bool] = mapped_column(default=False, server_default="false")
    contrato_orfao: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente")  # noqa: F821
    processo: Mapped["Processo | None"] = relationship("Processo")  # noqa: F821
    recebimentos: Mapped[list["Recebimento"]] = relationship(
        "Recebimento", back_populates="honorario",
        cascade="all, delete-orphan",
        order_by="Recebimento.data_recebimento",
    )

    @property
    def total_recebido(self) -> float:
        return sum(float(r.valor) for r in self.recebimentos)

    @property
    def saldo_pendente(self) -> float:
        return float(self.valor_total) - self.total_recebido


class Recebimento(Base):
    __tablename__ = "recebimentos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    honorario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("honorarios.id"), nullable=False
    )

    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    data_recebimento: Mapped[date] = mapped_column(Date, nullable=False)
    forma_pagamento: Mapped[str] = mapped_column(
        Enum("pix", "ted", "boleto", "cheque", "dinheiro", "outro",
             name="forma_pagamento"),
        nullable=False,
        default="pix",
    )
    observacao: Mapped[str | None] = mapped_column(String(500))

    honorario: Mapped["Honorario"] = relationship("Honorario", back_populates="recebimentos")
