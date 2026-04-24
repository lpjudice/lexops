import uuid
from datetime import date, datetime

from pydantic import BaseModel


class AndamentoOut(BaseModel):
    id: uuid.UUID
    processo_id: uuid.UUID
    data_andamento: date | None
    descricao: str
    tipo: str | None
    fonte: str | None
    grau: str | None
    lido: bool
    notificado: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SincronizacaoResult(BaseModel):
    processo_id: str
    tribunal: str | None
    status: str                          # ok | erro | nenhum
    novos_andamentos: int
    mensagem: str | None
    ultimo_andamento_data: date | None = None   # data do andamento mais recente no DB
