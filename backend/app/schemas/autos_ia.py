import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, computed_field

TipoPeca = Literal[
    "peticao", "decisao", "despacho", "certidao", "oficio", "recurso", "documento", "outro"
]


class CasoCreate(BaseModel):
    nome: str
    numero_processo: str | None = None
    descricao: str | None = None
    processo_id: uuid.UUID | None = None
    sync_jusbr_ativo: bool = False


class CasoUpdate(BaseModel):
    nome: str | None = None
    numero_processo: str | None = None
    descricao: str | None = None
    status: Literal["ativo", "arquivado"] | None = None
    processo_id: uuid.UUID | None = None
    sync_jusbr_ativo: bool | None = None


class CasoOut(BaseModel):
    id: uuid.UUID
    nome: str
    numero_processo: str | None
    descricao: str | None
    status: str
    total_paginas: int
    tem_peca_pendente_continuacao: bool
    processo_id: uuid.UUID | None
    sync_jusbr_ativo: bool
    ultima_sincronizacao_em: datetime | None
    ultimo_sync_status: str | None
    ultimo_sync_mensagem: str | None
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class CasoResumo(CasoOut):
    total_pecas: int
    total_documentos: int
    total_perguntas_faq: int


class DocumentoOut(BaseModel):
    id: uuid.UUID
    caso_id: uuid.UUID
    nome_arquivo: str
    pagina_inicio: int
    pagina_fim: int
    status: str
    erro_mensagem: str | None
    pecas_geradas: int
    paginas_ocr: int
    criado_em: datetime

    model_config = {"from_attributes": True}


OrigemPeca = Literal["upload", "jusbr"]


class PecaOut(BaseModel):
    id: uuid.UUID
    caso_id: uuid.UUID
    documento_id: uuid.UUID | None
    andamento_id: uuid.UUID | None
    peca_pai_id: uuid.UUID | None
    tipo: str
    titulo: str
    autor: str | None
    data_peca: date | None
    id_processual: str | None
    pagina_inicio: int
    pagina_fim: int
    resumo: str | None
    keywords: list[str] | None
    ids_mencionados: list[str] | None
    status: str
    erro_mensagem: str | None
    criado_em: datetime
    total_anexos: int = 0

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def origem(self) -> OrigemPeca:
        return "jusbr" if self.andamento_id else "upload"


class PecaDetalheOut(PecaOut):
    texto_md: str


class GrafoNo(BaseModel):
    id: uuid.UUID
    tipo: str
    titulo: str
    autor: str | None
    data_peca: date | None
    id_processual: str | None
    resumo: str | None
    keywords: list[str] | None
    pagina_inicio: int
    pagina_fim: int
    peca_pai_id: uuid.UUID | None = None


class GrafoAresta(BaseModel):
    id: uuid.UUID
    peca_origem_id: uuid.UUID
    peca_destino_id: uuid.UUID | None
    id_mencionado: str


class GrafoOut(BaseModel):
    nos: list[GrafoNo]
    arestas: list[GrafoAresta]


class FaqPerguntaCreate(BaseModel):
    pergunta: str


class FaqPerguntaOut(BaseModel):
    id: uuid.UUID
    caso_id: uuid.UUID
    pergunta: str
    resposta: str | None
    pecas_relacionadas: list[str] | None
    status: str
    erro_mensagem: str | None
    criado_em: datetime

    model_config = {"from_attributes": True}
