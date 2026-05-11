import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

FontePublicacao = Literal[
    "gmail", "scraping_tjes", "scraping_tjsp", "scraping_tjam", "scraping_tjrj", "scraping_djen", "pje_comunica", "manual"
]
TipoAto = Literal[
    "despacho", "decisao", "sentenca", "acordao", "intimacao", "citacao", "outro"
]


class PublicacaoBase(BaseModel):
    fonte: FontePublicacao
    data_publicacao: date
    numero_cnj: str | None = None
    tipo_ato: TipoAto | None = None
    tribunal: str | None = None
    vara: str | None = None
    texto_resumo: str | None = None
    texto_completo: str | None = None
    processo_id: uuid.UUID | None = None
    lida: bool = False
    gera_prazo: bool = False


class PublicacaoCreate(PublicacaoBase):
    pass


class PublicacaoUpdate(BaseModel):
    processo_id: uuid.UUID | None = None
    lida: bool | None = None
    gera_prazo: bool | None = None
    prazo_id: uuid.UUID | None = None
    tipo_ato: TipoAto | None = None
    vara: str | None = None


class PublicacaoOut(PublicacaoBase):
    id: uuid.UUID
    prazo_id: uuid.UUID | None
    email_message_id: str | None
    analise_ia: str | None = None
    cliente_nome_pub: str | None = None
    url_fonte: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncResult(BaseModel):
    inseridas: int
    duplicatas: int
    erros: int
    fonte: str
    mensagem: str | None = None
