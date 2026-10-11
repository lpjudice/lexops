import api from './client'

export type StatusScraping = 'pendente' | 'ok' | 'erro_parsing'
export type StatusIa = 'nao_aplicavel' | 'pendente' | 'processando' | 'ok' | 'erro'

export interface InformativoStfItem {
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
  resumo_leigo?: string | null
  instagram_sugestao_id?: string | null
  instagram_gerado_em?: string | null
  instagram_status?: 'sugerido' | 'aprovado' | 'rejeitado' | 'publicado' | null
  custo_ia_usd: number
  ia_processado_em?: string | null
  erro_ia?: string | null
  edicao_numero?: number | null
}

export interface DestaqueResumo {
  id: string
  titulo: string
  resumo_tema_central?: string | null
  ramo_direito: string
  favorito: boolean
}

export interface InformativoStfEdicao {
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
  destaques: DestaqueResumo[]
}

export interface InformativoStfEdicaoDetalhe extends InformativoStfEdicao {
  itens: InformativoStfItem[]
}

export interface InformativoStfConfig {
  areas_selecionadas: string[]
  keywords_livres: string[]
  atualizado_em: string
}

export interface SyncResponse {
  edicoes_processadas: number
  detalhe?: unknown[] | null
  erro?: string | null
}

export const informativoStfApi = {
  listarEdicoes: (limit = 20) =>
    api.get<InformativoStfEdicao[]>('/informativo-stf/edicoes', { params: { limit } }).then((r) => r.data),

  getEdicao: (edicaoId: string) =>
    api.get<InformativoStfEdicaoDetalhe>(`/informativo-stf/edicoes/${edicaoId}`).then((r) => r.data),

  listarItens: (params?: { area?: string; destacado?: boolean; status_ia?: string; q?: string }) =>
    api.get<InformativoStfItem[]>('/informativo-stf/itens', { params }).then((r) => r.data),

  getConfig: () => api.get<InformativoStfConfig>('/informativo-stf/config').then((r) => r.data),

  updateConfig: (payload: { areas_selecionadas: string[]; keywords_livres: string[] }) =>
    api.put<InformativoStfConfig>('/informativo-stf/config', payload).then((r) => r.data),

  reclassificar: () =>
    api.post<{ total_itens: number; alterados: number }>('/informativo-stf/reclassificar').then((r) => r.data),

  reprocessarItem: (itemId: string) =>
    api.post<InformativoStfItem>(`/informativo-stf/itens/${itemId}/reprocessar`).then((r) => r.data),

  sincronizarAgora: () =>
    api.post<SyncResponse>('/informativo-stf/sync', undefined, { timeout: 120000 }).then((r) => r.data),

  buscar: (q: string) =>
    api.get<InformativoStfItem[]>('/informativo-stf/busca', { params: { q } }).then((r) => r.data),

  listarFavoritos: () =>
    api.get<InformativoStfItem[]>('/informativo-stf/favoritos').then((r) => r.data),

  favoritar: (itemId: string) =>
    api.post<InformativoStfItem>(`/informativo-stf/itens/${itemId}/favoritar`).then((r) => r.data),

  forcarInstagram: (itemId: string) =>
    api.post<InformativoStfItem>(`/informativo-stf/itens/${itemId}/forcar-instagram`, undefined, { timeout: 120000 }).then((r) => r.data),

  reprocessarTudo: () =>
    api.post<{ total: number; ok: number; erro: number }>('/informativo-stf/reprocessar-tudo', undefined, { timeout: 300000 }).then((r) => r.data),

  enviarEmailItem: (itemId: string, destinatario?: string) =>
    api.post<{ enviado_para: string }>(`/informativo-stf/itens/${itemId}/enviar-email`, { destinatario }).then((r) => r.data),
}
