from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class EnderecoIn(BaseModel):
    logradouro: str
    numero: str
    bairro: str
    cod_municipio: str
    cep: str
    complemento: str = ""
    cod_pais: str = "1058"


class IntermediarioIn(BaseModel):
    nome: str
    cpf_cnpj: str
    inscricao_municipal: str = ""


class EmitirNFSeIn(BaseModel):
    # Competência
    competencia: str = Field(..., pattern=r"^\d{4}-\d{2}$", examples=["2026-06"])

    # Tomador
    tomador_cpf_cnpj: str
    tomador_nome: str
    tomador_email: Optional[str] = None
    tomador_telefone: Optional[str] = None
    tomador_endereco: Optional[EnderecoIn] = None
    tomador_no_exterior: bool = False

    # Serviço
    descricao_servico: str
    cod_tributacao_nacional: str = "010900"

    # Tributação
    natureza_operacao: str = "1"   # 1=Tributado município (padrão)
    regime_tributario: str = "1"   # 1=Simples Nacional
    reg_apuracao_sn: str = "3"     # 3=Fed+Mun pelo Simples Nacional

    # Valores
    valor_servicos: Decimal = Field(..., gt=0)
    retencao_ir: Decimal = Decimal("0")
    retencao_inss: Decimal = Decimal("0")
    retencao_csll: Decimal = Decimal("0")
    retencao_cofins: Decimal = Decimal("0")
    retencao_pis: Decimal = Decimal("0")
    iss_retido: bool = False

    # IBS/CBS (reforma tributária agosto 2026)
    ibs_valor: Optional[Decimal] = None
    cbs_valor: Optional[Decimal] = None

    # Intermediário
    intermediario: Optional[IntermediarioIn] = None

    # Vínculo financeiro
    honorario_id: Optional[uuid.UUID] = None
    recebimento_id: Optional[uuid.UUID] = None
    contrato_id: Optional[uuid.UUID] = None

    # Série (padrão "1")
    serie: str = "1"


class NotaFiscalOut(BaseModel):
    id: uuid.UUID
    numero_nfse: Optional[str]
    chave_acesso: Optional[str]
    serie: str
    numero_dps: Optional[int]
    competencia: str
    data_emissao: Optional[date]

    prestador_cnpj: str
    tomador_cpf_cnpj: str
    tomador_nome: str
    tomador_email: Optional[str]

    cod_tributacao_nacional: str
    descricao_servico: str
    natureza_operacao: str
    regime_tributario: str

    valor_servicos: float
    retencao_ir: Optional[float]
    retencao_inss: Optional[float]
    retencao_csll: Optional[float]
    retencao_cofins: Optional[float]
    retencao_pis: Optional[float]
    iss_retido: Optional[bool]
    ibs_valor: Optional[float]
    cbs_valor: Optional[float]
    valor_liquido: float

    status: str
    erro_mensagem: Optional[str]
    xml_nfse: Optional[str]

    honorario_id: Optional[uuid.UUID]
    recebimento_id: Optional[uuid.UUID]
    contrato_id: Optional[uuid.UUID]

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
    contrato_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


class PreFillNFSeOut(BaseModel):
    competencia: str
    tomador_cpf_cnpj: Optional[str]
    tomador_nome: Optional[str]
    tomador_email: Optional[str]
    tomador_telefone: Optional[str]
    valor_servicos: float
    descricao_servico: str
    honorario_id: uuid.UUID
    recebimento_id: Optional[uuid.UUID]
    contrato_id: Optional[uuid.UUID]


class CancelarNFSeIn(BaseModel):
    motivo: str = Field(..., min_length=10, max_length=255)


class CodigoTributacaoOut(BaseModel):
    codigo: str
    label: str
    descricao: str


class OpcaoOut(BaseModel):
    valor: str
    label: str
    descricao: str
