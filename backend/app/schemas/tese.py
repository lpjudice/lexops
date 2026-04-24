import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ModeloIA = Literal["claude", "gpt", "gemini"]


class TeseCreate(BaseModel):
    titulo: str
    texto_input: str
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    modelo_ativo: ModeloIA = "claude"


class TeseUpdate(BaseModel):
    titulo: str | None = None
    modelo_ativo: ModeloIA | None = None


class TeseOut(BaseModel):
    id: uuid.UUID
    titulo: str
    texto_input: str
    resposta_claude: str | None
    resposta_gpt: str | None
    resposta_gemini: str | None
    modelo_ativo: ModeloIA
    cliente_id: uuid.UUID | None
    processo_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
