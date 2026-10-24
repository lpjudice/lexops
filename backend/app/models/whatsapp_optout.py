import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WhatsappOptOut(Base):
    """Quem pediu pra NÃO receber mais mensagens de marketing por WhatsApp
    (botão "Parar de receber" do template ou texto PARAR). Vale pra qualquer
    pessoa — contato do Conselho, cliente ou inscrito — e é consultada antes de
    todo envio de marketing. Chave = últimos 8 dígitos do número (mesmo critério
    do bot que identifica o remetente, que ignora DDI/DDD/nono dígito)."""

    __tablename__ = "whatsapp_optout"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telefone8: Mapped[str] = mapped_column(String(8), nullable=False, unique=True, index=True)
    # 'botao' | 'texto' | 'manual'
    origem: Mapped[str] = mapped_column(String(20), nullable=False, default="botao")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
