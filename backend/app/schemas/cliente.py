import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


def _blank_to_none(v: str | None) -> str | None:
    """Convert empty/whitespace strings to None so unique constraints don't clash."""
    if v is not None and v.strip() == "":
        return None
    return v


class ClienteBase(BaseModel):
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

    @field_validator("cpf_cnpj", "email", "telefone", "endereco", "observacoes", mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nome: str | None = None
    tipo: Literal["PF", "PJ"] | None = None
    cpf_cnpj: str | None = None
    email: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    observacoes: str | None = None
    monitorar_diario: bool | None = None


class ClienteOut(ClienteBase):
    id: uuid.UUID
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
