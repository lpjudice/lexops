from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JusbrSession(Base):
    """Single-row store for the shared jus.br/PDPJ session.

    Persisted in Postgres so it survives Fly.io deploys / machine swaps without
    extra cost (same database). Only one row is used (id == 1).
    """

    __tablename__ = "jusbr_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
