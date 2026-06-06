from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ─── Endereço tomador ────────────────────────────────────────────────────────

class EnderecoIn(BaseModel):
    logradouro: str
    numero: str
    bairro: str
    cod_municipio: str          # IBGE 7 dígitos
    cep: str
    complemento: str = ""


# ─── Input para emissão ──────────────────────────────────────────────────────

class EmitirNFSeIn(BaseModel):
    # Competência
    competencia: str = Field(..., pattern=r"^\d{4}-\d{2}$", example="2026-06")

    # Tomador
    tomador_cpf_cnpj: str       # apenas dígitos
    tomador_nome: str
    tomador_email: Optional[str] = None
    tomador_telefone: Optional[str] = None
    tomador_endereco: Optional[EnderecoIn] = None

    # Serviço
    descricao_servico: str
    cod_tributacao_nacional: str = "010900"

    # Valores
    valor_servicos: Decimal = Field(..., gt=0)

    # Retenções (0 = não reter)
    retencao_ir: Decimal = Decimal("0")
    retencao_inss: Decimal = Decimal("0")
    retencao_csll: Decimal = Decimal("0")
    retencao_cofins: Decimal = Decimal("0")
    retencao_pis: Decimal = Decimal("0")

    # IBS/CBS (reforma tributária — agosto 2026)
    ibs_valor: Optional[Decimal] = None
    cbs_valor: Optional[Decimal] = None

    # Vínculo financeiro (opcional)
    honorario_id: Optional[uuid.UUID] = None
    recebimento_id: Optional[uuid.UUID] = None

    # Série da DPS (padrão "1")
    serie: str = "1"


# ─── Output ──────────────────────────────────────────────────────────────────

class NotaFiscalOut(BaseModel):
    id: uuid.UUID
    numero_nfse: Optional[str]
    chave_acesso: Optional[str]
    serie: str
    competencia: str
    data_emissao: Optional[date]

    prestador_cnpj: str
    tomador_cpf_cnpj: str
    tomador_nome: str
    tomador_email: Optional[str]

    cod_tributacao_nacional: str
    descricao_servico: str

    valor_servicos: float
    retencao_ir: Optional[float]
    retencao_inss: Optional[float]
    retencao_csll: Optional[float]
    retencao_cofins: Optional[float]
    retencao_pis: Optional[float]
    ibs_valor: Optional[float]
    cbs_valor: Optional[float]
    valor_liquido: float

    status: str
    erro_mensagem: Optional[str]

    honorario_id: Optional[uuid.UUID]
    recebimento_id: Optional[uuid.UUID]

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotaFiscalResumo(BaseModel):
    id: uuid.UUID
    numero_nfse: Optional[str]
    competencia: str
    data_emissao: Optional[date]
    tomador_nome: str
    valor_servicos: float
    valor_liquido: float
    status: str
    honorario_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


# ─── Pré-preenchimento a partir de honorário ─────────────────────────────────

class PreFillNFSeOut(BaseModel):
    """Dados sugeridos para emissão de NFS-e a partir de um honorário/recebimento."""
    competencia: str
    tomador_cpf_cnpj: Optional[str]
    tomador_nome: Optional[str]
    tomador_email: Optional[str]
    valor_servicos: float
    descricao_servico: str
    honorario_id: uuid.UUID
    recebimento_id: Optional[uuid.UUID]


# ─── Cancelamento ────────────────────────────────────────────────────────────

class CancelarNFSeIn(BaseModel):
    motivo: str = Field(..., min_length=10, max_length=255)
