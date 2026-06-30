import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

CategoriaDiretriz = Literal["operacional", "juridico", "comercial", "parcerias"]
StatusDiretriz = Literal["Não iniciado", "Em andamento", "Bloqueado", "Concluído", "Atrasado"]
TipoParceiro = Literal["Advogado", "Contador", "Assessor de investimentos", "Outro"]
StatusParceiro = Literal["Quente", "Frio", "Reativado"]


# ── Diretrizes ────────────────────────────────────────────────────────────

class SubtaskCreate(BaseModel):
    texto: str
    concluida: bool = False
    ordem: int = 0


class SubtaskOut(SubtaskCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class AnexoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nome_arquivo: str
    storage_path: str | None = None
    created_at: datetime


class DiretrizCreate(BaseModel):
    categoria: CategoriaDiretriz
    titulo: str
    descricao: str | None = None
    prazo: date | None = None
    status: StatusDiretriz = "Não iniciado"
    notas: str | None = None
    subtasks: list[SubtaskCreate] = []


class DiretrizUpdate(BaseModel):
    categoria: CategoriaDiretriz | None = None
    titulo: str | None = None
    descricao: str | None = None
    prazo: date | None = None
    status: StatusDiretriz | None = None
    notas: str | None = None


class DiretrizOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    categoria: str
    titulo: str
    descricao: str | None
    prazo: date | None
    status: str
    notas: str | None
    created_at: datetime
    updated_at: datetime
    subtasks: list[SubtaskOut] = []
    anexos: list[AnexoOut] = []


# ── Pipeline ──────────────────────────────────────────────────────────────

class PipelineCreate(BaseModel):
    nome: str
    origem: str | None = None
    tema: str | None = None
    estagio: str = "Prospecção"
    ultimo_contato: date | None = None
    proxima_acao: str | None = None
    proxima_data: date | None = None
    ticket: float | None = None
    probabilidade: int | None = None


class PipelineUpdate(BaseModel):
    nome: str | None = None
    origem: str | None = None
    tema: str | None = None
    estagio: str | None = None
    ultimo_contato: date | None = None
    proxima_acao: str | None = None
    proxima_data: date | None = None
    ticket: float | None = None
    probabilidade: int | None = None


class PipelineOut(PipelineCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ── Contatos ──────────────────────────────────────────────────────────────

class ContatoNotaCreate(BaseModel):
    texto: str
    evento_id: uuid.UUID | None = None
    data: date | None = None


class ContatoNotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    contato_id: uuid.UUID
    evento_id: uuid.UUID | None
    evento_nome: str | None = None
    texto: str
    data: date | None
    created_at: datetime


class ContatoCreate(BaseModel):
    primeiro_nome: str
    sobrenome: str | None = None
    empresa: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    mensagem_global: str | None = None
    evento_id: uuid.UUID | None = None  # opcional: vincula direto a um evento ao criar


class ContatoUpdate(BaseModel):
    primeiro_nome: str | None = None
    sobrenome: str | None = None
    empresa: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    mensagem_global: str | None = None


class ContatoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    primeiro_nome: str
    sobrenome: str | None
    empresa: str | None
    email: str | None
    whatsapp: str | None
    mensagem_global: str | None
    created_at: datetime
    updated_at: datetime
    notas: list[ContatoNotaOut] = []
    eventos: list[str] = []  # nomes dos eventos vinculados, preenchido no router


# ── Eventos ───────────────────────────────────────────────────────────────

class ConvidadoAdd(BaseModel):
    contato_id: uuid.UUID


class ConvidadoUpdate(BaseModel):
    presenca_confirmada: bool | None = None
    participacao_confirmada: bool | None = None
    mensagem_pessoal: str | None = None


class ConvidadoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    evento_id: uuid.UUID
    contato_id: uuid.UUID
    presenca_confirmada: bool
    participacao_confirmada: bool
    mensagem_pessoal: str | None
    contato: ContatoOut


class EventoCreate(BaseModel):
    nome: str
    data: date | None = None
    cohost: str | None = None
    custo: float | None = None
    receita: float | None = None
    mensagem_master: str | None = None
    dias_lembrete: int = 2


class EventoUpdate(BaseModel):
    nome: str | None = None
    data: date | None = None
    cohost: str | None = None
    custo: float | None = None
    receita: float | None = None
    reunioes: int | None = None
    propostas: int | None = None
    fechados: int | None = None
    mensagem_master: str | None = None
    dias_lembrete: int | None = None


class EventoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nome: str
    data: date | None
    cohost: str | None
    custo: float | None
    receita: float | None
    reunioes: int | None
    propostas: int | None
    fechados: int | None
    mensagem_master: str | None
    dias_lembrete: int
    created_at: datetime
    updated_at: datetime
    convidados: list[ConvidadoOut] = []


# ── Parceiros ─────────────────────────────────────────────────────────────

class ParceiroCreate(BaseModel):
    nome: str
    tipo: TipoParceiro
    status: StatusParceiro = "Frio"
    ultimo_encaminhamento: date | None = None
    plano: str | None = None
    proximo_contato: date | None = None


class ParceiroUpdate(BaseModel):
    nome: str | None = None
    tipo: TipoParceiro | None = None
    status: StatusParceiro | None = None
    ultimo_encaminhamento: date | None = None
    plano: str | None = None
    proximo_contato: date | None = None


class ParceiroOut(ParceiroCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ── Logs / Métricas ───────────────────────────────────────────────────────

class LogCreate(BaseModel):
    data: date
    numero: float
    nota: str | None = None


class LogOut(LogCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime


class MetricasOut(BaseModel):
    media_logs_7d: float
    total_contatos: int
    contatos_participaram_ao_menos_uma_vez: int
    contatos_reconvidados: int  # presentes em 2+ eventos
    contatos_reiterados: int  # participação confirmada em 2+ eventos


# ── IA ────────────────────────────────────────────────────────────────────

class MelhorarIARequest(BaseModel):
    campo: str
    texto: str


class MelhorarIAResponse(BaseModel):
    texto: str


# ── Anexos (biblioteca do módulo) ──────────────────────────────────────────

class AnexoLibOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nome_arquivo: str
    content_type: str | None
    created_at: datetime


# ── Disparo de e-mail ───────────────────────────────────────────────────────

ModoDisparo = Literal["individual", "bcc_unico"]


class DestinatarioDisparo(BaseModel):
    contato_id: uuid.UUID
    evento_id: uuid.UUID | None = None  # usado para resolver {evento} quando o contato pertence a vários


class DispararEmailRequest(BaseModel):
    destinatarios: list[DestinatarioDisparo]
    assunto: str
    corpo_template: str
    modo: ModoDisparo = "individual"
    evento_nome: str | None = None
    anexo_id: uuid.UUID | None = None


class DisparoResultadoItem(BaseModel):
    contato_id: uuid.UUID
    nome: str
    email: str | None
    sucesso: bool
    erro: str | None = None


class DispararEmailResponse(BaseModel):
    enviado_por: str  # e-mail usado como remetente (usuário ou master)
    resultados: list[DisparoResultadoItem]
