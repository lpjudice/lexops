import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Formato = Literal["carrossel", "estatico"]
TemaCapa = Literal["A", "B", "C", "D"]  # legado (não usado no novo design)
TipoSlide = Literal["capa", "conteudo", "fechamento"]
FonteTipo = Literal["insight", "publicacao", "andamento", "peca", "tese", "evergreen"]
Status = Literal["sugerido", "aprovado", "rejeitado", "publicado"]

# Layouts do design system @dr.lucasjudice (5 capas + 5 miolos + fechamento)
Layout = Literal[
    "capa_teal", "capa_offwhite", "capa_split", "capa_cream", "capa_keyword",
    "editorial", "numero", "icones", "citacao", "imagem",
    "fechamento",
]
# Ícones de linha disponíveis para o layout "icones" (o front conhece cada nome)
IconeNome = Literal[
    "usuario", "balanca", "check", "escudo", "casa", "familia",
    "documento", "acordo", "grafico", "engrenagem", "cofre", "arvore",
]


class IconeItem(BaseModel):
    icone: IconeNome = "check"
    label: str


class SlideBlock(BaseModel):
    """Um slide do post no novo design system (minimalista, sem bullet points).

    O campo `layout` decide a montagem visual; os demais campos são preenchidos
    conforme o layout (ver prompt em ia_instagram)."""

    tipo: TipoSlide = "conteudo"
    layout: Layout = "editorial"
    kicker: str | None = None         # rótulo curto em caixa alta (ex.: "HOLDING · SUCESSÃO")
    titulo: str | None = None         # headline principal
    frase: str | None = None          # 1 frase de apoio (nunca listas)
    numero: str | None = None         # layout "numero": dado de impacto (ex.: "50/50")
    citacao: str | None = None        # layout "citacao": definição/quote em card
    icones: list[IconeItem] = []      # layout "icones": 2–3 ícones com rótulo
    imagem_hint: str | None = None    # layout "imagem": descrição da imagem/ilustração sugerida
    destaque: str | None = None       # capa_keyword: palavra realçada
    cta: str | None = None            # fechamento: texto do botão pílula


# ── Sugestão ──────────────────────────────────────────────────────────────────
class SugestaoOut(BaseModel):
    id: uuid.UUID
    titulo: str
    tema: str
    formato: Formato
    tema_capa: str
    # JSON livre: convive com sugestões antigas (schema velho) e novas sem quebrar
    slides: list[dict]
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


class AjustarRequest(BaseModel):
    """Pedido de ajuste pontual: a IA muda SÓ o que for pedido, mantém o resto."""
    instrucao: str
    slide_index: int | None = None  # opcional: focar num slide específico


class CardPublicoOut(BaseModel):
    """Versão pública (sem auth) do card, para render em /post/{id}."""
    id: uuid.UUID
    titulo: str
    formato: Formato
    slides: list[dict]
    legenda: str
    hashtags: str
    status: Status
    data_sugerida: date | None = None

    model_config = {"from_attributes": True}


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
