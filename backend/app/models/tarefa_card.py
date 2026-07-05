"""Modelo do módulo "Tarefas Cards" (teste).

Card macro no estilo das Diretrizes (Expansão) combinado com as funções da
Tarefa: responsável, privacidade (confidencial), vínculo a cliente/processo,
agrupamento por Projeto e agenda no Google Calendar.

Tabelas próprias (`tarefa_cards`, `tarefa_card_subtasks`) — não compartilha
registros com o módulo Tarefas atual. Reaproveita apenas a lista de
`tarefa_projetos` para agrupar, por decisão do teste.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TarefaCard(Base):
    __tablename__ = "tarefa_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Agrupamento (reusa a lista de projetos existente, sem puxar tarefas)
    projeto_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tarefa_projetos.id", ondelete="SET NULL"), nullable=True
    )
    # Vínculos
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True
    )
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id", ondelete="SET NULL"), nullable=True
    )
    criado_por_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsavel_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("responsaveis.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pendente")
    data_limite: Mapped[date | None] = mapped_column(Date, nullable=True)
    google_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    ordem: Mapped[int | None] = mapped_column(Integer, nullable=True)

    confidencial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usuarios_com_acesso: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subtasks: Mapped[list["TarefaCardSubtask"]] = relationship(
        "TarefaCardSubtask",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="TarefaCardSubtask.ordem",
    )


class TarefaCardSubtask(Base):
    __tablename__ = "tarefa_card_subtasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tarefa_cards.id", ondelete="CASCADE"), nullable=False
    )
    texto: Mapped[str] = mapped_column(String(500), nullable=False)
    concluida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsavel_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_limite: Mapped[date | None] = mapped_column(Date, nullable=True)

    card: Mapped["TarefaCard"] = relationship("TarefaCard", back_populates="subtasks")
