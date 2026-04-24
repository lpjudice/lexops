import uuid
from datetime import date

from sqlalchemy import Date, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Feriado(Base):
    __tablename__ = "feriados"
    __table_args__ = (UniqueConstraint("data", "estado", name="uq_feriado_data_estado"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    data: Mapped[date] = mapped_column(Date, nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    # "nacional" ou sigla do estado: ES, SP, AM, RJ
    estado: Mapped[str] = mapped_column(String(10), nullable=False, default="nacional")
    recorrente: Mapped[bool] = mapped_column(default=True)  # ignora o ano no cálculo
