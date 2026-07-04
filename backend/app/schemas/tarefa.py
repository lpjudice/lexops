import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

StatusTarefa = Literal["pendente", "em_andamento", "concluido", "cancelado"]


class TarefaCreate(BaseModel):
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    anotacao_id: uuid.UUID | None = None
    projeto_id: uuid.UUID | None = None
    titulo: str
    descricao: str | None = None
    responsavel: str | None = None
    responsavel_email: str | None = None
    tags: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    data_limite: date | None = None
    status: StatusTarefa = "pendente"
    resumo_ia: str | None = None
    confidencial: bool = False
    ordem: int | None = None


class TarefaUpdate(BaseModel):
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    projeto_id: uuid.UUID | None = None
    titulo: str | None = None
    descricao: str | None = None
    responsavel: str | None = None
    responsavel_email: str | None = None
    tags: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    data_limite: date | None = None
    status: StatusTarefa | None = None
    resumo_ia: str | None = None
    confidencial: bool | None = None
    ordem: int | None = None


class PedidoAcessoTarefa(BaseModel):
    usuario_id: str
    nome: str


class TarefaOut(BaseModel):
    id: uuid.UUID
    cliente_id: uuid.UUID | None
    processo_id: uuid.UUID | None
    anotacao_id: uuid.UUID | None
    projeto_id: uuid.UUID | None = None
    projeto_nome: str | None = None
    projeto_cor: str | None = None
    criado_por_id: uuid.UUID | None = None
    titulo: str
    descricao: str | None
    responsavel: str | None
    responsavel_email: str | None = None
    tags: str | None
    data_inicio: date | None = None
    data_fim: date | None = None
    data_limite: date | None
    status: str
    resumo_ia: str | None
    google_event_id: str | None = None
    ordem: int | None = None
    confidencial: bool = False
    usuarios_com_acesso: list[str] | None = None
    criado_automaticamente: bool = False
    created_at: datetime
    updated_at: datetime
    # Enriched
    criado_por_nome: str | None = None
    cliente_nome: str | None = None
    # Access control
    acesso_restrito: bool = False
    pedidos_acesso: list[PedidoAcessoTarefa] = []
    ja_solicitou: bool = False
    usuarios_com_acesso_nomes: list[dict] = []  # [{id, nome}] for granted users (not pending)

    model_config = {"from_attributes": True}


class SolicitarAcessoTarefaResponse(BaseModel):
    ok: bool
    mensagem: str
