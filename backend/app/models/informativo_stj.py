import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InformativoStjEdicao(Base):
    """Uma edição do Informativo de Jurisprudência do STJ (scraping semanal).

    O STJ publica semanalmente (geralmente segunda-feira), numeração sequencial,
    com edições extraordinárias temáticas eventuais. O RSS do STJ só anuncia a
    edição nova (número/data) sem conteúdo — por isso a ingestão real é scraping
    da página HTML de cada edição em scon.stj.jus.br.
    """

    __tablename__ = "informativo_stj_edicoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    numero: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    data_publicacao: Mapped[date | None] = mapped_column(Date, nullable=True)

    # 'ordinaria' | 'extraordinaria'
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="ordinaria")
    tema_extraordinario: Mapped[str | None] = mapped_column(String(255), nullable=True)

    url_origem: Mapped[str] = mapped_column(Text, nullable=False)

    # Resumo ultra-curto (IA) do que tem de relevante nessa edição — usado na
    # listagem para decidir se vale abrir, sem precisar ler item por item.
    resumo_edicao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 'pendente' | 'ok' | 'erro_parsing'
    status_scraping: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    erro_scraping: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InformativoStjItem(Base):
    """Um verbete (julgado) dentro de uma edição do Informativo STJ.

    `destacado` é calculado na ingestão a partir da InformativoStjConfig vigente
    (área do direito oficial do STJ + keywords livres). `texto_explicativo` é
    sempre salvo bruto (mesmo nos não destacados) para permitir reclassificação
    retroativa sem precisar refazer o scraping.
    """

    __tablename__ = "informativo_stj_itens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    edicao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("informativo_stj_edicoes.id", ondelete="CASCADE"),
        nullable=False,
    )

    orgao_julgador: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    # Rótulo oficial do STJ (ex: "Direito Civil", "Direito Tributário") — sem mapeamento próprio
    ramo_direito: Mapped[str] = mapped_column(String(255), nullable=False, default="Não classificado")

    titulo: Mapped[str] = mapped_column(Text, nullable=False, default="")
    destaque_oficial: Mapped[str] = mapped_column(Text, nullable=False, default="")

    processo_numero: Mapped[str | None] = mapped_column(Text, nullable=True)
    processo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    relator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_julgamento: Mapped[date | None] = mapped_column(Date, nullable=True)

    texto_explicativo: Mapped[str | None] = mapped_column(Text, nullable=True)
    legislacao_citada: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    destacado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    favorito: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    motivo_destaque: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 'nao_aplicavel' | 'pendente' | 'processando' | 'ok' | 'erro'
    status_ia: Mapped[str] = mapped_column(String(20), nullable=False, default="nao_aplicavel")
    resumo_tema_central: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumo_ratio_decidendi: Mapped[str | None] = mapped_column(Text, nullable=True)
    custo_ia_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ia_processado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erro_ia: Mapped[str | None] = mapped_column(Text, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InformativoStjConfig(Base):
    """Config singleton (1 linha) com as áreas/keywords de destaque do usuário."""

    __tablename__ = "informativo_stj_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    areas_selecionadas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    keywords_livres: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
