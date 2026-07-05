import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TipoPrazo = Literal[
    "contestacao", "recurso", "contrarrazoes", "manifestacao",
    "audiencia", "pericia", "outro"
]
TipoContagem = Literal["uteis", "corridos"]
StatusPrazo = Literal["pendente", "cumprido", "perdido", "ignorado"]


class PrazoBase(BaseModel):
    processo_id: uuid.UUID
    tipo: TipoPrazo
    descricao: str | None = None
    peca_necessaria: str | None = None
    responsavel: str | None = None
    data_publicacao: date
    dias_prazo: int
    tipo_contagem: TipoContagem = "uteis"
    status: StatusPrazo = "pendente"


class PrazoCreate(PrazoBase):
    pass


class PrazoUpdate(BaseModel):
    tipo: TipoPrazo | None = None
    descricao: str | None = None
    peca_necessaria: str | None = None
    responsavel: str | None = None
    data_publicacao: date | None = None
    dias_prazo: int | None = None
    tipo_contagem: TipoContagem | None = None
    status: StatusPrazo | None = None


class TarefaVinculada(BaseModel):
    id: uuid.UUID
    titulo: str


class PrazoOut(PrazoBase):
    id: uuid.UUID
    data_limite: date | None
    data_limite_sem_feriado: date | None
    peca_necessaria: str | None
    responsavel: str | None
    google_event_id: str | None
    criado_automaticamente: bool = False
    tarefas_vinculadas: list[TarefaVinculada] = []
    peca_doc_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
