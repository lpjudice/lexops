import uuid
from datetime import datetime

from pydantic import BaseModel


class TarefaProjetoCreate(BaseModel):
    nome: str
    cor: str = "#6366f1"
    oculto: bool = False


class TarefaProjetoUpdate(BaseModel):
    nome: str | None = None
    cor: str | None = None
    oculto: bool | None = None


class TarefaProjetoOut(BaseModel):
    id: uuid.UUID
    nome: str
    cor: str
    oculto: bool
    created_at: datetime

    model_config = {"from_attributes": True}
