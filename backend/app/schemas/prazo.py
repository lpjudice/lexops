import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TipoPrazo = Literal[
    "contestacao", "recurso", "contrarrazoes", "manifestacao",
    "audiencia", "pericia", "outro"
]
TipoContagem = Literal["uteis", "corridos"]
StatusPrazo = Literal["pendente", "cumprido", "perdido", "ignorado", "nada_a_fazer"]


class PrazoBase(BaseModel):
    processo_id: uuid.UUID
    tipo: TipoPrazo
    descricao: str | None = None
    peca_necessaria: str | None = None
    responsavel: str | None = None
    responsavel_id: uuid.UUID | None = None
    data_publicacao: date
    dias_prazo: int
    tipo_contagem: TipoContagem = "uteis"
    status: StatusPrazo = "pendente"


class PrazoCreate(PrazoBase):
    pass


class PrazoUpdate(BaseModel):
    # Editável: o prazo pode ter nascido vinculado ao processo errado (match
    # automático de CNJ na publicação), e antes disso não havia como corrigir.
    processo_id: uuid.UUID | None = None
    tipo: TipoPrazo | None = None
    descricao: str | None = None
    peca_necessaria: str | None = None
    responsavel: str | None = None
    responsavel_id: uuid.UUID | None = None
    data_publicacao: date | None = None
    dias_prazo: int | None = None
    tipo_contagem: TipoContagem | None = None
    status: StatusPrazo | None = None


class TarefaVinculada(BaseModel):
    id: uuid.UUID
    titulo: str


class PublicacaoOrigem(BaseModel):
    """Publicação (Diário Oficial ou Recorte Digital) que originou o prazo —
    devolvida junto pra tela de Prazos poder voltar à origem sem outra chamada."""
    id: uuid.UUID
    fonte: str
    origem_menu: Literal["diario", "recorte"]
    data_publicacao: date
    numero_cnj: str | None = None
    tribunal: str | None = None
    texto_resumo: str | None = None
    url_fonte: str | None = None
    disposicao: str | None = None


class PrazoOut(PrazoBase):
    id: uuid.UUID
    data_limite: date | None
    data_limite_sem_feriado: date | None
    peca_necessaria: str | None
    responsavel: str | None
    responsavel_id: uuid.UUID | None = None
    google_event_id: str | None
    criado_automaticamente: bool = False
    tarefas_vinculadas: list[TarefaVinculada] = []
    peca_doc_url: str | None = None
    publicacao_origem: PublicacaoOrigem | None = None
    ultimo_lembrete_em: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
