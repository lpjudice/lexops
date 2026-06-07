import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RelatorioFiscalLog(Base):
    """Histórico de relatórios fiscais enviados ao contador."""
    __tablename__ = "relatorio_fiscal_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competencia: Mapped[str] = mapped_column(String(7), nullable=False)
    enviado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    destinatarios: Mapped[list] = mapped_column(JSONB, default=list)
    cc: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nf_qtd: Mapped[int] = mapped_column(Integer, default=0)
    anexos: Mapped[int] = mapped_column(Integer, default=0)
    gmail_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    drive_pasta_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="enviado")  # enviado | erro
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)
