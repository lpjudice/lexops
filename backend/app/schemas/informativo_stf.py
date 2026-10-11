import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    edicao_id: uuid.UUID
    orgao_julgador: str
    ramo_direito: str
    titulo: str
    destaque_oficial: str
    processo_numero: str | None
    processo_url: str | None
    relator: str | None
    data_julgamento: date | None
    texto_explicativo: str | None
    legislacao_citada: list[str]
    ordem: int
    destacado: bool
    favorito: bool
    motivo_destaque: str | None
    status_ia: str
    resumo_tema_central: str | None
    resumo_ratio_decidendi: str | None
    resumo_leigo: str | None
    instagram_sugestao_id: uuid.UUID | None
    instagram_gerado_em: datetime | None
    instagram_status: str | None = None
    custo_ia_usd: float
    ia_processado_em: datetime | None
    erro_ia: str | None
    edicao_numero: int | None = None


class DestaqueResumoOut(BaseModel):
    id: uuid.UUID
    titulo: str
    resumo_tema_central: str | None
    ramo_direito: str
    favorito: bool


class EdicaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: int
    data_publicacao: date | None
    tipo: str
    tema_extraordinario: str | None
    url_origem: str
    status_scraping: str
    erro_scraping: str | None
    scraped_em: datetime | None
    total_itens: int = 0
    total_destacados: int = 0
    destaques: list[DestaqueResumoOut] = []


class EdicaoDetalheOut(EdicaoOut):
    itens: list[ItemOut] = []


class ConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    areas_selecionadas: list[str]
    keywords_livres: list[str]
    atualizado_em: datetime


class ConfigUpdate(BaseModel):
    areas_selecionadas: list[str]
    keywords_livres: list[str]


class SyncResponse(BaseModel):
    edicoes_processadas: int
    detalhe: list[dict] | None = None
    erro: str | None = None


class CandidatoOut(BaseModel):
    item_id: str
    titulo: str
    tema_central: str | None
    ratio_decidendi: str | None
    processo_numero: str | None
    ramo_direito: str
    edicao_numero: int | None
    url_origem: str | None
