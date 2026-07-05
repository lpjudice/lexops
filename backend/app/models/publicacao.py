import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Publicacao(Base):
    __tablename__ = "publicacoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Origem
    fonte: Mapped[str] = mapped_column(
        Enum("gmail", "scraping_tjes", "scraping_tjsp", "scraping_tjam", "scraping_tjrj", "scraping_djen", "pje_comunica", "manual", name="fonte_publicacao"),
        nullable=False,
    )
    data_publicacao: Mapped[date] = mapped_column(Date, nullable=False)

    # Conteúdo extraído
    numero_cnj: Mapped[str | None] = mapped_column(String(25))
    tipo_ato: Mapped[str | None] = mapped_column(
        Enum(
            "despacho", "decisao", "sentenca", "acordao",
            "intimacao", "citacao", "outro",
            name="tipo_ato_publicacao",
        )
    )
    tribunal: Mapped[str | None] = mapped_column(String(20))
    vara: Mapped[str | None] = mapped_column(String(255))
    texto_resumo: Mapped[str | None] = mapped_column(Text)
    texto_completo: Mapped[str | None] = mapped_column(Text)

    # Vínculo com processo (opcional — pode ser vinculado manualmente depois)
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id"), nullable=True
    )

    # Controle
    lida: Mapped[bool] = mapped_column(Boolean, default=False)
    rejeitada: Mapped[bool] = mapped_column(Boolean, default=False)
    gera_prazo: Mapped[bool] = mapped_column(Boolean, default=False)
    prazo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prazos.id", ondelete="SET NULL"), nullable=True
    )
    # Confirmação humana do vínculo processo/cliente (tela Despacho) — o match
    # automático (CNJ/OAB/nome) só é tratado como certo depois disso.
    vinculo_confirmado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Sugestão de ação da IA (JSON), gerada após a confirmação do vínculo.
    sugestao_acao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Conteúdo da peça gerada (JSON), antes de virar documento no Google Docs.
    peca_gerada: Mapped[str | None] = mapped_column(Text, nullable=True)

    # IA
    analise_ia: Mapped[str | None] = mapped_column(Text)          # JSON do Claude
    cliente_nome_pub: Mapped[str | None] = mapped_column(String(500))  # extraído da IA

    # Rastreabilidade
    email_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    url_fonte: Mapped[str | None] = mapped_column(Text)  # link para o email ou página do diário
    # ID estável da comunicação no DJEN/Comunica — chave de dedup à prova de duplicata
    comunica_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    # Quando a publicação veio da busca por OAB, guarda qual OAB casou (ex.: "14477/ES").
    # Marca de match forte: garante exibição mesmo sem nome/CNJ no texto.
    match_oab: Mapped[str | None] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    processo: Mapped["Processo | None"] = relationship("Processo")  # noqa: F821
    prazo: Mapped["Prazo | None"] = relationship("Prazo")  # noqa: F821
