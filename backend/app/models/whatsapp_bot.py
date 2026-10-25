import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WhatsappBotMensagem(Base):
    """Memória curta da conversa do bot de clientes por WhatsApp: sem isso cada
    mensagem era respondida isolada e um "1" (escolha de um item da lista que o
    próprio bot acabou de mandar) voltava pro "Olá". Guarda só o necessário pra
    manter o fio e é apagada em poucas horas (ver whatsapp_bot._MEMORIA_*)."""

    __tablename__ = "whatsapp_bot_mensagens"
    __table_args__ = (Index("ix_whatsapp_bot_msgs_tel_data", "telefone8", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telefone8: Mapped[str] = mapped_column(String(8), nullable=False)
    # 'user' | 'assistant'
    papel: Mapped[str] = mapped_column(String(10), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WhatsappRecado(Base):
    """Recado que o assistente de WhatsApp repassou à equipe (cliente pediu algo que só o
    advogado resolve). Guarda o que foi dito e o resultado de cada canal — fica o registro
    mesmo se Telegram/e-mail falharem."""

    __tablename__ = "whatsapp_recados"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    processo_cnj: Mapped[str | None] = mapped_column(String(25), nullable=True)
    # [{"destinatario": "Nome", "email": "enviado|sem_email|erro: ...", "telegram": "enviado|nao_vinculado|falhou"}]
    resultado: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
