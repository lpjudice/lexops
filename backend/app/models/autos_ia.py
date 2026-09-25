"""Autos IA — leitura incremental de autos processuais volumosos.

Módulo paralelo ao restante do gestor: cada Caso é um processo judicial
independente, alimentado por uploads sucessivos de blocos de páginas do PDF
dos autos. Cada bloco é segmentado em peças (petições, decisões, despachos,
certidões etc.), e cada peça recebe resumo, palavras-chave e a lista de IDs
processuais que menciona, permitindo busca por tema/data, timeline e o grafo
de referências entre peças.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AutosIACaso(Base):
    __tablename__ = "autos_ia_casos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    numero_processo: Mapped[str | None] = mapped_column(String(50))
    descricao: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ativo")  # ativo | arquivado

    # Total de páginas já ingeridas (soma dos blocos) — usado para calcular
    # automaticamente o início do próximo bloco quando o usuário não informa.
    total_paginas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Cauda de uma peça que ficou incompleta no fim do último bloco processado
    # (cortada no meio pela fronteira do upload). Reaproveitada como contexto
    # na segmentação do próximo bloco, para não duplicar nem perder a peça.
    buffer_incompleto: Mapped[str | None] = mapped_column(Text)
    buffer_pagina_inicio: Mapped[int | None] = mapped_column(Integer)

    criado_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuarios.id"))

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documentos: Mapped[list["AutosIADocumento"]] = relationship(
        back_populates="caso", cascade="all, delete-orphan", order_by="AutosIADocumento.pagina_inicio"
    )
    pecas: Mapped[list["AutosIAPeca"]] = relationship(
        back_populates="caso", cascade="all, delete-orphan", order_by="AutosIAPeca.pagina_inicio"
    )
    perguntas_faq: Mapped[list["AutosIAPerguntaFaq"]] = relationship(
        back_populates="caso", cascade="all, delete-orphan", order_by="AutosIAPerguntaFaq.criado_em"
    )

    @property
    def tem_peca_pendente_continuacao(self) -> bool:
        return self.buffer_incompleto is not None


class AutosIADocumento(Base):
    """Um bloco de páginas do PDF dos autos, enviado em um upload."""

    __tablename__ = "autos_ia_documentos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("autos_ia_casos.id"), nullable=False)

    nome_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(String(1000), nullable=False)

    pagina_inicio: Mapped[int] = mapped_column(Integer, nullable=False)
    pagina_fim: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    # pendente | processando | concluido | erro
    erro_mensagem: Mapped[str | None] = mapped_column(Text)
    pecas_geradas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paginas_ocr: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    caso: Mapped["AutosIACaso"] = relationship(back_populates="documentos")


class AutosIAPeca(Base):
    """Uma peça processual individual (petição, decisão, despacho, certidão...)."""

    __tablename__ = "autos_ia_pecas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("autos_ia_casos.id"), nullable=False)
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("autos_ia_documentos.id")
    )

    tipo: Mapped[str] = mapped_column(String(50), nullable=False, default="outro")
    # peticao | decisao | despacho | certidao | oficio | recurso | documento | outro
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    autor: Mapped[str | None] = mapped_column(String(255))
    data_peca: Mapped[date | None] = mapped_column(Date)
    id_processual: Mapped[str | None] = mapped_column(String(100), index=True)

    pagina_inicio: Mapped[int] = mapped_column(Integer, nullable=False)
    pagina_fim: Mapped[int] = mapped_column(Integer, nullable=False)

    texto_md: Mapped[str] = mapped_column(Text, nullable=False)
    resumo: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    ids_mencionados: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente_resumo")
    # pendente_resumo | resumida | erro
    erro_mensagem: Mapped[str | None] = mapped_column(Text)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    caso: Mapped["AutosIACaso"] = relationship(back_populates="pecas")
    referencias_saida: Mapped[list["AutosIAReferencia"]] = relationship(
        back_populates="peca_origem",
        foreign_keys="AutosIAReferencia.peca_origem_id",
        cascade="all, delete-orphan",
    )


class AutosIAReferencia(Base):
    """Menção a um ID processual dentro do texto de uma peça (aresta do grafo)."""

    __tablename__ = "autos_ia_referencias"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("autos_ia_casos.id"), nullable=False)
    peca_origem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("autos_ia_pecas.id"), nullable=False
    )
    peca_destino_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("autos_ia_pecas.id")
    )

    id_mencionado: Mapped[str] = mapped_column(String(100), nullable=False)
    contexto: Mapped[str | None] = mapped_column(Text)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    peca_origem: Mapped["AutosIAPeca"] = relationship(
        back_populates="referencias_saida", foreign_keys=[peca_origem_id]
    )
    peca_destino: Mapped["AutosIAPeca | None"] = relationship(foreign_keys=[peca_destino_id])


class AutosIAPerguntaFaq(Base):
    """Pergunta pré-mapeada com resposta gerada a partir das peças indexadas."""

    __tablename__ = "autos_ia_faq"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("autos_ia_casos.id"), nullable=False)

    pergunta: Mapped[str] = mapped_column(Text, nullable=False)
    resposta: Mapped[str | None] = mapped_column(Text)
    pecas_relacionadas: Mapped[list[str] | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    # pendente | respondida | erro
    erro_mensagem: Mapped[str | None] = mapped_column(Text)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    caso: Mapped["AutosIACaso"] = relationship(back_populates="perguntas_faq")
