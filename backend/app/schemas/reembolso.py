import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

StatusReembolso = Literal["rascunho", "aguardando_pagamento", "enviado", "pago", "cancelado"]


class ItemReembolsoCreate(BaseModel):
    data: date
    descricao: str
    natureza: str
    documento_comprobatorio: str | None = None
    valor: float


class ItemReembolsoOut(BaseModel):
    id: uuid.UUID
    reembolso_id: uuid.UUID
    data: date
    descricao: str
    natureza: str
    documento_comprobatorio: str | None
    comprovante_path: str | None = None
    comprovante_drive_link: str | None = None  # link do primeiro ComprovanteItem
    valor: float

    model_config = {"from_attributes": True}


class ReembolsoCreate(BaseModel):
    cliente_id: uuid.UUID
    processo_id: uuid.UUID | None = None
    titulo: str
    data_emissao: date
    data_vencimento: date | None = None


class ItemReembolsoUpdate(BaseModel):
    valor: float | None = None
    descricao: str | None = None
    natureza: str | None = None
    documento_comprobatorio: str | None = None
    data: date | None = None


class ReembolsoUpdate(BaseModel):
    titulo: str | None = None
    data_emissao: date | None = None
    data_vencimento: date | None = None
    status: StatusReembolso | None = None
    tratar_como_perda: bool | None = None


class ReembolsoOut(BaseModel):
    id: uuid.UUID
    cliente_id: uuid.UUID
    processo_id: uuid.UUID | None
    titulo: str
    data_emissao: date
    data_vencimento: date | None
    status: StatusReembolso
    tratar_como_perda: bool = False
    total: float
    pdf_path: str | None
    drive_link: str | None = None
    email_destinatario: str | None = None
    ultimo_lembrete_em: datetime | None = None
    itens: list[ItemReembolsoOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
