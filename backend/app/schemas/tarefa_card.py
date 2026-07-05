import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

StatusTarefaCard = Literal["pendente", "em_andamento", "concluido", "cancelado"]


# ── Subtasks ────────────────────────────────────────────────────────────────

class SubtaskCardCreate(BaseModel):
    texto: str
    concluida: bool = False
    ordem: int = 0
    responsavel: str | None = None
    responsavel_email: str | None = None
    data_limite: date | None = None


class SubtaskCardOut(BaseModel):
    id: uuid.UUID
    texto: str
    concluida: bool
    ordem: int
    responsavel: str | None = None
    responsavel_email: str | None = None
    data_limite: date | None = None

    model_config = {"from_attributes": True}


# ── Cards ───────────────────────────────────────────────────────────────────

class TarefaCardCreate(BaseModel):
    projeto_id: uuid.UUID | None = None
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    titulo: str
    descricao: str | None = None
    notas: str | None = None
    responsavel: str | None = None
    responsavel_email: str | None = None
    responsavel_id: uuid.UUID | None = None
    status: StatusTarefaCard = "pendente"
    data_limite: date | None = None
    confidencial: bool = False
    ordem: int | None = None
    subtasks: list[SubtaskCardCreate] = []


class TarefaCardUpdate(BaseModel):
    projeto_id: uuid.UUID | None = None
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    titulo: str | None = None
    descricao: str | None = None
    notas: str | None = None
    responsavel: str | None = None
    responsavel_email: str | None = None
    responsavel_id: uuid.UUID | None = None
    status: StatusTarefaCard | None = None
    data_limite: date | None = None
    confidencial: bool | None = None
    ordem: int | None = None


class PedidoAcessoCard(BaseModel):
    usuario_id: str
    nome: str


class TarefaCardOut(BaseModel):
    id: uuid.UUID
    projeto_id: uuid.UUID | None = None
    projeto_nome: str | None = None
    projeto_cor: str | None = None
    cliente_id: uuid.UUID | None = None
    cliente_nome: str | None = None
    processo_id: uuid.UUID | None = None
    processo_numero: str | None = None
    criado_por_id: uuid.UUID | None = None
    criado_por_nome: str | None = None
    titulo: str
    descricao: str | None = None
    notas: str | None = None
    responsavel: str | None = None
    responsavel_email: str | None = None
    responsavel_id: uuid.UUID | None = None
    status: str
    data_limite: date | None = None
    google_event_id: str | None = None
    ordem: int | None = None
    confidencial: bool = False
    usuarios_com_acesso: list[str] | None = None
    created_at: datetime
    updated_at: datetime
    subtasks: list[SubtaskCardOut] = []
    # Access control
    acesso_restrito: bool = False
    pedidos_acesso: list[PedidoAcessoCard] = []
    ja_solicitou: bool = False
    usuarios_com_acesso_nomes: list[dict] = []

    model_config = {"from_attributes": True}


class SolicitarAcessoCardResponse(BaseModel):
    ok: bool
    mensagem: str
