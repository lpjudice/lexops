import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConfigFiscal(Base):
    """Configuração fiscal do escritório — linha única (singleton id=1)."""
    __tablename__ = "config_fiscal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # ── A. Emitente ───────────────────────────────────────────────────────
    razao_social: Mapped[str] = mapped_column(String(200), default="PIMENTA JUDICE SOCIEDADE INDIVIDUAL DE ADVOCACIA")
    cnpj: Mapped[str] = mapped_column(String(14), default="10901611000164")
    inscricao_municipal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cnae: Mapped[str | None] = mapped_column(String(20), nullable=True, default="6911-7/01")
    endereco: Mapped[str | None] = mapped_column(Text, nullable=True)
    municipio_ibge: Mapped[str] = mapped_column(String(7), default="3205309")
    municipio_nome: Mapped[str] = mapped_column(String(100), default="Vitória")
    uf: Mapped[str] = mapped_column(String(2), default="ES")
    email_fiscal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefone_fiscal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    regime_tributario: Mapped[str] = mapped_column(String(30), default="simples")  # simples|presumido|real

    # ── B. Bases de tributação ────────────────────────────────────────────
    aliquota_iss: Mapped[float] = mapped_column(Numeric(5, 2), default=2.00)
    regime_especial: Mapped[str] = mapped_column(String(2), default="0")  # 0=Nenhum 6=Soc.Prof
    anexo_simples: Mapped[str] = mapped_column(String(5), default="IV")
    rbt12: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)  # receita bruta 12m
    aliquota_efetiva_simples: Mapped[float] = mapped_column(Numeric(5, 2), default=6.00)  # pTotTribSN

    # Retenções padrão (quando tomador PJ) — percentuais
    ret_ir_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    ret_inss_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    ret_csll_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    ret_pis_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    ret_cofins_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    iss_retido_padrao: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── D. Reforma tributária IBS/CBS ─────────────────────────────────────
    ibs_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    cbs_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    piloto_ibscbs: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── E. Contabilidade / relatórios ─────────────────────────────────────
    emails_contador: Mapped[list] = mapped_column(JSONB, default=list)
    email_master: Mapped[str | None] = mapped_column(String(255), nullable=True, default="pj@pimentajudice.com.br")
    dia_envio_relatorio: Mapped[int] = mapped_column(Integer, default=1)
    enviar_relatorio_auto: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── F. Numeração ──────────────────────────────────────────────────────
    serie_padrao: Mapped[str] = mapped_column(String(10), default="1")

    # ── G. Catálogos ──────────────────────────────────────────────────────
    codigos_favoritos: Mapped[list] = mapped_column(JSONB, default=list)
    templates_descricao: Mapped[list] = mapped_column(JSONB, default=list)

    # ── H. DANFSe ─────────────────────────────────────────────────────────
    rodape_danfse: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Prefixo do número exibido na DANFSe (cosmético): 17 → "PJ150" + "17" = PJ15017
    danfse_prefixo_numero: Mapped[str] = mapped_column(String(20), default="", server_default="")
    dfe_ultimo_nsu: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Carga tributária média (IBPT / Lei 12.741) — advocacia ~16,33%
    carga_media_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=16.33, server_default="16.33")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
