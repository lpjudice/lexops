import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TipoAnotacao = Literal["reuniao", "ligacao", "whatsapp", "email", "documento", "anamnese", "reuniao_todo", "outro"]


class AnotacaoBase(BaseModel):
    cliente_id: uuid.UUID
    processo_id: uuid.UUID | None = None
    tipo: TipoAnotacao = "outro"
    data_evento: date
    titulo: str | None = None
    texto: str


class AnotacaoCreate(AnotacaoBase):
    pass


class AnotacaoUpdate(BaseModel):
    tipo: TipoAnotacao | None = None
    data_evento: date | None = None
    titulo: str | None = None
    texto: str | None = None
    processo_id: uuid.UUID | None = None


class AnotacaoOut(AnotacaoBase):
    id: uuid.UUID
    reuniao_id: uuid.UUID | None = None
    confidencial: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TimelineItem(BaseModel):
    """Item unificado da timeline do cliente."""
    tipo: Literal["anotacao", "prazo", "publicacao", "email", "reuniao"]
    data: str  # ISO string para ordenação uniforme
    titulo: str
    subtitulo: str | None = None
    texto: str | None = None
    referencia_id: str | None = None  # id do objeto original
    meta: dict = {}  # campos extras (status, fonte, etc.)
