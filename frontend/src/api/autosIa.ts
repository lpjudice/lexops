import api, { getToken } from './client'

export type StatusCaso = 'ativo' | 'arquivado'
export type StatusDocumento = 'pendente' | 'processando' | 'concluido' | 'erro' | 'cancelado'
export type StatusPeca = 'pendente_resumo' | 'resumida' | 'erro'
export type StatusFaq = 'pendente' | 'respondida' | 'erro'
export type TipoPeca =
  | 'peticao' | 'decisao' | 'despacho' | 'certidao' | 'oficio' | 'recurso' | 'documento' | 'outro'

export const TIPOS_PECA: { value: TipoPeca; label: string }[] = [
  { value: 'peticao', label: 'Petição' },
  { value: 'decisao', label: 'Decisão' },
  { value: 'despacho', label: 'Despacho' },
  { value: 'certidao', label: 'Certidão' },
  { value: 'oficio', label: 'Ofício' },
  { value: 'recurso', label: 'Recurso' },
  { value: 'documento', label: 'Documento' },
  { value: 'outro', label: 'Outro' },
]

export type StatusSync = 'ok' | 'erro' | 'nenhum' | 'processando' | 'cancelado'
export type EtapaSync = 'lendo' | 'resumindo'

export interface Caso {
  id: string
  nome: string
  numero_processo?: string | null
  descricao?: string | null
  status: StatusCaso
  total_paginas: number
  tem_peca_pendente_continuacao: boolean
  processo_id?: string | null
  sync_jusbr_ativo: boolean
  ultima_sincronizacao_em?: string | null
  ultimo_sync_status?: StatusSync | null
  ultimo_sync_mensagem?: string | null
  sync_etapa?: EtapaSync | null
  sync_total_itens?: number | null
  sync_itens_processados?: number | null
  sync_iniciado_em?: string | null
  custo_usd_total: number
  criado_em: string
  atualizado_em: string
}

export interface CasoResumo extends Caso {
  total_pecas: number
  total_documentos: number
  total_perguntas_faq: number
}

export interface EstimativaProcessamento {
  pecas_estimadas: number
  custo_estimado_usd: number
  tempo_estimado_minutos: number
}

export interface EstimativaImportacao {
  itens_pendentes: number
  custo_estimado_usd: number
  tempo_estimado_minutos: number
}

export interface Documento {
  id: string
  caso_id: string
  nome_arquivo: string
  pagina_inicio: number
  pagina_fim: number
  total_paginas: number
  status: StatusDocumento
  erro_mensagem?: string | null
  pecas_geradas: number
  paginas_ocr: number
  etapa?: string | null
  paginas_processadas: number
  pecas_resumidas: number
  custo_usd: number
  estimativa: EstimativaProcessamento
  criado_em: string
}

export type OrigemPeca = 'upload' | 'jusbr'

export interface Peca {
  id: string
  caso_id: string
  documento_id?: string | null
  andamento_id?: string | null
  peca_pai_id?: string | null
  origem: OrigemPeca
  total_anexos: number
  tipo: TipoPeca
  titulo: string
  autor?: string | null
  data_peca?: string | null
  id_processual?: string | null
  pagina_inicio: number
  pagina_fim: number
  resumo?: string | null
  keywords?: string[] | null
  ids_mencionados?: string[] | null
  status: StatusPeca
  erro_mensagem?: string | null
  custo_usd: number
  criado_em: string
}

export interface PecaDetalhe extends Peca {
  texto_md: string
}

export interface DocumentoDriveAnexo {
  id: string
  tipo: TipoPeca
  titulo: string
  resumo?: string | null
  autor?: string | null
  data_peca?: string | null
  protocolado_em?: string | null
  status: StatusPeca
  arquivo_nome?: string | null
  arquivo_drive_link?: string | null
  nome_indexado?: string | null
  nota_usuario?: string | null
  keywords_usuario?: string[] | null
  titulo_customizado?: string | null
}

export interface DocumentoDrive extends DocumentoDriveAnexo {
  anexos: DocumentoDriveAnexo[]
}

export interface GrafoNo {
  id: string
  tipo: TipoPeca
  titulo: string
  autor?: string | null
  data_peca?: string | null
  id_processual?: string | null
  resumo?: string | null
  keywords?: string[] | null
  pagina_inicio: number
  pagina_fim: number
  peca_pai_id?: string | null
}

export interface GrafoAresta {
  id: string
  peca_origem_id: string
  peca_destino_id?: string | null
  id_mencionado: string
}

export interface Grafo {
  nos: GrafoNo[]
  arestas: GrafoAresta[]
}

export interface FaqPergunta {
  id: string
  caso_id: string
  pergunta: string
  resposta?: string | null
  pecas_relacionadas?: string[] | null
  status: StatusFaq
  erro_mensagem?: string | null
  criado_em: string
}

export const autosIa = {
  listarCasos: () => api.get<CasoResumo[]>('/autos-ia/casos').then((r) => r.data),

  criarCaso: (data: {
    nome: string
    numero_processo?: string
    descricao?: string
    processo_id?: string
    sync_jusbr_ativo?: boolean
  }) => api.post<Caso>('/autos-ia/casos', data).then((r) => r.data),

  obterCaso: (casoId: string) => api.get<Caso>(`/autos-ia/casos/${casoId}`).then((r) => r.data),

  atualizarCaso: (
    casoId: string,
    data: Partial<Pick<Caso, 'nome' | 'numero_processo' | 'descricao' | 'status' | 'processo_id' | 'sync_jusbr_ativo'>>,
  ) => api.patch<Caso>(`/autos-ia/casos/${casoId}`, data).then((r) => r.data),

  deletarCaso: (casoId: string) => api.delete(`/autos-ia/casos/${casoId}`),

  sincronizarAgora: (casoId: string) =>
    api.post<Caso>(`/autos-ia/casos/${casoId}/sincronizar`).then((r) => r.data),

  importarExistentes: (casoId: string) =>
    api.post<Caso>(`/autos-ia/casos/${casoId}/importar-existentes`).then((r) => r.data),

  estimativaImportacao: (casoId: string) =>
    api.get<EstimativaImportacao>(`/autos-ia/casos/${casoId}/estimativa-importacao`).then((r) => r.data),

  cancelarSync: (casoId: string) =>
    api.post<Caso>(`/autos-ia/casos/${casoId}/cancelar-sync`).then((r) => r.data),

  atualizarMetadados: (casoId: string) =>
    api.post<Caso>(`/autos-ia/casos/${casoId}/atualizar-metadados`).then((r) => r.data),

  reagrupar: (casoId: string) =>
    api.post<Caso>(`/autos-ia/casos/${casoId}/reagrupar`).then((r) => r.data),

  estimativaReclassificacao: (casoId: string) =>
    api.get<EstimativaImportacao>(`/autos-ia/casos/${casoId}/estimativa-reclassificacao`).then((r) => r.data),

  reclassificar: (casoId: string) =>
    api.post<Caso>(`/autos-ia/casos/${casoId}/reclassificar`).then((r) => r.data),

  enviarBloco: (casoId: string, arquivo: File, paginaInicio: number | null, onProgress?: (pct: number) => void) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    if (paginaInicio != null) fd.append('pagina_inicio', String(paginaInicio))
    return api.post<Documento>(`/autos-ia/casos/${casoId}/upload`, fd, {
      headers: { 'Content-Type': undefined },
      timeout: 10 * 60 * 1000,
      onUploadProgress: (evt) => {
        if (onProgress && evt.total) onProgress(Math.round((evt.loaded / evt.total) * 100))
      },
    }).then((r) => r.data)
  },

  listarDocumentos: (casoId: string) =>
    api.get<Documento[]>(`/autos-ia/casos/${casoId}/documentos`).then((r) => r.data),

  cancelarDocumento: (documentoId: string) =>
    api.post<Documento>(`/autos-ia/documentos/${documentoId}/cancelar`).then((r) => r.data),

  retomarDocumento: (documentoId: string) =>
    api.post<Documento>(`/autos-ia/documentos/${documentoId}/retomar`).then((r) => r.data),

  listarPecas: (
    casoId: string,
    params: {
      q?: string; tipo?: string; data_inicio?: string; data_fim?: string; incluir_anexos?: boolean
      offset?: number; limit?: number
    },
  ) => api.get<Peca[]>(`/autos-ia/casos/${casoId}/pecas`, { params }).then((r) => r.data),

  obterPeca: (pecaId: string) => api.get<PecaDetalhe>(`/autos-ia/pecas/${pecaId}`).then((r) => r.data),

  listarDocumentosDrive: (
    casoId: string,
    params: { q?: string; ordem?: 'asc' | 'desc'; offset?: number; limit?: number },
  ) => api.get<DocumentoDrive[]>(`/autos-ia/casos/${casoId}/documentos-drive`, { params }).then((r) => r.data),

  atualizarTipoPeca: (pecaId: string, tipo: TipoPeca) =>
    api.patch<Peca>(`/autos-ia/pecas/${pecaId}/tipo`, { tipo }).then((r) => r.data),

  atualizarAnotacaoPeca: (
    pecaId: string,
    data: { nota_usuario?: string | null; keywords_usuario?: string[] | null; titulo_customizado?: string | null },
  ) => api.patch<Peca>(`/autos-ia/pecas/${pecaId}/anotacao`, data).then((r) => r.data),

  listarAnexos: (pecaId: string) => api.get<Peca[]>(`/autos-ia/pecas/${pecaId}/anexos`).then((r) => r.data),

  urlDownloadPecas: (casoId: string, opts: { apenasPrincipais?: boolean; tipo?: string } = {}) => {
    const params = new URLSearchParams()
    params.set('apenas_principais', String(opts.apenasPrincipais ?? true))
    if (opts.tipo) params.set('tipo', opts.tipo)
    const token = getToken()
    if (token) params.set('token', token)
    return `/api/autos-ia/casos/${casoId}/pecas/download?${params.toString()}`
  },

  obterGrafo: (casoId: string) => api.get<Grafo>(`/autos-ia/casos/${casoId}/grafo`).then((r) => r.data),

  listarFaq: (casoId: string) => api.get<FaqPergunta[]>(`/autos-ia/casos/${casoId}/faq`).then((r) => r.data),

  perguntar: (casoId: string, pergunta: string) =>
    api.post<FaqPergunta>(`/autos-ia/casos/${casoId}/faq`, { pergunta }, { timeout: 120000 }).then((r) => r.data),

  reprocessarPergunta: (perguntaId: string) =>
    api.post<FaqPergunta>(`/autos-ia/faq/${perguntaId}/reprocessar`, {}, { timeout: 120000 }).then((r) => r.data),

  deletarPergunta: (perguntaId: string) => api.delete(`/autos-ia/faq/${perguntaId}`),
}
