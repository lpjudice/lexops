import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Reembolso(Base):
    __tablename__ = "reembolsos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False
    )
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id"), nullable=True
    )

    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    data_emissao: Mapped[date] = mapped_column(Date, nullable=False)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum("rascunho", "aguardando_pagamento", "enviado", "pago", "cancelado",
             name="status_reembolso", create_type=False),
        nullable=False,
        default="rascunho",
    )

    # Decisão EXPLÍCITA de perda: o adiantamento não será cobrado do cliente e vira
    # despesa/perda real do escritório (com crédito IBS/CBS se elegível). Marcado a partir
    # do rascunho. NÃO confundir com status="cancelado" (que é erro de cadastro refeito).
    tratar_como_perda: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Caminho do PDF gerado (armazenado localmente)
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    # Link do PDF no Google Drive (após upload)
    drive_link: Mapped[str | None] = mapped_column(String(1000))
    # E-mail usado para envio e controle de lembretes automáticos.
    email_destinatario: Mapped[str | None] = mapped_column(String(255))
    ultimo_lembrete_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente")  # noqa: F821
    processo: Mapped["Processo | None"] = relationship("Processo")  # noqa: F821
    itens: Mapped[list["ItemReembolso"]] = relationship(
        "ItemReembolso", back_populates="reembolso", cascade="all, delete-orphan",
        order_by="ItemReembolso.data"
    )

    @property
    def total(self) -> float:
        return sum(float(i.valor) for i in self.itens)


class ItemReembolso(Base):
    __tablename__ = "itens_reembolso"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reembolso_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reembolsos.id"), nullable=False
    )

    data: Mapped[date] = mapped_column(Date, nullable=False)
    descricao: Mapped[str] = mapped_column(String(500), nullable=False)
    natureza: Mapped[str] = mapped_column(String(100), nullable=False)
    documento_comprobatorio: Mapped[str | None] = mapped_column(String(500))
    comprovante_path: Mapped[str | None] = mapped_column(String(1000))
    valor: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    reembolso: Mapped["Reembolso"] = relationship("Reembolso", back_populates="itens")

    @property
    def comprovante_drive_link(self) -> str | None:
        """Primeiro drive_link dos ComprovantesItem (ou None). Exposto no schema Out."""
        for c in self.comprovantes:
            if c.drive_link:
                return c.drive_link
        return None

    # Docs adicionais da despesa (ex.: um pagamento que cobre vários comprovantes).
    # O campo comprovante_path acima continua apontando para o doc principal (compat
    # com a geração de PDF e a UI atuais); aqui ficam todos os anexos.
    comprovantes: Mapped[list["ComprovanteItem"]] = relationship(
        "ComprovanteItem", back_populates="item", cascade="all, delete-orphan",
        order_by="ComprovanteItem.created_at"
    )


class ComprovanteItem(Base):
    __tablename__ = "comprovantes_item"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("itens_reembolso.id"), nullable=False
    )
    filename: Mapped[str | None] = mapped_column(String(500))
    file_path: Mapped[str | None] = mapped_column(String(1000))
    drive_link: Mapped[str | None] = mapped_column(String(1000))
    mime: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    item: Mapped["ItemReembolso"] = relationship("ItemReembolso", back_populates="comprovantes")
