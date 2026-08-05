import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TipoBem = Literal["movel", "imovel"]
Objetivo = Literal["venda", "aluguel", "uso_proprio", "uso_herdeiro", "nao_fazer_nada", "segurar"]
StatusBem = Literal["em_validacao", "validado", "incerto"]
OrigemTitulo = Literal["matricula_rgi", "escritura_publica", "contrato_particular", "outro"]
TipoDocumentoElo = Literal[
    "contrato_compra_venda",
    "escritura_publica",
    "cessao_direitos",
    "matricula",
    "formal_partilha",
    "outro",
]


# ── Anexos ──────────────────────────────────────────────────────────────────
class AnexoOut(BaseModel):
    id: uuid.UUID
    filename: str
    drive_link: str | None = None
    mime: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Cadeia sucessória ───────────────────────────────────────────────────────
class CadeiaEloBase(BaseModel):
    ordem: int = 0
    tipo_documento: TipoDocumentoElo = "outro"
    de_quem: str | None = None
    para_quem: str | None = None
    data: date | None = None
    descricao: str | None = None


class CadeiaEloCreate(CadeiaEloBase):
    pass


class CadeiaEloUpdate(BaseModel):
    ordem: int | None = None
    tipo_documento: TipoDocumentoElo | None = None
    de_quem: str | None = None
    para_quem: str | None = None
    data: date | None = None
    descricao: str | None = None


class CadeiaEloOut(CadeiaEloBase):
    id: uuid.UUID
    arquivo_nome: str | None = None
    drive_link: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Sócios (bem móvel = cota social) ─────────────────────────────────────────
class SocioBase(BaseModel):
    ordem: int = 0
    nome: str
    cpf: str | None = None
    percentual: float | None = None
    integralizar: bool = False


class SocioCreate(SocioBase):
    pass


class SocioUpdate(BaseModel):
    ordem: int | None = None
    nome: str | None = None
    cpf: str | None = None
    percentual: float | None = None
    integralizar: bool | None = None


class SocioOut(SocioBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Comentários ──────────────────────────────────────────────────────────────
class ComentarioCreate(BaseModel):
    titulo: str | None = None
    texto: str


class ComentarioOut(BaseModel):
    id: uuid.UUID
    titulo: str | None = None
    texto: str
    autor_nome: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Bem ─────────────────────────────────────────────────────────────────────
class BemBase(BaseModel):
    tipo_bem: TipoBem = "imovel"
    nome: str
    descricao: str | None = None
    valor_compra: float | None = None
    valor_mercado: float | None = None
    valor_ir: float | None = None
    data_compra: date | None = None
    objetivo: Objetivo | None = None
    descricao_matricula: str | None = None
    numero_matricula: str | None = None
    cartorio: str | None = None
    origem_titulo: OrigemTitulo | None = None
    escritura_numero: str | None = None
    escritura_livro: str | None = None
    escritura_folha: str | None = None
    status: StatusBem = "em_validacao"
    integralizar_holding: bool = False
    proprietario_real: str | None = None
    proprietario_matricula: str | None = None
    tem_gravame: bool = False
    gravame_descricao: str | None = None
    observacoes: str | None = None
    # Cota social / participação societária (bem móvel)
    empresa_nome: str | None = None
    empresa_cnpj: str | None = None
    capital_social: float | None = None
    valor_balanco: float | None = None
    data_balanco: date | None = None
    participacao_cliente_pct: float | None = None


class BemCreate(BemBase):
    cliente_id: uuid.UUID


class BemUpdate(BaseModel):
    tipo_bem: TipoBem | None = None
    nome: str | None = None
    descricao: str | None = None
    valor_compra: float | None = None
    valor_mercado: float | None = None
    valor_ir: float | None = None
    data_compra: date | None = None
    objetivo: Objetivo | None = None
    descricao_matricula: str | None = None
    numero_matricula: str | None = None
    cartorio: str | None = None
    origem_titulo: OrigemTitulo | None = None
    escritura_numero: str | None = None
    escritura_livro: str | None = None
    escritura_folha: str | None = None
    status: StatusBem | None = None
    integralizar_holding: bool | None = None
    proprietario_real: str | None = None
    proprietario_matricula: str | None = None
    tem_gravame: bool | None = None
    gravame_descricao: str | None = None
    observacoes: str | None = None
    empresa_nome: str | None = None
    empresa_cnpj: str | None = None
    capital_social: float | None = None
    valor_balanco: float | None = None
    data_balanco: date | None = None
    participacao_cliente_pct: float | None = None


class BemOut(BemBase):
    id: uuid.UUID
    cliente_id: uuid.UUID
    ordem: int | None = None
    anexos: list[AnexoOut] = []
    cadeia: list[CadeiaEloOut] = []
    socios: list[SocioOut] = []
    comentarios: list[ComentarioOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
