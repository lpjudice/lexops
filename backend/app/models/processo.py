import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── Many-to-many: litisconsórcio ──────────────────────────────────────────────
processo_clientes = Table(
    "processo_clientes",
    Base.metadata,
    Column("processo_id", UUID(as_uuid=True), ForeignKey("processos.id", ondelete="CASCADE"), primary_key=True),
    Column("cliente_id", UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), primary_key=True),
    Column("polo", String(50), nullable=True),
    Column("principal", Boolean, default=False),
)


class Processo(Base):
    __tablename__ = "processos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    numero_cnj: Mapped[str] = mapped_column(String(25), unique=True, nullable=False)
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False
    )

    vara: Mapped[str | None] = mapped_column(String(255))
    comarca: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[str] = mapped_column(
        Enum("ES", "SP", "AM", "RJ", "outro", name="estado_processo"), nullable=False
    )
    tribunal: Mapped[str | None] = mapped_column(String(20))  # TJES, TJSP, TJAM, TJRJ

    materia: Mapped[str | None] = mapped_column(String(255))
    # Texto livre; editável na mão ou sugerido automaticamente após sync do
    # jus.br a partir de ProcessoParte (ver services/processo_partes_store.py).
    parte_contraria: Mapped[str | None] = mapped_column(String(500))
    fase: Mapped[str | None] = mapped_column(
        Enum(
            "conhecimento",
            "recursal",
            "execucao",
            "cumprimento_sentenca",
            "outro",
            name="fase_processo",
        )
    )
    status: Mapped[str] = mapped_column(
        Enum("ativo", "suspenso", "arquivado", "encerrado", name="status_processo"),
        nullable=False,
        default="ativo",
    )
    objeto: Mapped[str | None] = mapped_column(Text)
    polo: Mapped[str | None] = mapped_column(String(50))

    # Expanded form fields
    orgao_julgador_tipo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    serventia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    foro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sistema_juridico: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grau: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grau_texto: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Sync fields
    ultimo_andamento_data: Mapped[date | None] = mapped_column(Date, nullable=True)
    ultimo_andamento_desc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ultimo_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Indicador visual da última sincronização: 'ok' (verde), 'incompleto'
    # (amarelo — faltaram documentos) ou 'erro' (vermelho).
    ultimo_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tentativas_falha: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    andamentos_nao_lidos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Push diário do @jusbr_andamentos_bot — pode silenciar processo a processo.
    notificar_telegram: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="processos")  # noqa: F821
    clientes_litisconsorcio: Mapped[list["Cliente"]] = relationship(  # noqa: F821
        "Cliente",
        secondary=processo_clientes,
    )
    prazos: Mapped[list["Prazo"]] = relationship(  # noqa: F821
        "Prazo", back_populates="processo", cascade="all, delete-orphan"
    )
    andamentos: Mapped[list["AndamentoProcesso"]] = relationship(  # noqa: F821
        "AndamentoProcesso", back_populates="processo",
        cascade="all, delete-orphan", order_by="AndamentoProcesso.data_andamento.desc()"
    )
