import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

StatusInformativo = Literal["rascunho", "primeiro_draft", "revisado", "publicado"]


class InformativoOut(BaseModel):
    id: uuid.UUID
    numero: int | None = None
    mes_referencia: date
    titulo: str
    tema_resumido: str | None = None
    tema_sugestao_id: uuid.UUID | None = None
    status: StatusInformativo
    responsavel_id: uuid.UUID | None = None
    google_doc_id: str | None = None
    google_doc_link: str | None = None
    conteudo_texto: str | None = None
    paginas_estimadas: float | None = None
    citacoes_validadas: list[dict] = []
    arquivos_referencia: list[dict] = []
    instrucoes_ia: str | None = None
    rascunho_gerado_em: datetime | None = None
    drive_folder_link: str | None = None
    drive_pdf_link: str | None = None
    data_prazo_draft: date | None = None
    data_prazo_final: date | None = None
    lembrete_draft_enviado: bool = False
    lembrete_final_enviado: bool = False
    publicado_em: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InformativoCriar(BaseModel):
    mes_referencia: date
    titulo: str
    responsavel_id: uuid.UUID | None = None
    tema_resumido: str | None = None
    tema_sugestao_id: uuid.UUID | None = None


class InformativoAtualizar(BaseModel):
    titulo: str | None = None
    tema_resumido: str | None = None
    responsavel_id: uuid.UUID | None = None
    status: StatusInformativo | None = None
    instrucoes_ia: str | None = None


class SincronizarResponse(BaseModel):
    conteudo_texto: str


class ValidarCitacoesResponse(BaseModel):
    citacoes: list[dict]


class PublicarResponse(BaseModel):
    paginas: int
    aviso: str | None = None
    pdf_link: str | None = None
