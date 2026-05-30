import hashlib
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AndamentoProcesso(Base):
    __tablename__ = "andamentos_processo"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    processo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    data_andamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(255), nullable=True)    # e.g. "Despacho", "Sentença"
    fonte: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "TJES", "TJSP", etc.
    grau: Mapped[str | None] = mapped_column(String(10), nullable=True)    # "1G", "2G"
    arquivo_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arquivo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    arquivo_drive_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    documento_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    hash_unico: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lido: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notificado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    processo: Mapped["Processo"] = relationship("Processo", back_populates="andamentos")  # noqa: F821

    @staticmethod
    def calcular_hash(
        processo_id: str,
        data_andamento: str | None,
        descricao: str,
        documento_id: str | None = None,
    ) -> str:
        raw = f"{processo_id}|{data_andamento}|{descricao[:500]}"
        # Documentos distintos do mesmo movimento podem ter descrição idêntica
        # (ex.: dois "Petição" na mesma juntada). Incluir o id único do documento
        # mantém o hash exclusivo por documento. Para linhas sem documento o hash
        # permanece idêntico ao formato antigo (compatibilidade).
        if documento_id:
            raw += f"|{documento_id}"
        return hashlib.sha256(raw.encode()).hexdigest()


class SincronizacaoLog(Base):
    __tablename__ = "sincronizacao_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    processo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tribunal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")  # ok | erro | nenhum
    novos_andamentos: Mapped[int] = mapped_column(Integer, default=0)
    mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)
    iniciado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
