import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tarefa(Base):
    __tablename__ = "tarefas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True)
    processo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("processos.id", ondelete="SET NULL"), nullable=True)
    anotacao_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("anotacoes.id", ondelete="SET NULL"), nullable=True)
    criado_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    projeto_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tarefa_projetos.id", ondelete="SET NULL"), nullable=True)
    # Prazo formal ligado a esta tarefa (ex: ambos criados juntos no Despacho).
    prazo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("prazos.id", ondelete="SET NULL"), nullable=True)

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    responsavel: Mapped[str | None] = mapped_column(String(255))
    responsavel_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("responsaveis.id", ondelete="SET NULL"), nullable=True
    )
    tags: Mapped[str | None] = mapped_column(String(500))
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_limite: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pendente")
    resumo_ia: Mapped[str | None] = mapped_column(Text)
    google_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    ordem: Mapped[int | None] = mapped_column(Integer, nullable=True)

    confidencial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # List of usuario UUID strings with explicit access (same "req:" prefix for pending requests)
    usuarios_com_acesso: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)

    # Criada automaticamente pelo gestor jurídico (Despacho), sem clique humano.
    criado_automaticamente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    arquivada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    arquivada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Código curto único da entidade (base36), replicado nas pastas/arquivos do Drive
    codigo: Mapped[str | None] = mapped_column(String(12), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    criado_por: Mapped["Usuario"] = relationship("Usuario", foreign_keys=[criado_por_id])  # noqa: F821
    anexos: Mapped[list["TarefaAnexo"]] = relationship(
        "TarefaAnexo", back_populates="tarefa", cascade="all, delete-orphan"
    )


class TarefaAnexo(Base):
    """Anexo (Drive) de uma tarefa do menu original."""
    __tablename__ = "tarefa_anexos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tarefa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tarefas.id", ondelete="CASCADE"), nullable=False
    )
    nome_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    drive_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    drive_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tarefa: Mapped["Tarefa"] = relationship("Tarefa", back_populates="anexos")
