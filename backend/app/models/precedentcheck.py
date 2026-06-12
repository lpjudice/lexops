import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class PrecedentCheckAnalise(Base):
    __tablename__ = "precedentcheck_analises"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True)
    processo_id = Column(UUID(as_uuid=True), nullable=True)
    titulo = Column(String(500), nullable=True)
    texto_peca = Column(Text, nullable=False)
    # lista de CitacaoVerificada serializada
    citacoes = Column(JSONB, nullable=False, default=list)
    total_citacoes = Column(Integer, nullable=False, default=0)
    total_ok = Column(Integer, nullable=False, default=0)
    total_divergencia = Column(Integer, nullable=False, default=0)
    total_nao_encontrado = Column(Integer, nullable=False, default=0)
    arquivado = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
