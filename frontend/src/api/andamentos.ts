import api, { getToken } from './client'

export interface Andamento {
  id: string
  processo_id: string
  data_andamento: string | null  // YYYY-MM-DD
  descricao: string
  tipo: string | null
  fonte: string | null
  grau: string | null
  arquivo_nome: string | null
  arquivo_drive_link: string | null
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
  documentos_baixados?: number             // arquivos enviados ao Drive nesta sync
  documentos_total?: number                // total de arquivos detectados no processo
}

export interface JusbrSyncJobStart {
  job_id: string
}

export interface JusbrSyncJobStatus {
  job_id: string
  status: 'rodando' | 'concluido' | 'erro'
  stage: string
  message: string | null
  total: number
  processed: number
  uploaded: number
  result: SincronizacaoResult | null
  error: string | null
  started_at: string
  updated_at: string
}

export interface JusbrBatchJobStatus {
  job_id: string
  status: 'rodando' | 'concluido' | 'erro'
  stage: string
  message: string | null
  total: number
  processed: number
  current_index: number
  current_cnj: string | null
  current_total: number
  current_processed: number
  current_uploaded: number
  results: SincronizacaoResult[]
  error: string | null
  started_at: string
  updated_at: string
}

export interface AndamentoCount {
  total: number
  nao_lidos: number
}

export interface RelatorioLoteItem {
  processo_id: string
  novos: number
}

export interface RelatorioLoteResult {
  drive_link: string | null
  filename: string
  pdf_base64: string
}

export interface JusbrSessionStatus {
  active: boolean
  expires_at: string | null
  detected_url: string | null
  capture_kind: string | null
  has_refresh_token: boolean
  has_cookies: boolean
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

  gerarRelatorioLote: (items: RelatorioLoteItem[]) =>
    api
      .post<RelatorioLoteResult>('/andamentos/relatorio-lote', { items })
      .then((r) => r.data),

  sincronizarJusBR: (processoId: string, token?: string) =>
    api
      .post<SincronizacaoResult>(`/andamentos/processo/${processoId}/sincronizar-jusbr`, { token })
      .then((r) => r.data),

  iniciarSincronizacaoJusBR: (processoId: string, token?: string) =>
    api
      .post<JusbrSyncJobStart>(`/andamentos/processo/${processoId}/sincronizar-jusbr-job`, { token })
      .then((r) => r.data),

  statusSincronizacaoJusBR: (jobId: string) =>
    api.get<JusbrSyncJobStatus>(`/andamentos/sincronizar-jusbr-job/${jobId}`).then((r) => r.data),

  sincronizarBatchJusBR: (processoIds: string[], token?: string) =>
    api
      .post<SincronizacaoResult[]>('/andamentos/sincronizar-batch-jusbr', { processo_ids: processoIds, token })
      .then((r) => r.data),

  iniciarSincronizacaoBatchJusBR: (processoIds: string[], token?: string) =>
    api
      .post<JusbrSyncJobStart>('/andamentos/sincronizar-batch-jusbr-job', { processo_ids: processoIds, token })
      .then((r) => r.data),

  statusSincronizacaoBatchJusBR: (jobId: string) =>
    api
      .get<JusbrBatchJobStatus>(`/andamentos/sincronizar-batch-jusbr-job/${jobId}`)
      .then((r) => r.data),

  obterSessaoJusBR: () =>
    api.get<JusbrSessionStatus>('/andamentos/jusbr/session').then((r) => r.data),

  configurarSessaoJusBR: (capture: string) =>
    api.post<JusbrSessionStatus>('/andamentos/jusbr/session', { capture }).then((r) => r.data),

  limparSessaoJusBR: () =>
    api.delete('/andamentos/jusbr/session').then((r) => r.data),

  dashboardAvisos: () =>
    api
      .get<{
        total_processos: number
        total_andamentos: number
        items: Array<{
          processo_id: string
          numero_cnj: string
          cliente_nome: string
          tribunal: string | null
          vara: string | null
          qtd_nao_lidos: number
          mais_recente: string | null
          ultimo_desc: string
        }>
      }>('/andamentos/dashboard/avisos')
      .then((r) => r.data),

  marcarLidosLote: (payload: { processo_ids?: string[]; all?: boolean }) =>
    api.post('/andamentos/dashboard/marcar-lidos-lote', payload).then((r) => r.data),

  iniciarPkceJusBR: () =>
    api
      .post<{ url: string; state_id: string; expires_in: number }>('/andamentos/jusbr/pkce/start')
      .then((r) => r.data),

  finalizarPkceJusBR: (state_id: string, pasted_url: string) =>
    api
      .post<{
        ok: boolean
        expires_at: string | null
        refresh_type: string | null
        refresh_scope: string | null
        refresh_expires_at: string | null
      }>('/andamentos/jusbr/pkce/finish', { state_id, pasted_url })
      .then((r) => r.data),

  arquivoUrl: (andamentoId: string) =>
    `/api/andamentos/arquivo/${andamentoId}?token=${encodeURIComponent(getToken() ?? '')}`,

  importarJusBR: (processoId: string, payload: string) =>
    api
      .post<SincronizacaoResult>(`/andamentos/processo/${processoId}/importar-jusbr`, { payload })
      .then((r) => r.data),

  codexStatus: (processoId: string) =>
    api
      .get<{ corrompidos: Array<{ id: string; nome: string | null; documento_id: string | null; data: string | null }> }>(
        `/andamentos/processo/${processoId}/codex-status`
      )
      .then((r) => r.data),

  repararCodex: (processoId: string) =>
    api
      .post<{
        ok: boolean
        erro?: string
        msg?: string
        detectados?: number
        reparados?: number
        pendentes?: number
      }>(`/andamentos/processo/${processoId}/reparar-codex`)
      .then((r) => r.data),
}
