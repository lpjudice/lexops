import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class MemoriaEstrategicaCreate(BaseModel):
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    texto: str

    @model_validator(mode="after")
    def _exige_cliente_ou_processo(self):
        if not self.cliente_id and not self.processo_id:
            raise ValueError("Informe cliente_id e/ou processo_id")
        return self


class MemoriaEstrategicaOut(BaseModel):
    id: uuid.UUID
    cliente_id: uuid.UUID | None
    processo_id: uuid.UUID | None
    texto: str
    autor_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
