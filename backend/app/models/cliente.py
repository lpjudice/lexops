import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, String, Text, func
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
    # Contato adicional (WhatsApp), comum a PF e PJ.
    whatsapp: Mapped[str | None] = mapped_column(String(30))
    endereco: Mapped[str | None] = mapped_column(Text)
    observacoes: Mapped[str | None] = mapped_column(Text)

    # ── Endereço estruturado (auto-preenchível por CEP via ViaCEP) ──────────────
    # Mantemos `endereco` (texto único) por compatibilidade; estes são os campos
    # canônicos do autocadastro.
    cep: Mapped[str | None] = mapped_column(String(9))
    logradouro: Mapped[str | None] = mapped_column(String(255))
    numero: Mapped[str | None] = mapped_column(String(20))
    complemento: Mapped[str | None] = mapped_column(String(120))
    bairro: Mapped[str | None] = mapped_column(String(120))
    cidade: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))

    # ── Campos Pessoa Física ────────────────────────────────────────────────────
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    rg: Mapped[str | None] = mapped_column(String(30))
    estado_civil: Mapped[str | None] = mapped_column(String(120))
    profissao: Mapped[str | None] = mapped_column(String(150))
    # Empresas vinculadas ao CPF (texto livre, uma por linha).
    empresas_vinculadas: Mapped[str | None] = mapped_column(Text)

    # ── Campos Pessoa Jurídica ──────────────────────────────────────────────────
    # `nome` guarda a razão social; nome_fantasia é o nome comercial.
    nome_fantasia: Mapped[str | None] = mapped_column(String(255))
    responsavel_nome: Mapped[str | None] = mapped_column(String(255))
    responsavel_cpf: Mapped[str | None] = mapped_column(String(18))
    responsavel_email: Mapped[str | None] = mapped_column(String(255))
    responsavel_telefone: Mapped[str | None] = mapped_column(String(30))

    # Origem do cadastro: 'manual' (padrão) ou 'autocadastro' (formulário público).
    origem_cadastro: Mapped[str | None] = mapped_column(
        String(30), default="manual", server_default="manual"
    )
    incompleto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    projeto_nome: Mapped[str | None] = mapped_column(String(500), nullable=True)
    worktree_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ID estável da pasta-raiz do cliente no Google Drive. Vínculo imune a renome:
    # quando preenchido, os uploads usam este ID em vez de procurar pela string do nome.
    drive_folder_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Código curto único da entidade (base36), replicado no final das pastas/arquivos do Drive.
    codigo: Mapped[str | None] = mapped_column(String(12), nullable=True)
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
