import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TipoHonorario = Literal["fixo", "percentual", "exito"]
StatusHonorario = Literal["pendente", "parcial", "pago", "cancelado"]
FormaPagamento = Literal["pix", "ted", "boleto", "cheque", "dinheiro", "outro"]
StatusParcela = Literal["pendente", "pago", "cancelado"]


class RecebimentoCreate(BaseModel):
    valor: float
    data_recebimento: date
    forma_pagamento: FormaPagamento = "pix"
    observacao: str | None = None
    parcela_id: uuid.UUID | None = None


class RecebimentoOut(BaseModel):
    id: uuid.UUID
    honorario_id: uuid.UUID
    parcela_id: uuid.UUID | None = None
    valor: float
    data_recebimento: date
    forma_pagamento: FormaPagamento
    observacao: str | None

    model_config = {"from_attributes": True}


# ── Parcelas ──────────────────────────────────────────────────────────────────

class ParcelaInput(BaseModel):
    """Uma parcela no cronograma (criação/edição em lote pelo form do recebível)."""
    numero: int
    valor: float
    data_vencimento: date
    observacao: str | None = None


class ParcelaUpdate(BaseModel):
    valor: float | None = None
    data_vencimento: date | None = None
    observacao: str | None = None


class ParcelaPagar(BaseModel):
    data_recebimento: date | None = None
    forma_pagamento: FormaPagamento = "pix"
    valor: float | None = None          # default = valor da parcela
    observacao: str | None = None


class ParcelaOut(BaseModel):
    id: uuid.UUID
    honorario_id: uuid.UUID
    numero: int
    valor: float
    data_vencimento: date
    status: StatusParcela
    data_pagamento: date | None
    observacao: str | None
    ultimo_lembrete_em: datetime | None = None

    model_config = {"from_attributes": True}


class HonorarioCreate(BaseModel):
    cliente_id: uuid.UUID
    processo_id: uuid.UUID | None = None
    descricao: str
    tipo: TipoHonorario = "fixo"
    valor_total: float
    data_contrato: date | None = None
    data_vencimento: date | None = None
    observacoes: str | None = None
    # Êxito
    valor_causa: float | None = None
    percentual_exito: float | None = None
    data_estimada_sentenca: date | None = None
    # Vínculo com contrato existente + cobrança
    contrato_id: uuid.UUID | None = None
    cobranca_ativa: bool = False
    cobranca_emails: list[str] | None = None
    # Cronograma de parcelas (opcional). Quando informado, valor_total = soma das parcelas
    # e o vencimento simples é ignorado em favor do cronograma.
    parcelas: list[ParcelaInput] | None = None


class HonorarioUpdate(BaseModel):
    descricao: str | None = None
    tipo: TipoHonorario | None = None
    valor_total: float | None = None
    status: StatusHonorario | None = None
    data_contrato: date | None = None
    data_vencimento: date | None = None
    observacoes: str | None = None
    valor_causa: float | None = None
    percentual_exito: float | None = None
    data_estimada_sentenca: date | None = None
    contrato_orfao: bool | None = None
    contrato_id: uuid.UUID | None = None
    cobranca_ativa: bool | None = None
    cobranca_emails: list[str] | None = None


class HonorarioOut(BaseModel):
    id: uuid.UUID
    cliente_id: uuid.UUID
    processo_id: uuid.UUID | None
    descricao: str
    tipo: TipoHonorario
    valor_total: float
    status: StatusHonorario
    total_recebido: float
    saldo_pendente: float
    data_contrato: date | None
    data_vencimento: date | None
    observacoes: str | None
    valor_causa: float | None = None
    percentual_exito: float | None = None
    data_estimada_sentenca: date | None = None
    contrato_id: uuid.UUID | None = None
    pendente_assinatura: bool = False
    contrato_orfao: bool = False
    cobranca_ativa: bool = False
    cobranca_email: str | None = None
    cobranca_emails: list[str] = []
    recebimentos: list[RecebimentoOut]
    parcelas: list[ParcelaOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Resumo ────────────────────────────────────────────────────────────────────

class ResumoCliente(BaseModel):
    cliente_id: uuid.UUID
    cliente_nome: str
    total_contratado: float
    total_recebido: float
    saldo_pendente: float


class ResumoMensal(BaseModel):
    ano: int
    mes: int
    total_recebido: float


class ResumoFinanceiro(BaseModel):
    total_contratado: float
    total_recebido: float
    total_pendente: float
    total_vencido: float              # pendente com data_vencimento < hoje
    total_reembolsos_pendentes: float  # reembolsos aguardando pagamento
    total_reembolsos_pagos: float      # reembolsos já pagos
    projecao_exito: float             # soma dos êxitos esperados (valor_causa × percentual)
    a_vencer_30: float                # saldo pendente que vence em até 30 dias
    a_vencer_60: float                # saldo pendente que vence entre 31-60 dias
    a_vencer_90: float                # saldo pendente que vence entre 61-90 dias
    por_cliente: list[ResumoCliente]
    por_mes: list[ResumoMensal]       # últimos 12 meses
