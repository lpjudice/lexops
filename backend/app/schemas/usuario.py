import uuid
from datetime import datetime

from pydantic import BaseModel


class UsuarioBase(BaseModel):
    email: str
    nome: str
    role: str = "membro"
    ativo: bool = False
    pode_ver_financeiro: bool = True
    pode_ver_contratos: bool = True
    pode_ver_tarefas_outros: bool = True
    clientes_restritos: bool = False


class UsuarioCreate(UsuarioBase):
    # senha is NOT required — magic link flow sets it
    pass


class UsuarioUpdate(BaseModel):
    nome: str | None = None
    role: str | None = None
    ativo: bool | None = None
    pode_ver_financeiro: bool | None = None
    pode_ver_contratos: bool | None = None
    pode_ver_tarefas_outros: bool | None = None
    clientes_restritos: bool | None = None
    senha: str | None = None
    primeiro_acesso: bool | None = None


class UsuarioOut(UsuarioBase):
    id: uuid.UUID
    created_at: datetime
    primeiro_acesso: bool = False
    clientes_ids: list[uuid.UUID] = []
    google_email: str | None = None
    google_email_extra: str | None = None

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: str
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


class AcceptInviteRequest(BaseModel):
    senha: str


class UserClienteLink(BaseModel):
    cliente_id: uuid.UUID
