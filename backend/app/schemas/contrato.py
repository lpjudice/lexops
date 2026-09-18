import uuid
from datetime import date, datetime
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
    cpf: str | None = None
    data_nascimento: date | None = None


class SignatarioOut(SignatarioCreate):
    id: uuid.UUID
    contrato_id: uuid.UUID
    clicksign_signer_key: str | None
    status_assinatura: StatusAssinatura
    assinado_em: datetime | None

    model_config = {"from_attributes": True}


TipoDocumento = Literal["contrato", "procuracao"]


class ContratoCreate(BaseModel):
    cliente_id: uuid.UUID
    processo_id: uuid.UUID | None = None
    titulo: str
    descricao: str | None = None
    tipo_documento: TipoDocumento = "contrato"


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


class OutorgadoInput(BaseModel):
    nome: str = ""
    oab: str = ""
    cpf: str = ""


# Chaves válidas para GerarProcuracaoRequest.poderes_especiais — ver PODERES_ESPECIAIS_OPCOES
# em app/services/procuracao_pdf.py para o texto de cada uma.
PoderEspecial = Literal[
    "confessar", "desistir", "transigir", "firmar_acordos", "receber_quitacao", "substabelecer"
]

DEFAULT_PODERES_ESPECIAIS: list[PoderEspecial] = [
    "confessar", "desistir", "transigir", "firmar_acordos", "receber_quitacao", "substabelecer"
]


TipoOutorgante = Literal["PF", "PJ"]


class GerarProcuracaoRequest(BaseModel):
    outorgante_tipo: TipoOutorgante = "PF"
    outorgante_nome: str
    outorgante_nacionalidade: str = "brasileiro(a)"
    outorgante_estado_civil: str = ""
    outorgante_profissao: str = ""
    outorgante_cpf_cnpj: str = ""
    outorgante_endereco: str = ""
    outorgante_email: str = ""
    # Só relevante quando outorgante_tipo == "PJ" (representante legal da empresa).
    outorgante_representante_nome: str = ""
    outorgante_representante_cpf: str = ""
    outorgante_representante_cargo: str = ""
    outorgados: list[OutorgadoInput] = []
    endereco_escritorio: str = ""
    incluir_poderes_gerais: bool = True
    poderes_especiais: list[PoderEspecial] = DEFAULT_PODERES_ESPECIAIS
    poderes_adicionais: str = ""
    finalidade: str = ""
    data_validade: str = ""           # YYYY-MM-DD, opcional
    data_procuracao: str = ""         # YYYY-MM-DD


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
    # Quando True, pula o alerta de nome parecido ao criar (revisor já
    # confirmou que é pessoa/empresa diferente de um cliente existente).
    ignorar_similares: bool = False


class ContratoFinanceiro(BaseModel):
    """Dados financeiros lidos do contrato (para lançar/atualizar o Honorário)."""
    valor_honorarios: float | None = None
    tem_exito: bool = False
    percentual_exito: float | None = None
    valor_causa: float | None = None
    data_vencimento: str | None = None
    condicao_pagamento: str | None = None
    num_parcelas: int | None = None
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
    doc_gerado_filename: str | None = None
    procuracao_dados: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
