import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Contrato(Base):
    __tablename__ = "contratos"

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
    descricao: Mapped[str | None] = mapped_column(Text)
    arquivo_path: Mapped[str | None] = mapped_column(String(500))  # path local do PDF original (legado)
    arquivo_assinado_path: Mapped[str | None] = mapped_column(String(500))  # PDF assinado
    # Lista de arquivos: [{"filename": str, "path": str, "clicksign_key": str|null}]
    arquivos: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))

    status: Mapped[str] = mapped_column(
        Enum(
            "rascunho",
            "aguardando_assinatura",
            "parcialmente_assinado",
            "assinado",
            "cancelado",
            name="status_contrato",
        ),
        nullable=False,
        default="rascunho",
    )

    # Assinatura manual (fora do ClickSign)
    assinatura_manual: Mapped[bool] = mapped_column(default=False, server_default="false")

    # Links do Drive do documento final assinado (pasta do cliente + pasta mestra /Contratos)
    drive_link_cliente: Mapped[str | None] = mapped_column(String(1000))
    drive_link_master: Mapped[str | None] = mapped_column(String(1000))

    # ClickSign
    clicksign_document_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    clicksign_request_signature_key: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="contratos")  # noqa: F821
    processo: Mapped["Processo | None"] = relationship("Processo")  # noqa: F821
    signatarios: Mapped[list["Signatario"]] = relationship(
        "Signatario", back_populates="contrato", cascade="all, delete-orphan"
    )


class Signatario(Base):
    __tablename__ = "signatarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contrato_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id"), nullable=False
    )

    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[str] = mapped_column(
        Enum("contratante", "contratado", "testemunha", "outro", name="papel_signatario"),
        nullable=False,
        default="outro",
    )

    # ClickSign
    clicksign_signer_key: Mapped[str | None] = mapped_column(String(255))
    clicksign_request_key: Mapped[str | None] = mapped_column(String(255))
    status_assinatura: Mapped[str] = mapped_column(
        Enum("pendente", "assinado", "recusado", name="status_assinatura"),
        nullable=False,
        default="pendente",
    )
    assinado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contrato: Mapped["Contrato"] = relationship("Contrato", back_populates="signatarios")
