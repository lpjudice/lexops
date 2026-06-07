import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotaFiscal(Base):
    __tablename__ = "notas_fiscais"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Identificação no sistema nacional ────────────────────────────────
    numero_nfse: Mapped[str | None] = mapped_column(String(50), nullable=True)
    chave_acesso: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    serie: Mapped[str] = mapped_column(String(10), nullable=False, default="1")
    numero_dps: Mapped[int | None] = mapped_column(Integer, nullable=True)  # seq interno

    # ── Competência e datas ───────────────────────────────────────────────
    competencia: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    data_emissao: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ── Prestador (sempre Pimenta Judice) ────────────────────────────────
    prestador_cnpj: Mapped[str] = mapped_column(
        String(14), nullable=False, default="10901611000164"
    )

    # ── Tomador ───────────────────────────────────────────────────────────
    tomador_cpf_cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    tomador_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    tomador_email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tomador_telefone: Mapped[str | None] = mapped_column(String(11), nullable=True)
    # Endereço em texto livre (não obrigatório para tomador PJ grande)
    tomador_logradouro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tomador_numero: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tomador_complemento: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tomador_bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tomador_cod_municipio: Mapped[str | None] = mapped_column(String(7), nullable=True)
    tomador_cep: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # ── Serviço ───────────────────────────────────────────────────────────
    cod_tributacao_nacional: Mapped[str] = mapped_column(String(20), nullable=False)
    descricao_servico: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Valores ───────────────────────────────────────────────────────────
    valor_servicos: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    # Retenções (nullable = não há retenção)
    retencao_ir: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    retencao_inss: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    retencao_csll: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    retencao_cofins: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    retencao_pis: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # IBS/CBS — reforma tributária (agosto 2026)
    ibs_valor: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    cbs_valor: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    # ── Tributação extra ─────────────────────────────────────────────────
    natureza_operacao: Mapped[str] = mapped_column(String(2), nullable=False, server_default="1")
    regime_tributario: Mapped[str] = mapped_column(String(2), nullable=False, server_default="1")
    iss_retido: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    contrato_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    processo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    processos_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    pdf_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    drive_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ambiente: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")  # 1=Prod 2=Teste
    retroativa: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    # ── Status ────────────────────────────────────────────────────────────
    # rascunho | emitida | cancelada | erro
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="rascunho")
    erro_mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── XML armazenado ────────────────────────────────────────────────────
    xml_nfse: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Vínculo com Financeiro ────────────────────────────────────────────
    honorario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("honorarios.id"), nullable=True
    )
    recebimento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recebimentos.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    honorario: Mapped["Honorario | None"] = relationship("Honorario")  # noqa: F821
    recebimento: Mapped["Recebimento | None"] = relationship("Recebimento")  # noqa: F821

    @property
    def valor_liquido(self) -> float:
        retencoes = sum(
            float(v) for v in [
                self.retencao_ir, self.retencao_inss, self.retencao_csll,
                self.retencao_cofins, self.retencao_pis,
            ] if v is not None
        )
        return float(self.valor_servicos) - retencoes
