import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, field_validator


def _blank_to_none(v: str | None) -> str | None:
    """Convert empty/whitespace strings to None so unique constraints don't clash."""
    if v is not None and v.strip() == "":
        return None
    return v


_CADASTRO_STR_FIELDS = (
    "cpf_cnpj", "email", "telefone", "whatsapp", "endereco", "observacoes",
    "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
    "rg", "estado_civil", "profissao", "empresas_vinculadas",
    "nome_fantasia", "responsavel_nome", "responsavel_cpf",
    "responsavel_email", "responsavel_telefone",
)


class _CadastroFields(BaseModel):
    """Campos cadastrais estendidos, compartilhados por Base/Update/Out."""

    whatsapp: str | None = None
    # Endereço estruturado
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    # Pessoa Física
    data_nascimento: date | None = None
    rg: str | None = None
    estado_civil: str | None = None
    profissao: str | None = None
    empresas_vinculadas: str | None = None
    # Pessoa Jurídica
    nome_fantasia: str | None = None
    responsavel_nome: str | None = None
    responsavel_cpf: str | None = None
    responsavel_email: str | None = None
    responsavel_telefone: str | None = None


class ClienteBase(_CadastroFields):
    nome: str
    tipo: Literal["PF", "PJ"]
    cpf_cnpj: str | None = None
    email: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    observacoes: str | None = None
    incompleto: bool = False
    # Opt-in: quando True, o nome deste cliente entra na busca automática do Diário Oficial.
    monitorar_diario: bool = False

    @field_validator(*_CADASTRO_STR_FIELDS, mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(_CadastroFields):
    nome: str | None = None
    tipo: Literal["PF", "PJ"] | None = None
    cpf_cnpj: str | None = None
    email: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    observacoes: str | None = None
    monitorar_diario: bool | None = None

    @field_validator(*_CADASTRO_STR_FIELDS, mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class ClienteOut(ClienteBase):
    id: uuid.UUID
    origem_cadastro: str | None = None
    projeto_nome: str | None = None
    worktree_nome: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def get_cliente_with_processos_model():
    from app.schemas.processo import ProcessoOut

    class ClienteWithProcessos(ClienteOut):
        processos: list[ProcessoOut] = []

    return ClienteWithProcessos


# Instanciado na primeira importação para evitar circular import
ClienteWithProcessos = get_cliente_with_processos_model()
