import api from './client'

export type FontePublicacao =
  | 'gmail' | 'scraping_tjes' | 'scraping_tjsp' | 'scraping_tjam' | 'scraping_tjrj' | 'scraping_djen' | 'pje_comunica' | 'manual'
export type TipoAto =
  | 'despacho' | 'decisao' | 'sentenca' | 'acordao' | 'intimacao' | 'citacao' | 'outro'

export interface AnaliseIA {
  cliente_nome?: string
  numero_cnj?: string
  tribunal?: string
  vara?: string
  data_publicacao?: string
  data_disponibilizacao?: string
  tipo_ato?: TipoAto
  requer_resposta: boolean
  peca_necessaria?: string
  dias_prazo?: number
  tipo_contagem?: 'uteis' | 'corridos'
  resumo: string
  erro?: string
}

export interface Publicacao {
  id: string
  fonte: FontePublicacao
  data_publicacao: string
  numero_cnj?: string
  tipo_ato?: TipoAto
  tribunal?: string
  vara?: string
  texto_resumo?: string
  texto_completo?: string
  processo_id?: string
  prazo_id?: string
  lida: boolean
  gera_prazo: boolean
  analise_ia?: string      // JSON serializado
  cliente_nome_pub?: string
  url_fonte?: string
  created_at: string
}

export interface SyncResult {
  inseridas: number
  duplicatas: number
  erros: number
  fonte: string
}

export interface DiarioMonitoringConfig {
  tribunais: string[]
  termos_extras: string[]
  auto_sync: boolean
}

export const diarioApi = {
  listar: (params?: { lida?: boolean; tribunal?: string; processo_id?: string }) =>
    api.get<Publicacao[]>('/diario/', { params }).then((r) => r.data),

  syncGmail: (days_back = 3) =>
    api.post<SyncResult>('/diario/gmail/sync', null, { params: { days_back } }).then((r) => r.data),

  syncScraping: (tribunais: string[], termos: string[] = [], days_back = 1) =>
    api.post<SyncResult>('/diario/scraping/sync', null, {
      params: { tribunais, termos, days_back },
    }).then((r) => r.data),

  marcarLida: (id: string) =>
    api.patch<Publicacao>(`/diario/${id}/lida`).then((r) => r.data),

  vincularProcesso: (id: string, processo_id: string) =>
    api.patch<Publicacao>(`/diario/${id}`, { processo_id }).then((r) => r.data),

  analisar: (id: string) =>
    api.post<Publicacao>(`/diario/${id}/analisar`).then((r) => r.data),

  criarPrazo: (id: string) =>
    api.post<{ prazo_id: string; data_limite: string; tipo: string }>(`/diario/${id}/criar-prazo`).then((r) => r.data),

  criarTese: (id: string) =>
    api.post<{ tese_id: string }>(`/diario/${id}/criar-tese`).then((r) => r.data),

  deletar: (id: string) => api.delete(`/diario/${id}`),

  googleStatus: () =>
    api.get<{ conectado: boolean }>('/auth/google/status').then((r) => r.data),

  syncPje: () =>
    api.post<{ inseridas: number; duplicatas: number; total_pje: number }>('/pje/sync').then(r => r.data),

  pjeConfig: () =>
    api.get<{ configurado: boolean; login_cpf: string }>('/pje/config').then(r => r.data),

  savePjeConfig: (login_cpf: string, senha: string) =>
    api.post('/pje/config', { login_cpf, senha }).then(r => r.data),

  monitoramento: () =>
    api.get<DiarioMonitoringConfig>('/diario/monitoramento').then((r) => r.data),

  salvarMonitoramento: (data: DiarioMonitoringConfig) =>
    api.put<DiarioMonitoringConfig>('/diario/monitoramento', data).then((r) => r.data),
}
