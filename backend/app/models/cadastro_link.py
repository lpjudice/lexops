"""Autocadastro de cliente via link público (Fase 2).

Dois modelos:
- ClienteCadastroLink: o convite. Genérico (cliente_id nulo, reutilizável) ou
  atrelado a um cliente existente (convite de atualização, uso único).
- ClienteCadastroSubmissao: o que o cliente enviou. NUNCA escreve direto em
  `clientes` — fica em staging até o Lucas aprovar (Fase 3).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ClienteCadastroLink(Base):
    __tablename__ = "cliente_cadastro_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Nulo = link genérico (captação de cliente novo). Preenchido = convite de
    # atualização atrelado a um cliente existente.
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True
    )
    rotulo: Mapped[str | None] = mapped_column(String(255))
    # Genérico é reutilizável (vários envios); convite é uso único por padrão.
    reutilizavel: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogado: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    usos: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    submissoes: Mapped[list["ClienteCadastroSubmissao"]] = relationship(
        "ClienteCadastroSubmissao", back_populates="link"
    )


class ClienteCadastroSubmissao(Base):
    __tablename__ = "cliente_cadastro_submissoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cliente_cadastro_links.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Cliente que este envio pretende atualizar (do convite, ou casado por CPF/CNPJ).
    # Nulo = cadastro novo.
    cliente_id_alvo: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True
    )
    tipo: Mapped[str] = mapped_column(String(2), nullable=False)  # PF | PJ
    # Todos os campos cadastrais preenchidos (dict), validados na aprovação.
    dados: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    # Anexos opcionais em staging: [{filename, path, mime}]. Vão pro Drive na aprovação.
    anexos: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    # LGPD: consentimento carimbado com data/hora e o texto exato exibido.
    consentimento: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    consentimento_texto: Mapped[str | None] = mapped_column(Text)
    consentimento_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)

    # pendente | aprovado | rejeitado
    status: Mapped[str] = mapped_column(
        String(20), default="pendente", server_default="pendente", nullable=False, index=True
    )
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revisado_por_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    link: Mapped["ClienteCadastroLink | None"] = relationship(
        "ClienteCadastroLink", back_populates="submissoes"
    )
