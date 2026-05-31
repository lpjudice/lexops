import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(
        Enum("PF", "PJ", name="tipo_cliente"), nullable=False
    )
    cpf_cnpj: Mapped[str | None] = mapped_column(String(18), unique=True)
    email: Mapped[str | None] = mapped_column(String(255))
    telefone: Mapped[str | None] = mapped_column(String(30))
    endereco: Mapped[str | None] = mapped_column(Text)
    observacoes: Mapped[str | None] = mapped_column(Text)
    incompleto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    projeto_nome: Mapped[str | None] = mapped_column(String(500), nullable=True)
    worktree_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ID estável da pasta-raiz do cliente no Google Drive. Vínculo imune a renome:
    # quando preenchido, os uploads usam este ID em vez de procurar pela string do nome.
    drive_folder_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Quando True, o nome deste cliente entra na busca automática do Diário Oficial.
    # Seletivo de propósito — evita ruído de homônimo ao buscar todos os clientes por nome.
    monitorar_diario: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    processos: Mapped[list["Processo"]] = relationship(  # noqa: F821
        "Processo", back_populates="cliente", cascade="all, delete-orphan"
    )
    anotacoes: Mapped[list["Anotacao"]] = relationship(  # noqa: F821
        "Anotacao", back_populates="cliente", cascade="all, delete-orphan"
    )
    contratos: Mapped[list["Contrato"]] = relationship(  # noqa: F821
        "Contrato", back_populates="cliente", cascade="all, delete-orphan"
    )
