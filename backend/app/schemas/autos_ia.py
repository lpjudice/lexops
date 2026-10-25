import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, computed_field, field_validator

TipoPeca = Literal[
    "peticao", "decisao", "despacho", "certidao", "oficio", "recurso", "documento", "outro"
]


class CasoCreate(BaseModel):
    nome: str
    numero_processo: str | None = None
    descricao: str | None = None
    processo_id: uuid.UUID | None = None
    sync_jusbr_ativo: bool = False


class CasoUpdate(BaseModel):
    nome: str | None = None
    numero_processo: str | None = None
    descricao: str | None = None
    status: Literal["ativo", "arquivado"] | None = None
    processo_id: uuid.UUID | None = None
    sync_jusbr_ativo: bool | None = None


class CasoOut(BaseModel):
    id: uuid.UUID
    nome: str
    numero_processo: str | None
    descricao: str | None
    status: str
    total_paginas: int
    tem_peca_pendente_continuacao: bool
    processo_id: uuid.UUID | None
    sync_jusbr_ativo: bool
    ultima_sincronizacao_em: datetime | None
    ultimo_sync_status: str | None
    ultimo_sync_mensagem: str | None
    sync_etapa: str | None
    sync_total_itens: int | None
    sync_itens_processados: int | None
    sync_iniciado_em: datetime | None
    sync_detalhe: str | None
    custo_usd_total: float
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class CasoResumo(CasoOut):
    total_pecas: int = 0
    total_documentos: int = 0
    total_perguntas_faq: int = 0


class DocumentoOut(BaseModel):
    id: uuid.UUID
    caso_id: uuid.UUID
    nome_arquivo: str
    pagina_inicio: int
    pagina_fim: int
    status: str
    erro_mensagem: str | None
    pecas_geradas: int
    paginas_ocr: int
    etapa: str | None
    paginas_processadas: int
    pecas_resumidas: int
    custo_usd: float
    criado_em: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_paginas(self) -> int:
        return self.pagina_fim - self.pagina_inicio + 1

    @computed_field  # type: ignore[prop-decorator]
    @property
    def estimativa(self) -> dict:
        from app.services.autos_ia.estimativa import estimar_processamento
        return estimar_processamento(self.total_paginas)


OrigemPeca = Literal["upload", "jusbr"]


class PecaOut(BaseModel):
    id: uuid.UUID
    caso_id: uuid.UUID
    documento_id: uuid.UUID | None
    andamento_id: uuid.UUID | None
    peca_pai_id: uuid.UUID | None
    tipo: str
    titulo: str
    autor: str | None
    data_peca: date | None
    id_processual: str | None
    pagina_inicio: int
    pagina_fim: int
    resumo: str | None
    keywords: list[str] | None
    ids_mencionados: list[str] | None
    status: str
    erro_mensagem: str | None
    custo_usd: float
    criado_em: datetime
    total_anexos: int = 0

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def origem(self) -> OrigemPeca:
        return "jusbr" if self.andamento_id else "upload"


class PecaDetalheOut(PecaOut):
    texto_md: str


class DocumentoDriveAnexoOut(BaseModel):
    """Uma peça (ou anexo) na listagem compacta de Documentos — nome do arquivo
    + link pro Drive, sem o texto/keywords completos (a lista pode ter
    centenas de linhas, e essa tela é pra reconhecer documentos pelo nome/
    resumo curto, não pra ler cada um)."""
    id: uuid.UUID
    tipo: str
    titulo: str
    resumo: str | None
    autor: str | None
    data_peca: date | None
    protocolado_em: datetime | None
    id_processual: str | None
    status: str
    erro_mensagem: str | None
    arquivo_nome: str | None
    arquivo_drive_link: str | None
    nome_indexado: str | None
    nota_usuario: str | None
    keywords_usuario: list[str] | None
    titulo_customizado: str | None
    advogado_responsavel: str | None = None

    model_config = {"from_attributes": True}


class DocumentoDriveOut(DocumentoDriveAnexoOut):
    anexos: list[DocumentoDriveAnexoOut] = []


class PecaTipoUpdate(BaseModel):
    tipo: TipoPeca


class PecaAnotacaoUpdate(BaseModel):
    """Atualização parcial — só os campos enviados são alterados (permite
    limpar um campo mandando null explicitamente, sem mexer nos outros)."""
    nota_usuario: str | None = None
    keywords_usuario: list[str] | None = None
    titulo_customizado: str | None = None
    advogado_responsavel: str | None = None

    @field_validator("advogado_responsavel")
    @classmethod
    def _normaliza_advogado(cls, v: str | None) -> str | None:
        # Espaços nas pontas e duplicados no meio virariam "advogados" distintos
        # no filtro do grafo; vazio vira null (limpa o campo).
        if v is None:
            return None
        v = " ".join(v.split())
        return v[:255] or None


class GrafoNo(BaseModel):
    id: uuid.UUID
    tipo: str
    titulo: str
    autor: str | None
    data_peca: date | None
    id_processual: str | None
    resumo: str | None
    keywords: list[str] | None
    pagina_inicio: int
    pagina_fim: int
    peca_pai_id: uuid.UUID | None = None
    arquivo_drive_link: str | None = None
    status: str
    erro_mensagem: str | None = None
    advogado_responsavel: str | None = None


class GrafoAresta(BaseModel):
    id: uuid.UUID
    peca_origem_id: uuid.UUID
    peca_destino_id: uuid.UUID | None
    id_mencionado: str


class GrafoOut(BaseModel):
    nos: list[GrafoNo]
    arestas: list[GrafoAresta]


class EstimativaImportacaoOut(BaseModel):
    itens_pendentes: int
    custo_estimado_usd: float
    tempo_estimado_minutos: float


class FaqPerguntaCreate(BaseModel):
    pergunta: str


class FaqPerguntaOut(BaseModel):
    id: uuid.UUID
    caso_id: uuid.UUID
    pergunta: str
    resposta: str | None
    pecas_relacionadas: list[str] | None
    status: str
    erro_mensagem: str | None
    custo_usd: float = 0
    criado_em: datetime

    model_config = {"from_attributes": True}


class PeticaoRefOut(BaseModel):
    """Referência a uma petição: o ID processual leva ao PDF (ou, sem PDF, ao .md) no Drive."""
    peca_id: uuid.UUID
    id_processual: str | None = None
    data: date | None = None
    titulo: str
    link_pdf: str | None = None
    link_md: str | None = None


class AdvPessoaOut(BaseModel):
    id: str                       # OAB "cabeça" da pessoa (chave estável)
    nome: str | None = None
    oabs: list[str]


class ParteDoAdvogadoOut(BaseModel):
    chave: str
    nome: str
    variantes: list[str] = []
    principal: bool = False        # marcado à mão como o advogado principal desta parte
    manual: bool = False           # adicionado à mão (sem petição que o ligue a esta parte)
    peticoes: list[PeticaoRefOut]


class AdvogadoRelacaoOut(AdvPessoaOut):
    manual: bool = False
    total_peticoes: int
    partes: list[ParteDoAdvogadoOut]


class AdvogadoDaParteOut(AdvPessoaOut):
    principal: bool = False
    sugerido: bool = False         # nenhum principal marcado: o de mais petições nesta parte
    manual: bool = False
    peticoes: list[PeticaoRefOut]


class ParteRelacaoOut(BaseModel):
    chave: str
    nome: str
    variantes: list[str] = []
    total_peticoes: int
    peticoes: list[PeticaoRefOut] = []        # todas as petições da parte, com ou sem advogado
    advogados: list[AdvogadoDaParteOut]
    removidos: list[AdvPessoaOut] = []        # vínculos removidos à mão (dá para restaurar)


class PeticaoSemAdvogadoOut(BaseModel):
    # sem_texto: arquivo não lido · texto_incompleto: texto cortado (assinatura ficou de fora) ·
    # ministerio_publico / administrador_judicial: quem assina não é advogado · sem_oab: sem OAB no texto
    motivo: Literal["sem_texto", "texto_incompleto", "ministerio_publico", "administrador_judicial", "sem_oab"]
    parte: str | None = None
    assinante: str | None = None
    peticao: PeticaoRefOut


class RelacaoResumoOut(BaseModel):
    peticoes_total: int
    peticoes_sem_texto: int
    peticoes_com_advogado: int
    peticoes_sem_advogado: int
    eventos_sem_arquivo: int = 0   # protocolos "Petição" sem documento — não são a petição em si
    advogados: int
    partes: int


class RenomearAdvogadoIn(BaseModel):
    adv_id: str
    nome: str


class AdicionarAdvogadoIn(BaseModel):
    parte_chave: str
    nome: str
    oab: str | None = None


class PrincipalIn(BaseModel):
    parte_chave: str
    adv_id: str | None = None      # None = desmarca o principal


class VinculoIn(BaseModel):
    parte_chave: str
    adv_id: str


class AdvogadosPartesOut(BaseModel):
    resumo: RelacaoResumoOut
    advogados: list[AdvogadoRelacaoOut]
    partes: list[ParteRelacaoOut]
    sem_advogado: list[PeticaoSemAdvogadoOut]


class PastasDriveOut(BaseModel):
    """Links das pastas do caso no Drive (None = a pasta ainda não existe)."""
    processo: str | None = None   # pasta do processo — raiz das duas abaixo
    pdfs: str | None = None       # "Andamentos" (PDFs / peças originais)
    md: str | None = None         # "Andamentos (MD)" (resumo + inteiro teor)


class ExportMdStatusOut(BaseModel):
    """Exportação do resumo + inteiro teor das peças (.md) para o Drive."""
    estado: Literal["ocioso", "rodando", "concluido", "erro"]
    total: int
    exportadas: int
    feitos: int = 0
    enviados: int = 0
    ignorados: int = 0
    erros: int = 0
    mensagem: str | None = None
    pasta_nome: str
    pasta_link: str | None = None


class AlertaConfigOut(BaseModel):
    ativo: bool
    # Destinatário padrão: usuário(s) master do sistema (não editável aqui).
    email_padrao: list[str]
    emails_extras: list[str]


class AlertaConfigUpdate(BaseModel):
    ativo: bool | None = None
    emails_extras: list[str] | None = None


# ── Banco de fatos: valores (R$) e reconciliador ─────────────────────────────

class FatoValorOut(BaseModel):
    id: uuid.UUID
    valor_centavos: int
    valor: str
    rotulo_original: str | None = None
    tema: str | None = None
    tema_rotulo: str
    sujeito: str | None = None
    sujeito_canonico: str | None = None
    natureza: str | None = None
    fonte_citada: str | None = None
    data_ref: str | None = None
    trecho: str | None = None
    confianca: float | None = None
    status: str
    nota: str | None = None
    ocorrencias: int = 1
    afirmante: str
    afirmante_chave: str
    peticao: PeticaoRefOut


class FatosValoresListaOut(BaseModel):
    total: int
    itens: list[FatoValorOut]


class FatosValoresStatusOut(BaseModel):
    estado: Literal["ocioso", "rodando", "concluido", "erro"]
    total_fatos: int
    validados: int
    pecas_com_fatos: int
    pecas_pendentes: int
    total: int = 0
    feitos: int = 0
    fatos_novos: int = 0
    erros: int = 0
    custo_usd: float = 0.0
    mensagem: str | None = None


class ReconValorOut(BaseModel):
    valor_centavos: int
    valor: str
    afirmantes: list[str]
    fatos: list[FatoValorOut]


class DivergenciaOut(BaseModel):
    tema: str
    tema_rotulo: str
    sujeito: str | None = None
    valores: list[ReconValorOut]
    afirmantes: list[str]
    razao: float | None = None
    n_fatos: int


class CorroboracaoValorOut(BaseModel):
    valor_centavos: int
    valor: str
    n_pecas: int
    afirmantes: list[str]
    temas: list[str]
    sujeitos: list[str]
    fatos: list[FatoValorOut]


class ReconciliacaoOut(BaseModel):
    resumo: dict
    divergencias: list[DivergenciaOut]
    corroboracoes: list[CorroboracaoValorOut]


class FatoValorUpdateIn(BaseModel):
    tema: str | None = None
    sujeito_canonico: str | None = None
    status: Literal["extraido", "validado", "rejeitado"] | None = None
    nota: str | None = None


class RenomearSujeitoIn(BaseModel):
    de: str
    para: str


class AnexoCorroboracaoOut(BaseModel):
    peca_id: uuid.UUID
    id_processual: str | None = None
    titulo: str | None = None
    tipo_pje: str | None = None
    data: date | None = None
    link_pdf: str | None = None
    link_md: str | None = None
    ocorrencias: int
    trecho: str


class TemaOut(BaseModel):
    chave: str
    rotulo: str


# ── Banco de fatos: determinações do Juízo e quadro de cumprimento ───────────

class DeterminacaoOut(BaseModel):
    id: uuid.UUID
    ordem: str | None = None
    capitulo: str | None = None
    destinatario: str | None = None
    destinatario_tipo: str | None = None
    destinatario_rotulo: str
    acao: str | None = None
    tema: str | None = None
    tema_rotulo: str
    prazo_dias: int | None = None
    prazo_tipo: str | None = None
    prazo_condicao: str | None = None
    sancao: str | None = None
    ligada_a_mediacao: bool = False
    trecho: str | None = None
    decisao_data: str | None = None
    intimacao_data: str | None = None
    vencimento: str | None = None
    vencimento_estimado: bool = True
    vencimento_motivo: str | None = None
    dias_para_vencer: int | None = None
    status_ia: str | None = None
    status_manual: str | None = None
    status: str
    justificativa: str | None = None
    nota: str | None = None
    confianca: float | None = None
    validado: bool = False
    evidencias: list[PeticaoRefOut] = []
    decisao: PeticaoRefOut


class DeterminacoesListaOut(BaseModel):
    total: int
    resumo: dict[str, int]
    itens: list[DeterminacaoOut]


class DeterminacoesStatusOut(BaseModel):
    estado: Literal["ocioso", "rodando", "concluido", "erro"]
    total_determinacoes: int
    atos_pendentes: int
    total: int = 0
    feitos: int = 0
    novas: int = 0
    erros: int = 0
    custo_usd: float = 0.0
    mensagem: str | None = None


class DeterminacaoUpdateIn(BaseModel):
    status_manual: str | None = None     # cumprida | parcial | nao_localizada | em_prazo | prejudicada | nao_aplicavel | automatico
    nota: str | None = None
    rejeitar: bool = False
    validar: bool | None = None


class IntimacaoIn(BaseModel):
    data: str | None = None              # AAAA-MM-DD; nulo volta a contar da data da decisão


class MinutaOut(BaseModel):
    markdown: str


class OpcoesDeterminacoesOut(BaseModel):
    destinatarios: list[TemaOut]
    temas: list[TemaOut]
    status: list[TemaOut]
