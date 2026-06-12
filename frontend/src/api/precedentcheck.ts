import api from './client'

export type StatusCitacao = 'pendente' | 'verificado' | 'divergencia' | 'nao_encontrado' | 'parcial'

export interface DimensaoResult {
  resultado: 'ok' | 'divergencia' | 'nao_encontrado' | 'inconclusivo' | 'adequado_com_ressalvas'
  detalhe: string
}

export interface CitacaoVerificada {
  tribunal: string
  numero: string
  relator?: string
  data?: string
  trecho_citado?: string
  contexto_na_peca?: string
  verificado: boolean
  status_geral: StatusCitacao
  numero_existe?: DimensaoResult
  relator_correto?: DimensaoResult
  data_procede?: DimensaoResult
  trecho_literal?: DimensaoResult
  voto_vencedor?: DimensaoResult
  contexto_compativel?: DimensaoResult
  ratio_fit?: DimensaoResult
  ementa_real?: string | null
  link_inteiro_teor?: string | null
  decisoes_mesmo_sentido?: { referencia: string; ementa: string; link?: string }[]
  decisoes_sentido_contrario?: { referencia: string; ementa: string; link?: string }[]
  custo_usd?: number
}

export interface AnaliseResumida {
  id: string
  titulo?: string | null
  total_citacoes: number
  total_ok: number
  total_divergencia: number
  total_nao_encontrado: number
  arquivado: boolean
  custo_usd?: number
  created_at: string
}

export interface AnaliseCompleta extends AnaliseResumida {
  texto_peca: string
  citacoes: CitacaoVerificada[]
}

export const precedentCheckApi = {
  extrairPdf: (file: File) => {
    const fd = new FormData()
    fd.append('arquivo', file)
    return api.post<{ texto: string }>('/precedentcheck/extrair-pdf', fd).then((r) => r.data)
  },

  analisar: (body: { texto: string; titulo?: string; cliente_id?: string; processo_id?: string }) =>
    api.post<{ analise_id: string; total_citacoes: number; citacoes: CitacaoVerificada[] }>(
      '/precedentcheck/analisar',
      body,
    ).then((r) => r.data),

  verificarCitacao: (analise_id: string, idx: number) =>
    api.post<CitacaoVerificada>(`/precedentcheck/verificar/${analise_id}/${idx}`).then((r) => r.data),

  listarHistorico: (arquivado = false) =>
    api.get<AnaliseResumida[]>(`/precedentcheck/historico?arquivado=${arquivado}`).then((r) => r.data),

  obterAnalise: (id: string) =>
    api.get<AnaliseCompleta>(`/precedentcheck/historico/${id}`).then((r) => r.data),

  patch: (id: string, body: { titulo?: string; arquivado?: boolean }) =>
    api.patch<AnaliseResumida>(`/precedentcheck/historico/${id}`, body).then((r) => r.data),

  deletar: (id: string) =>
    api.delete(`/precedentcheck/historico/${id}`).then((r) => r.data),
}
