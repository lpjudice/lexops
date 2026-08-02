import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Formato = Literal["carrossel", "estatico"]
TemaCapa = Literal["A", "B", "C", "D"]
Variante = Literal["dark", "light", "white", "cream"]
TipoSlide = Literal["capa", "conteudo", "cta"]
FonteTipo = Literal["insight", "publicacao", "andamento", "peca", "tese", "evergreen"]
Status = Literal["sugerido", "aprovado", "rejeitado", "publicado"]


# ── Slide estruturado (renderizado fiel no front) ─────────────────────────────
class CardBlock(BaseModel):
    destaque: str | None = None  # ex.: "Proteção:"
    texto: str


class SlideBlock(BaseModel):
    """Um slide do post. Blocos opcionais montam capa/conteúdo/CTA no padrão visual."""

    variante: Variante = "light"
    tipo: TipoSlide = "conteudo"
    tag: str | None = None            # rótulo pequeno em caixa alta
    titulo: str | None = None         # headline principal
    subtitulo: str | None = None      # subtítulo / apoio
    corpo: str | None = None          # parágrafo de corpo
    bullets: list[str] = []           # lista de tópicos
    cards: list[CardBlock] = []       # cartões destaque
    cta: str | None = None            # texto de chamada (slide final)


# ── Sugestão ──────────────────────────────────────────────────────────────────
class SugestaoOut(BaseModel):
    id: uuid.UUID
    titulo: str
    tema: str
    formato: Formato
    tema_capa: TemaCapa
    slides: list[SlideBlock]
    legenda: str
    hashtags: str
    fonte_tipo: FonteTipo
    fonte_ref: str | None = None
    motivo_ia: str
    status: Status
    data_sugerida: date | None = None
    enviado_assessoria_em: datetime | None = None
    data_geracao: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GerarRequest(BaseModel):
    quantidade: int = 3
    formato: Formato | None = None  # se None, o Agente decide por post


class GerarResponse(BaseModel):
    criadas: int
    sugestoes: list[SugestaoOut]
    aviso: str | None = None


class SugestaoUpdate(BaseModel):
    status: Status | None = None
    data_sugerida: date | None = None
    titulo: str | None = None
    legenda: str | None = None
    hashtags: str | None = None
    slides: list[SlideBlock] | None = None


class EnviarAssessoriaRequest(BaseModel):
    emails: list[str] | None = None  # se None, usa os e-mails padrão da assessoria
    observacao: str | None = None


class EnviarAssessoriaResponse(BaseModel):
    enviado_para: list[str]
    enviado_assessoria_em: datetime


class ConfigOut(BaseModel):
    assessoria_emails: str

    model_config = {"from_attributes": True}


class ConfigUpdate(BaseModel):
    assessoria_emails: str
