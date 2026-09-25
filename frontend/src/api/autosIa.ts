import api from './client'

export type StatusCaso = 'ativo' | 'arquivado'
export type StatusDocumento = 'pendente' | 'processando' | 'concluido' | 'erro'
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

export interface Caso {
  id: string
  nome: string
  numero_processo?: string | null
  descricao?: string | null
  status: StatusCaso
  total_paginas: number
  tem_peca_pendente_continuacao: boolean
  criado_em: string
  atualizado_em: string
}

export interface CasoResumo extends Caso {
  total_pecas: number
  total_documentos: number
  total_perguntas_faq: number
}

export interface Documento {
  id: string
  caso_id: string
  nome_arquivo: string
  pagina_inicio: number
  pagina_fim: number
  status: StatusDocumento
  erro_mensagem?: string | null
  pecas_geradas: number
  paginas_ocr: number
  criado_em: string
}

export interface Peca {
  id: string
  caso_id: string
  documento_id?: string | null
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
  criado_em: string
}

export interface PecaDetalhe extends Peca {
  texto_md: string
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

  criarCaso: (data: { nome: string; numero_processo?: string; descricao?: string }) =>
    api.post<Caso>('/autos-ia/casos', data).then((r) => r.data),

  obterCaso: (casoId: string) => api.get<Caso>(`/autos-ia/casos/${casoId}`).then((r) => r.data),

  atualizarCaso: (casoId: string, data: Partial<Pick<Caso, 'nome' | 'numero_processo' | 'descricao' | 'status'>>) =>
    api.patch<Caso>(`/autos-ia/casos/${casoId}`, data).then((r) => r.data),

  deletarCaso: (casoId: string) => api.delete(`/autos-ia/casos/${casoId}`),

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

  listarPecas: (casoId: string, params: { q?: string; tipo?: string; data_inicio?: string; data_fim?: string }) =>
    api.get<Peca[]>(`/autos-ia/casos/${casoId}/pecas`, { params }).then((r) => r.data),

  obterPeca: (pecaId: string) => api.get<PecaDetalhe>(`/autos-ia/pecas/${pecaId}`).then((r) => r.data),

  obterGrafo: (casoId: string) => api.get<Grafo>(`/autos-ia/casos/${casoId}/grafo`).then((r) => r.data),

  listarFaq: (casoId: string) => api.get<FaqPergunta[]>(`/autos-ia/casos/${casoId}/faq`).then((r) => r.data),

  perguntar: (casoId: string, pergunta: string) =>
    api.post<FaqPergunta>(`/autos-ia/casos/${casoId}/faq`, { pergunta }, { timeout: 120000 }).then((r) => r.data),

  reprocessarPergunta: (perguntaId: string) =>
    api.post<FaqPergunta>(`/autos-ia/faq/${perguntaId}/reprocessar`, {}, { timeout: 120000 }).then((r) => r.data),

  deletarPergunta: (perguntaId: string) => api.delete(`/autos-ia/faq/${perguntaId}`),
}
