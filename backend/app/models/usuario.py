import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    senha_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="membro")
    ativo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # False until invite accepted
    pode_ver_financeiro: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pode_ver_contratos: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pode_ver_tarefas_outros: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    clientes_restritos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Magic link invite
    invite_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invite_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # First login — redirect to Configurações
    primeiro_acesso: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Per-user personal Google OAuth tokens
    google_tokens: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
