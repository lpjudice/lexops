import api from './client'

export interface Andamento {
  id: string
  processo_id: string
  data_andamento: string | null  // YYYY-MM-DD
  descricao: string
  tipo: string | null
  fonte: string | null
  grau: string | null
  lido: boolean
  notificado: boolean
  created_at: string
}

export interface SincronizacaoResult {
  processo_id: string
  tribunal: string | null
  status: 'ok' | 'erro' | 'nenhum'
  novos_andamentos: number
  mensagem: string | null
  ultimo_andamento_data?: string | null   // YYYY-MM-DD
}

export interface AndamentoCount {
  total: number
  nao_lidos: number
}

export const andamentosApi = {
  listar: (processoId: string, limit = 10, offset = 0, fonte?: string) =>
    api
      .get<Andamento[]>(`/andamentos/processo/${processoId}`, { params: { limit, offset, fonte } })
      .then((r) => r.data),

  contar: (processoId: string, fonte?: string) =>
    api.get<AndamentoCount>(`/andamentos/processo/${processoId}/count`, { params: { fonte } }).then((r) => r.data),

  marcarLidos: (processoId: string) =>
    api.post(`/andamentos/processo/${processoId}/marcar-lidos`),

  sincronizar: (processoId: string) =>
    api
      .post<SincronizacaoResult>(`/andamentos/processo/${processoId}/sincronizar`)
      .then((r) => r.data),

  sincronizarBatch: (processoIds: string[]) =>
    api
      .post<SincronizacaoResult[]>('/andamentos/sincronizar-batch', { processo_ids: processoIds })
      .then((r) => r.data),

  sincronizarJusBR: (processoId: string, token: string) =>
    api
      .post<SincronizacaoResult>(`/andamentos/processo/${processoId}/sincronizar-jusbr`, { token })
      .then((r) => r.data),

  sincronizarBatchJusBR: (processoIds: string[], token: string) =>
    api
      .post<SincronizacaoResult[]>('/andamentos/sincronizar-batch-jusbr', { processo_ids: processoIds, token })
      .then((r) => r.data),

  importarJusBR: (processoId: string, payload: string) =>
    api
      .post<SincronizacaoResult>(`/andamentos/processo/${processoId}/importar-jusbr`, { payload })
      .then((r) => r.data),
}
