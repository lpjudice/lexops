import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
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
