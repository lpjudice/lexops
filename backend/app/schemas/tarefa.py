import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

StatusTarefa = Literal["pendente", "em_andamento", "concluido", "cancelado"]


class TarefaCreate(BaseModel):
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    anotacao_id: uuid.UUID | None = None
    titulo: str
    descricao: str | None = None
    responsavel: str | None = None
    tags: str | None = None
    data_limite: date | None = None
    status: StatusTarefa = "pendente"
    resumo_ia: str | None = None


class TarefaUpdate(BaseModel):
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    titulo: str | None = None
    descricao: str | None = None
    responsavel: str | None = None
    tags: str | None = None
    data_limite: date | None = None
    status: StatusTarefa | None = None
    resumo_ia: str | None = None


class TarefaOut(TarefaCreate):
    id: uuid.UUID
    google_event_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
