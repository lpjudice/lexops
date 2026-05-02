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
    confidencial: bool = False


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
    confidencial: bool | None = None


class ReuniaoOut(BaseModel):
    id: uuid.UUID
    titulo: str
    data_reuniao: datetime | None
    duracao_minutos: int | None
    google_meet_url: str | None
    cliente_id: uuid.UUID | None
    processo_id: uuid.UUID | None
    criado_por_id: uuid.UUID | None = None
    drive_transcricao_file_id: str | None
    drive_notas_file_id: str | None
    drive_tldr_file_id: str | None
    transcricao_texto: str | None
    resumo_ia: str | None
    acoes_sugeridas: list[dict[str, Any]] | None
    status: str
    fonte: str
    confidencial: bool = False
    usuarios_com_acesso: list[str] | None = None
    created_at: datetime
    updated_at: datetime
    # Enriched fields (not on the DB model directly)
    cliente_nome: str | None = None
    processo_numero: str | None = None
    criado_por_nome: str | None = None
    # When the meeting is confidential and the user has no access, these are masked
    acesso_restrito: bool = False

    model_config = {"from_attributes": True}


class ConfirmarAcoesRequest(BaseModel):
    """Payload para confirmar ações aprovadas. acoes_sugeridas com aprovada=True serão criadas."""
    acoes_sugeridas: list[dict[str, Any]]


class SolicitarAcessoResponse(BaseModel):
    ok: bool
    mensagem: str
