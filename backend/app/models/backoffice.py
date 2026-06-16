"""Modelos do Backoffice Fiscal — lançamentos mensais e motor comparativo."""
from __future__ import annotations
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FiscalMes(Base):
    """Competência com premissas tributárias opcionais (override do ConfigFiscal)."""
    __tablename__ = "fiscal_mes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mes: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)  # YYYY-MM

    # Override de premissas — null = usa ConfigFiscal
    ibs_full_pct: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    cbs_full_pct: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    reducao_setorial_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    credito_modo: Mapped[str] = mapped_column(String(10), default="integral")  # integral|parcial

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    receitas: Mapped[list[FiscalReceita]] = relationship(back_populates="fiscal_mes_rel", cascade="all, delete-orphan")
    despesas: Mapped[list[FiscalDespesa]] = relationship(back_populates="fiscal_mes_rel", cascade="all, delete-orphan")
    folha: Mapped[FiscalFolha | None] = relationship(back_populates="fiscal_mes_rel", uselist=False, cascade="all, delete-orphan")


class FiscalFolha(Base):
    """Folha de pagamento do mês (encargos e salários)."""
    __tablename__ = "fiscal_folha"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mes: Mapped[str] = mapped_column(String(7), ForeignKey("fiscal_mes.mes", ondelete="CASCADE"), nullable=False, unique=True)

    salarios: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    prolabore: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    inss_patronal: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    rat: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    fgts: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    beneficios: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    outros: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    fiscal_mes_rel: Mapped[FiscalMes] = relationship(back_populates="folha")


class RegraCredito(Base):
    """Catálogo de regras de crédito IBS/CBS por categoria de despesa.
    Separado dos meses — regra validada é reutilizada em lançamentos futuros.
    """
    __tablename__ = "regra_credito"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categoria: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_legal: Mapped[str] = mapped_column(String(200), default="LC 214/2025")
    fundamento_complementar: Mapped[str | None] = mapped_column(Text, nullable=True)

    # validado | pendente | revalidar | excecao
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    elegivel: Mapped[bool] = mapped_column(Boolean, default=False)

    last_check: Mapped[str | None] = mapped_column(String(7), nullable=True)   # YYYY-MM
    next_check: Mapped[str | None] = mapped_column(String(7), nullable=True)   # YYYY-MM (revalidação semestral)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FiscalDespesa(Base):
    """Despesa mensal com potencial de crédito IBS/CBS."""
    __tablename__ = "fiscal_despesa"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mes: Mapped[str] = mapped_column(String(7), ForeignKey("fiscal_mes.mes", ondelete="CASCADE"), nullable=False)

    categoria: Mapped[str] = mapped_column(String(100), nullable=False)
    fornecedor: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)

    tem_nota: Mapped[bool] = mapped_column(Boolean, default=True)
    elegivel: Mapped[bool] = mapped_column(Boolean, default=False)
    base_legal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # validado | pendente | revalidar | novo
    status: Mapped[str] = mapped_column(String(20), default="novo")
    last_check: Mapped[str | None] = mapped_column(String(7), nullable=True)

    regra_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("regra_credito.id"), nullable=True)
    criado_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    drive_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Vínculo informativo N:N: IDs de reembolsos que este pagamento cobre (ex.: 1 PIX ao ONR
    # cobre certidões de vários clientes). Apenas rastreio — não soma valores.
    reembolso_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Adiantamento: porção do valor tratada como PERDA (não reembolsada) → elegível a IBS/CBS.
    # saldo = valor − Σ alocações; a perda atua sobre o saldo remanescente.
    perda_valor: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    fiscal_mes_rel: Mapped[FiscalMes] = relationship(back_populates="despesas")
    regra: Mapped[RegraCredito | None] = relationship()


class FiscalReceita(Base):
    """Receita do mês — pode vir de NF emitida ou ser lançada manualmente."""
    __tablename__ = "fiscal_receita"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mes: Mapped[str] = mapped_column(String(7), ForeignKey("fiscal_mes.mes", ondelete="CASCADE"), nullable=False)

    nota_fiscal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notas_fiscais.id"), nullable=True, unique=True
    )

    cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # pj_regular | pj_simples | pf
    tipo_cliente: Mapped[str] = mapped_column(String(20), default="pj_regular")
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    retencoes: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    credito_interesse: Mapped[bool] = mapped_column(Boolean, default=False)
    # por_fora | embutido — afeta percepção do cliente, não o total do escritório
    modo_tributacao: Mapped[str] = mapped_column(String(10), default="embutido")
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    fiscal_mes_rel: Mapped[FiscalMes] = relationship(back_populates="receitas")


class AdiantamentoAlocacao(Base):
    """Alocação de parte de um adiantamento (FiscalDespesa reembolsável) a um item de
    reembolso de um cliente. O saldo do adiantamento = valor − Σ alocações."""
    __tablename__ = "adiantamento_alocacao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    despesa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fiscal_despesa.id", ondelete="CASCADE"), nullable=False
    )
    reembolso_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_reembolso_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotaFiscalSugestao(Base):
    """Entrada do extrato bancário sugerida para emissão de NF (fila de trabalho).
    O usuário emite (vira NotaFiscal) ou ignora (ex.: cliente devolvendo reembolso)."""
    __tablename__ = "nf_sugestoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    competencia: Mapped[str | None] = mapped_column(String(7), nullable=True)  # YYYY-MM
    pagador: Mapped[str] = mapped_column(String(200), nullable=False)
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # receita | reembolso_recebido | outro
    tipo_sugerido: Mapped[str] = mapped_column(String(30), default="receita")
    # pendente | emitida | ignorada
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    nota_fiscal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FiscalFornecedor(Base):
    """Fornecedores conhecidos — base para combobox no lançamento de despesas."""
    __tablename__ = "fiscal_fornecedor"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    cnpj: Mapped[str | None] = mapped_column(String(18), nullable=True)
    categoria_padrao: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DespesaRecorrente(Base):
    """Template de despesa recorrente — selecionável por checkbox a cada mês."""
    __tablename__ = "despesa_recorrente"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categoria: Mapped[str] = mapped_column(String(100), nullable=False)
    fornecedor: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_padrao: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    tem_nota: Mapped[bool] = mapped_column(Boolean, default=True)
    elegivel: Mapped[bool] = mapped_column(Boolean, default=False)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
