import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

    # ── Cobrança automática (lembretes ao cliente até o pagamento) ──────────────
    # Opt-in por recebível. Quando ativa, o cron diário envia e-mail + PDF de
    # cobrança para as parcelas pendentes vencidas, até serem marcadas como pagas.
    cobranca_ativa: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # E-mail para onde enviar a cobrança (legado, um único endereço — mantido por
    # compatibilidade). Superado por cobranca_emails; se ambos vazios, usa cliente.email.
    cobranca_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Lista de e-mails de destino da cobrança (registrados do cliente selecionados
    # + endereços extras digitados). Vazio = usa cliente.email.
    cobranca_emails: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    # Estágio do lembrete já enviado quando o recebível NÃO tem parcelas (pagamento
    # à vista, usa data_vencimento do próprio honorário). Mesma escala de Parcela.cobranca_estagio.
    cobranca_estagio: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)

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
    parcelas: Mapped[list["Parcela"]] = relationship(
        "Parcela", back_populates="honorario",
        cascade="all, delete-orphan",
        order_by="Parcela.numero",
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
    # Parcela que este pagamento quita (opcional). Pagar uma parcela cria um
    # Recebimento com este vínculo — e a NF continua se ligando ao recebimento.
    parcela_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parcelas.id"), nullable=True
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

    # Comprovante de pagamento (upload). Sobe para a pasta do cliente e para a
    # pasta mestra /Financeiro/Comprovantes no Drive (best-effort).
    comprovante_filename: Mapped[str | None] = mapped_column(String(500))
    comprovante_path: Mapped[str | None] = mapped_column(String(1000))
    comprovante_drive_link: Mapped[str | None] = mapped_column(String(1000))

    honorario: Mapped["Honorario"] = relationship("Honorario", back_populates="recebimentos")


class Parcela(Base):
    """Parcela agendada (a vencer) de um recebível (Honorário). O pagamento de uma
    parcela gera um Recebimento vinculado; a NF continua sendo emitida por recebimento."""
    __tablename__ = "parcelas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    honorario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("honorarios.id"), nullable=False
    )

    numero: Mapped[int] = mapped_column(nullable=False, default=1)
    valor: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("pendente", "pago", "cancelado", name="status_parcela"),
        nullable=False, default="pendente",
    )
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacao: Mapped[str | None] = mapped_column(String(500))
    # Controle de cobrança: última vez que o lembrete desta parcela saiu.
    ultimo_lembrete_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Estágio de lembrete já enviado: 0=nenhum, 1=D-15, 2=D-7, 3=D-2, 4=pós-vencimento (D+5).
    cobranca_estagio: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    honorario: Mapped["Honorario"] = relationship("Honorario", back_populates="parcelas")
