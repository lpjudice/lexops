import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TipoBem = Literal["movel", "imovel"]
Objetivo = Literal["venda", "aluguel", "segurar"]
StatusBem = Literal["em_validacao", "validado", "incerto"]
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
    status: StatusBem = "em_validacao"
    integralizar_holding: bool = False
    proprietario_real: str | None = None
    proprietario_matricula: str | None = None
    tem_gravame: bool = False
    gravame_descricao: str | None = None
    observacoes: str | None = None


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
    status: StatusBem | None = None
    integralizar_holding: bool | None = None
    proprietario_real: str | None = None
    proprietario_matricula: str | None = None
    tem_gravame: bool | None = None
    gravame_descricao: str | None = None
    observacoes: str | None = None


class BemOut(BemBase):
    id: uuid.UUID
    cliente_id: uuid.UUID
    anexos: list[AnexoOut] = []
    cadeia: list[CadeiaEloOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
