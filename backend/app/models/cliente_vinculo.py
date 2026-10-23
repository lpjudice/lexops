"""Vínculo entre clientes ("Outras pessoas vinculadas").

Relação cliente→cliente, armazenada nas DUAS direções (bidirecional): ao vincular
A↔B gravamos (A,B) e (B,A), para a consulta ser sempre por `cliente_id`.
Substitui o antigo texto livre `empresas_vinculadas` no lado interno — mas aquele
campo continua existindo para guardar o que o cliente digitou no autocadastro.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClienteVinculo(Base):
    __tablename__ = "cliente_vinculos"
    __table_args__ = (
        UniqueConstraint("cliente_id", "vinculado_id", name="uq_cliente_vinculo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    vinculado_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
