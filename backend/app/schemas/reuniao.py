import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

StatusReuniao = Literal["pendente", "em_revisao", "processada"]
FonteReuniao = Literal["drive_auto", "manual"]


class ReuniaoCreate(BaseModel):
    titulo: str
    data_reuniao: datetime | None = None
    duracao_minutos: int | None = None
    google_meet_url: str | None = None
    transcricao_texto: str | None = None
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    fonte: FonteReuniao = "manual"
    drive_transcricao_file_id: str | None = None
    drive_notas_file_id: str | None = None


class ReuniaoUpdate(BaseModel):
    titulo: str | None = None
    data_reuniao: datetime | None = None
    duracao_minutos: int | None = None
    google_meet_url: str | None = None
    transcricao_texto: str | None = None
    resumo_ia: str | None = None
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    status: StatusReuniao | None = None
    acoes_sugeridas: list[dict[str, Any]] | None = None


class ReuniaoOut(BaseModel):
    id: uuid.UUID
    titulo: str
    data_reuniao: datetime | None
    duracao_minutos: int | None
    google_meet_url: str | None
    cliente_id: uuid.UUID | None
    processo_id: uuid.UUID | None
    drive_transcricao_file_id: str | None
    drive_notas_file_id: str | None
    drive_tldr_file_id: str | None
    transcricao_texto: str | None
    resumo_ia: str | None
    acoes_sugeridas: list[dict[str, Any]] | None
    status: str
    fonte: str
    created_at: datetime
    updated_at: datetime
    cliente_nome: str | None = None
    processo_numero: str | None = None

    model_config = {"from_attributes": True}


class ConfirmarAcoesRequest(BaseModel):
    """Payload para confirmar ações aprovadas. acoes_sugeridas com aprovada=True serão criadas."""
    acoes_sugeridas: list[dict[str, Any]]
