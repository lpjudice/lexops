import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

StatusContrato = Literal[
    "rascunho", "aguardando_assinatura", "parcialmente_assinado", "assinado", "cancelado"
]
PapelSignatario = Literal["contratante", "contratado", "testemunha", "outro"]
StatusAssinatura = Literal["pendente", "assinado", "recusado"]


class SignatarioCreate(BaseModel):
    nome: str
    email: str
    papel: PapelSignatario = "outro"


class SignatarioOut(SignatarioCreate):
    id: uuid.UUID
    contrato_id: uuid.UUID
    clicksign_signer_key: str | None
    status_assinatura: StatusAssinatura
    assinado_em: datetime | None

    model_config = {"from_attributes": True}


class ContratoCreate(BaseModel):
    cliente_id: uuid.UUID
    processo_id: uuid.UUID | None = None
    titulo: str
    descricao: str | None = None


class ContratoUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    processo_id: uuid.UUID | None = None
    status: StatusContrato | None = None


class ContratoArquivoItem(BaseModel):
    filename: str
    path: str
    clicksign_key: str | None = None


class GerarPdfRequest(BaseModel):
    contratante_nome: str
    contratante_qualificacao: str = ""
    contratante_cpf_cnpj: str = ""
    contratante_endereco: str = ""
    contratante_email: str = ""
    objeto_tipo: str = "PPS"          # "PPS" | "Personalizado"
    objeto_texto_livre: str = ""
    valor_honorarios: str = ""
    valor_honorarios_num: float | None = None  # valor numérico para financeiro
    valor_causa: float | None = None           # valor da causa para êxito
    data_vencimento: str = ""
    condicao_pagamento: str = ""
    percentual_exito: str = "15%"
    percentual_exito_num: float | None = None  # % numérico para financeiro
    data_contrato: str = ""           # YYYY-MM-DD


# ── Leitura de contratantes por IA (upload) ──────────────────────────────────

class ContratanteDecisao(BaseModel):
    """Decisão da tela de revisão para UM contratante lido pela IA."""
    acao: Literal["atualizar", "criar", "ignorar"] = "criar"
    cliente_id: uuid.UUID | None = None   # obrigatório quando acao == "atualizar"
    nome: str
    tipo: Literal["PF", "PJ"] = "PF"
    cpf_cnpj: str | None = None
    email: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    estado_civil: str | None = None
    profissao: str | None = None
    # Nota para distinguir um 2º cadastro homônimo (vai para observações).
    diferenciador: str | None = None
    # Contratante em nome de quem o contrato fica vinculado (o "principal").
    principal: bool = False


class ContratoFinanceiro(BaseModel):
    """Dados financeiros lidos do contrato (para lançar/atualizar o Honorário)."""
    valor_honorarios: float | None = None
    tem_exito: bool = False
    percentual_exito: float | None = None
    valor_causa: float | None = None
    data_vencimento: str | None = None
    condicao_pagamento: str | None = None
    data_contrato: str | None = None


class AplicarContratantesRequest(BaseModel):
    decisoes: list[ContratanteDecisao]
    # Se True, o contrato passa a apontar para o cliente do contratante principal.
    vincular_contrato: bool = True
    # Se True, cria/atualiza o Honorário do contrato a partir de `financeiro`.
    lancar_financeiro: bool = False
    financeiro: ContratoFinanceiro | None = None


class ContratoOut(ContratoCreate):
    id: uuid.UUID
    arquivo_path: str | None
    arquivo_assinado_path: str | None
    arquivos: list[dict] = []
    status: StatusContrato
    assinatura_manual: bool = False
    drive_link_cliente: str | None = None
    drive_link_master: str | None = None
    clicksign_document_key: str | None
    signatarios: list[SignatarioOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
