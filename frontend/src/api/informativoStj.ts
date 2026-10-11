import api from './client'

export type StatusScraping = 'pendente' | 'ok' | 'erro_parsing'
export type StatusIa = 'nao_aplicavel' | 'pendente' | 'processando' | 'ok' | 'erro'

export interface InformativoStjItem {
  id: string
  edicao_id: string
  orgao_julgador: string
  ramo_direito: string
  titulo: string
  destaque_oficial: string
  processo_numero?: string | null
  processo_url?: string | null
  relator?: string | null
  data_julgamento?: string | null
  texto_explicativo?: string | null
  legislacao_citada: string[]
  ordem: number
  destacado: boolean
  favorito: boolean
  motivo_destaque?: string | null
  status_ia: StatusIa
  resumo_tema_central?: string | null
  resumo_ratio_decidendi?: string | null
  custo_ia_usd: number
  ia_processado_em?: string | null
  erro_ia?: string | null
}

export interface InformativoStjEdicao {
  id: string
  numero: number
  data_publicacao?: string | null
  tipo: 'ordinaria' | 'extraordinaria'
  tema_extraordinario?: string | null
  url_origem: string
  resumo_edicao?: string | null
  status_scraping: StatusScraping
  erro_scraping?: string | null
  scraped_em?: string | null
  total_itens: number
  total_destacados: number
}

export interface InformativoStjEdicaoDetalhe extends InformativoStjEdicao {
  itens: InformativoStjItem[]
}

export interface InformativoStjConfig {
  areas_selecionadas: string[]
  keywords_livres: string[]
  atualizado_em: string
}

export interface SyncResponse {
  edicoes_processadas: number
  detalhe?: unknown[] | null
  erro?: string | null
}

export const informativoStjApi = {
  listarEdicoes: (limit = 20) =>
    api.get<InformativoStjEdicao[]>('/informativo-stj/edicoes', { params: { limit } }).then((r) => r.data),

  getEdicao: (edicaoId: string) =>
    api.get<InformativoStjEdicaoDetalhe>(`/informativo-stj/edicoes/${edicaoId}`).then((r) => r.data),

  listarItens: (params?: { area?: string; destacado?: boolean; status_ia?: string; q?: string }) =>
    api.get<InformativoStjItem[]>('/informativo-stj/itens', { params }).then((r) => r.data),

  getConfig: () => api.get<InformativoStjConfig>('/informativo-stj/config').then((r) => r.data),

  updateConfig: (payload: { areas_selecionadas: string[]; keywords_livres: string[] }) =>
    api.put<InformativoStjConfig>('/informativo-stj/config', payload).then((r) => r.data),

  reclassificar: () =>
    api.post<{ total_itens: number; alterados: number }>('/informativo-stj/reclassificar').then((r) => r.data),

  reprocessarItem: (itemId: string) =>
    api.post<InformativoStjItem>(`/informativo-stj/itens/${itemId}/reprocessar`).then((r) => r.data),

  sincronizarAgora: () =>
    api.post<SyncResponse>('/informativo-stj/sync', undefined, { timeout: 120000 }).then((r) => r.data),

  buscar: (q: string) =>
    api.get<InformativoStjItem[]>('/informativo-stj/busca', { params: { q } }).then((r) => r.data),

  listarFavoritos: () =>
    api.get<InformativoStjItem[]>('/informativo-stj/favoritos').then((r) => r.data),

  favoritar: (itemId: string) =>
    api.post<InformativoStjItem>(`/informativo-stj/itens/${itemId}/favoritar`).then((r) => r.data),

  forcarInstagram: (itemId: string) =>
    api.post<{ sugestao_id: string }>(`/informativo-stj/itens/${itemId}/forcar-instagram`, undefined, { timeout: 120000 }).then((r) => r.data),
}
