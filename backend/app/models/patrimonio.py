import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PatrimonioBem(Base):
    """Um bem (móvel ou imóvel) no inventário patrimonial de um cliente.

    Pensado para diagnóstico de holding: registra valores (compra/mercado/IR),
    situação registral (matrícula, cartório, gravames), proprietário real x
    proprietário na matrícula, e a decisão de integralizar ou não na holding.
    """

    __tablename__ = "patrimonio_bens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )

    # 'movel' | 'imovel'
    tipo_bem: Mapped[str] = mapped_column(String(20), nullable=False, default="imovel")
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)

    valor_compra: Mapped[float | None] = mapped_column(Numeric(15, 2))
    valor_mercado: Mapped[float | None] = mapped_column(Numeric(15, 2))
    valor_ir: Mapped[float | None] = mapped_column(Numeric(15, 2))
    data_compra: Mapped[date | None] = mapped_column(Date)

    # 'venda' | 'aluguel' | 'segurar'
    objetivo: Mapped[str | None] = mapped_column(String(20))

    # Situação registral (relevante para imóveis)
    descricao_matricula: Mapped[str | None] = mapped_column(Text)
    numero_matricula: Mapped[str | None] = mapped_column(String(100))
    cartorio: Mapped[str | None] = mapped_column(String(255))

    # 'em_validacao' | 'validado' | 'incerto'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="em_validacao"
    )
    integralizar_holding: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    proprietario_real: Mapped[str | None] = mapped_column(String(255))
    proprietario_matricula: Mapped[str | None] = mapped_column(String(255))

    tem_gravame: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    gravame_descricao: Mapped[str | None] = mapped_column(Text)

    observacoes: Mapped[str | None] = mapped_column(Text)

    # ── Bem móvel do tipo cota social / participação societária (opcional) ──
    empresa_nome: Mapped[str | None] = mapped_column(String(255))
    empresa_cnpj: Mapped[str | None] = mapped_column(String(18))
    capital_social: Mapped[float | None] = mapped_column(Numeric(15, 2))
    valor_balanco: Mapped[float | None] = mapped_column(Numeric(15, 2))
    data_balanco: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente")  # noqa: F821
    anexos: Mapped[list["PatrimonioAnexo"]] = relationship(
        "PatrimonioAnexo",
        back_populates="bem",
        cascade="all, delete-orphan",
        order_by="PatrimonioAnexo.created_at",
    )
    cadeia: Mapped[list["PatrimonioCadeiaElo"]] = relationship(
        "PatrimonioCadeiaElo",
        back_populates="bem",
        cascade="all, delete-orphan",
        order_by="PatrimonioCadeiaElo.ordem",
    )
    socios: Mapped[list["PatrimonioSocio"]] = relationship(
        "PatrimonioSocio",
        back_populates="bem",
        cascade="all, delete-orphan",
        order_by="PatrimonioSocio.ordem",
    )


class PatrimonioAnexo(Base):
    """Arquivo anexado a um bem (matrícula, escritura, laudo...), salvo no Drive."""

    __tablename__ = "patrimonio_anexos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patrimonio_bens.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    drive_link: Mapped[str | None] = mapped_column(String(1000))
    mime: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bem: Mapped["PatrimonioBem"] = relationship("PatrimonioBem", back_populates="anexos")


class PatrimonioCadeiaElo(Base):
    """Um elo da cadeia sucessória/dominial de um bem.

    Usado quando a matrícula ainda não está no nome do cliente: registra a
    sequência de transmissões (contrato de compra e venda → escritura pública →
    cessão de direitos...), com anexo opcional do documento de cada elo.
    """

    __tablename__ = "patrimonio_cadeia_elos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patrimonio_bens.id", ondelete="CASCADE"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 'contrato_compra_venda' | 'escritura_publica' | 'cessao_direitos' |
    # 'matricula' | 'formal_partilha' | 'outro'
    tipo_documento: Mapped[str] = mapped_column(String(50), nullable=False, default="outro")
    de_quem: Mapped[str | None] = mapped_column(String(255))
    para_quem: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[date | None] = mapped_column(Date)
    descricao: Mapped[str | None] = mapped_column(Text)

    # Anexo opcional do documento deste elo (no Drive)
    arquivo_nome: Mapped[str | None] = mapped_column(String(500))
    drive_link: Mapped[str | None] = mapped_column(String(1000))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bem: Mapped["PatrimonioBem"] = relationship("PatrimonioBem", back_populates="cadeia")


class PatrimonioSocio(Base):
    """Sócio do quadro societário de um bem móvel do tipo cota social.

    Registra o sócio (nome/CPF), o percentual de participação e se aquela
    participação será ou não integralizada na holding.
    """

    __tablename__ = "patrimonio_socios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patrimonio_bens.id", ondelete="CASCADE"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    cpf: Mapped[str | None] = mapped_column(String(18))
    percentual: Mapped[float | None] = mapped_column(Numeric(6, 3))
    integralizar: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bem: Mapped["PatrimonioBem"] = relationship("PatrimonioBem", back_populates="socios")
