import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EstadoProcesso = Literal["ES", "SP", "AM", "RJ", "outro"]
FaseProcesso = Literal[
    "conhecimento", "recursal", "execucao", "cumprimento_sentenca", "outro"
]
StatusProcesso = Literal["ativo", "suspenso", "arquivado", "encerrado"]

PoloProcesso = Literal[
    "autor", "reu", "litisconsorte", "assistente", "opoente",
    "interveniente", "perito", "avaliador", "interessado",
    "embargante", "embargado", "apelante", "apelado",
    "agravante", "agravado", "recorrente", "recorrido",
    "outro",
]

SistemaJuridico = Literal["esaj", "projudi", "ejud", "pje"]
GrauProcesso = Literal["1grau", "2grau", "stj", "stf", "outro"]
OrgaoJulgadorTipo = Literal["vara", "camara", "turma", "pleno", "orgao_especial", "gabinete", "secao", "outro"]


class ProcessoClienteIn(BaseModel):
    cliente_id: uuid.UUID
    polo: PoloProcesso | None = None
    principal: bool = False


class ProcessoClienteOut(BaseModel):
    cliente_id: uuid.UUID
    nome: str
    polo: str | None = None
    principal: bool = False

    model_config = {"from_attributes": True}


class ProcessoBase(BaseModel):
    numero_cnj: str
    cliente_id: uuid.UUID
    vara: str | None = None
    comarca: str | None = None
    estado: EstadoProcesso
    tribunal: str | None = None
    materia: str | None = None
    fase: FaseProcesso | None = None
    status: StatusProcesso = "ativo"
    objeto: str | None = None
    polo: PoloProcesso | None = None
    # New fields
    orgao_julgador_tipo: OrgaoJulgadorTipo | None = None
    serventia: str | None = None
    foro: str | None = None
    sistema_juridico: SistemaJuridico | None = None
    grau: GrauProcesso | None = None
    grau_texto: str | None = None


class ProcessoCreate(ProcessoBase):
    clientes_litisconsorcio: list[ProcessoClienteIn] = []


class ProcessoUpdate(BaseModel):
    numero_cnj: str | None = None
    vara: str | None = None
    comarca: str | None = None
    estado: EstadoProcesso | None = None
    tribunal: str | None = None
    materia: str | None = None
    fase: FaseProcesso | None = None
    status: StatusProcesso | None = None
    objeto: str | None = None
    polo: PoloProcesso | None = None
    orgao_julgador_tipo: OrgaoJulgadorTipo | None = None
    serventia: str | None = None
    foro: str | None = None
    sistema_juridico: SistemaJuridico | None = None
    grau: GrauProcesso | None = None
    grau_texto: str | None = None
    clientes_litisconsorcio: list[ProcessoClienteIn] | None = None


class ProcessoOut(ProcessoBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    clientes_litisconsorcio: list[ProcessoClienteOut] = []

    model_config = {"from_attributes": True}
