import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

DEFAULT_ASSESSORIA_EMAILS = "moni@pimentajudice.com.br"


class InstagramSugestao(Base):
    """Uma sugestão de post de Instagram gerada pelo Agente master.

    O Agente varre os sinais da semana (publicações, andamentos, peças, teses,
    insights do site) + um banco de temas evergreen e propõe posts no padrão
    visual do @dr.lucasjudice (Pimenta Judice). Cada sugestão carrega os slides
    já estruturados (JSON) para render fiel no preview, além do motivo pelo qual
    o tema foi escolhido. O Lucas valida (aprova/rejeita), define a data e envia
    para a assessoria produzir.
    """

    __tablename__ = "instagram_sugestoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    tema: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # 'carrossel' | 'estatico'
    formato: Mapped[str] = mapped_column(String(20), nullable=False, default="carrossel")
    # Tema de capa do design system: 'A' (dark) | 'B' (white) | 'C' (cream) | 'D' (split)
    tema_capa: Mapped[str] = mapped_column(String(1), nullable=False, default="A")

    # Lista de slides estruturados (ver schema SlideBlock). Renderizados fiel no front.
    slides: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    legenda: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hashtags: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Origem do gancho: 'insight' | 'publicacao' | 'andamento' | 'peca' | 'tese' | 'evergreen'
    fonte_tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="evergreen")
    # Referência livre da fonte (nº de processo, id de publicação, título do insight…)
    fonte_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Por que o Agente master sugeriu este tema
    motivo_ia: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 'sugerido' | 'aprovado' | 'rejeitado' | 'publicado'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sugerido")
    # Data sugerida de publicação (preenchida ao aprovar)
    data_sugerida: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Quando foi aprovado (para filtro por mês de aprovação na Agenda)
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Link da pasta no Drive (preenchido ao salvar os PNGs)
    drive_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quando foi enviado para a assessoria (e-mail)
    enviado_assessoria_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Custo acumulado de IA (geração + ajustes) em USD
    custo_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    # Histórico de pedidos de ajuste: [{"instrucao","quando"}]
    ajustes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    ajustes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # ── Brinde / isca (lead magnet) ────────────────────────────────────────────
    # Palavra-chave que a pessoa comenta para receber o brinde (ex.: "HOLDING")
    brinde_palavra_chave: Mapped[str | None] = mapped_column(String(60), nullable=True)
    brinde_titulo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 'one_pager' | 'slides' | 'html'
    brinde_formato: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # HTML na identidade Pimenta Judice (fonte de verdade; PDF é gerado a partir dele)
    brinde_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Se o Lucas subiu o próprio PDF, link da pasta/arquivo no Drive
    brinde_drive_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Vídeo → copy: link da pasta do vídeo no Drive (a copy gerada vai p/ legenda/hashtags)
    video_drive_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    data_geracao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InstagramConfig(Base):
    """Configuração única do módulo Instagram (linha id=1).

    Hoje guarda os e-mails da assessoria que recebem os posts aprovados.
    """

    __tablename__ = "instagram_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    assessoria_emails: Mapped[str] = mapped_column(
        Text, nullable=False, default=DEFAULT_ASSESSORIA_EMAILS
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
