import uuid
from datetime import datetime

from pydantic import BaseModel


class ConversaIACreate(BaseModel):
    cliente_id: uuid.UUID
    titulo: str | None = None
    modelo: str = "claude"
    historico: list[dict] = []
    resumo: str | None = None
    parent_conversa_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None


class ConversaIAUpdate(BaseModel):
    titulo: str | None = None
    historico: list[dict] | None = None
    resumo: str | None = None
    modelo: str | None = None


class ConversaIAOut(ConversaIACreate):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
