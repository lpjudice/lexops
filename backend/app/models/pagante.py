import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Pagante(Base):
    """Pessoa/empresa contra quem se emite NF (tomador), cadastrável.

    Pode existir antes de qualquer NF (cadastro manual) ou ser criado/atualizado
    automaticamente (upsert por cpf_cnpj) quando uma NF é emitida.

    Pode estar vinculado a um Cliente (cliente_id) — ex.: o processo é da Mangrove
    mas quem paga é Ana Maria. Nesse caso, Ana Maria é um pagante NÃO-cliente, e o
    vínculo aponta para o cliente beneficiário.
    """
    __tablename__ = "pagantes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    # cpf_cnpj é a chave natural — só dígitos. unique para permitir upsert.
    cpf_cnpj: Mapped[str | None] = mapped_column(String(14), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Endereço (mesmos campos da NF, para prefill na emissão)
    logradouro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(10), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(60), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cidade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estado: Mapped[str | None] = mapped_column(String(2), nullable=True)  # UF
    cod_municipio: Mapped[str | None] = mapped_column(String(7), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Vínculo opcional a um cliente cadastrado (beneficiário ou o próprio cliente)
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # origem: "manual" (cadastrado na aba) | "nf" (auto ao emitir NF)
    origem: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", server_default="manual")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
