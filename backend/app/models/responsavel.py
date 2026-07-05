"""Responsável — pessoa que pode ser atribuída a uma tarefa/prazo/card.

Unifica dois tipos de gente na mesma lista pesquisável:
- usuário do sistema (tem login, `usuario_id` preenchido, sincronizado
  automaticamente com o cadastro em Usuários);
- "manual" (advogado ou terceiro sem acesso ao sistema, cadastrado direto
  aqui — ex: advogado da parte contrária citado numa publicação).

`categoria` é só uma etiqueta de organização (advogado/terceiro/colaborador/
financeiro), não controla permissão nenhuma — isso continua em Usuario.role.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Responsavel(Base):
    __tablename__ = "responsaveis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    oab_numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    oab_uf: Mapped[str | None] = mapped_column(String(2), nullable=True)

    categoria: Mapped[str] = mapped_column(
        Enum("advogado", "terceiro", "colaborador", "financeiro", name="categoria_responsavel"),
        nullable=False,
        default="terceiro",
    )

    # Preenchido quando este responsável é também um usuário logável do
    # sistema — mantido em sincronia (nome/email) pelo router de usuários.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=True, unique=True
    )

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
