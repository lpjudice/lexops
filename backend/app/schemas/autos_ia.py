import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TipoPeca = Literal[
    "peticao", "decisao", "despacho", "certidao", "oficio", "recurso", "documento", "outro"
]


class CasoCreate(BaseModel):
    nome: str
    numero_processo: str | None = None
    descricao: str | None = None


class CasoUpdate(BaseModel):
    nome: str | None = None
    numero_processo: str | None = None
    descricao: str | None = None
    status: Literal["ativo", "arquivado"] | None = None


class CasoOut(BaseModel):
    id: uuid.UUID
    nome: str
    numero_processo: str | None
    descricao: str | None
    status: str
    total_paginas: int
    tem_peca_pendente_continuacao: bool
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


class PecaOut(BaseModel):
    id: uuid.UUID
    caso_id: uuid.UUID
    documento_id: uuid.UUID | None
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

    model_config = {"from_attributes": True}


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
