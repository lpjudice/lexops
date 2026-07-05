import api from './client'
import type { DespachoStatus } from './diario'

export type StatusPrazoDiario2 = 'pendente' | 'cumprido' | 'perdido'

export interface Diario2Prazo {
  id: string
  tipo: string
  descricao?: string | null
  peca_necessaria?: string | null
  data_limite?: string | null
  status: StatusPrazoDiario2
  dias_prazo: number
  tipo_contagem: 'uteis' | 'corridos'
}

export interface Diario2Publicacao {
  id: string
  data_publicacao: string
  numero_cnj?: string | null
  cliente?: string | null
  cliente_sugerido?: string | null
  processo_id?: string | null
  tribunal?: string | null
  publicado_em_nome_de: string
  resumo_curto: string
  texto_resumo?: string | null
  texto_completo?: string | null
  texto_relevante?: string | null
  detalhes?: {
    data_disponibilizacao?: string
    data_publicacao?: string
    jornal?: string
    caderno?: string
    local?: string
    classe?: string
    orgao?: string
    relator?: string
    partes?: string[]
  }
  tem_publicacao: boolean
  url_fonte?: string | null
  analise_ia?: {
    requer_resposta?: boolean
    peca_necessaria?: string
    dias_prazo?: number
    tipo_contagem?: 'uteis' | 'corridos'
    resumo?: string
    erro?: string
  } | null
  prazo?: Diario2Prazo | null
  created_at?: string | null
  despacho_status?: DespachoStatus | null
}

export interface Diario2Dia {
  data: string
  publicacoes: Diario2Publicacao[]
}

export interface Diario2Lista {
  dias: Diario2Dia[]
}

export interface Diario2SyncResult {
  inseridas: number
  duplicatas: number
  erros: number
  sem_publicacoes: number
  mensagem: string
}

export interface Diario2GmailStatus {
  conectado: boolean
  email?: string | null
  email_esperado: string
  ok: boolean
}

export interface Diario2PrazoCreate {
  processo_id?: string | null
  tipo: string
  descricao?: string
  peca_necessaria?: string
  responsavel?: string
  dias_prazo: number
  tipo_contagem: 'uteis' | 'corridos'
}

export interface Diario2RelembreItem {
  data_publicacao: string
  numero_cnj?: string | null
  cliente?: string | null
  tribunal?: string | null
  resumo_curto: string
  tem_prazo: boolean
  prazo?: Diario2Prazo | null
}

export interface Diario2Relembre {
  days_back: number
  total: number
  itens: Diario2RelembreItem[]
}

export const diario2Api = {
  listar: (daysBack = 30) =>
    api.get<Diario2Lista>('/diario2/', { params: { days_back: daysBack } }).then((r) => r.data),

  gmailStatus: () =>
    api.get<Diario2GmailStatus>('/diario2/gmail/status').then((r) => r.data),

  syncGmail: (daysBack = 7) =>
    api.post<Diario2SyncResult>('/diario2/gmail/sync', null, { params: { days_back: daysBack } }).then((r) => r.data),

  analisar: (id: string) =>
    api.post<Diario2Publicacao>(`/diario2/${id}/analisar`).then((r) => r.data),

  criarPrazo: (id: string, data: Diario2PrazoCreate) =>
    api.post<Diario2Publicacao>(`/diario2/${id}/criar-prazo`, data).then((r) => r.data),

  atualizarPrazoStatus: (id: string, status: StatusPrazoDiario2) =>
    api.patch<Diario2Publicacao>(`/diario2/${id}/prazo-status`, { status }).then((r) => r.data),

  relembre: (daysBack = 7) =>
    api.get<Diario2Relembre>('/diario2/relembre', { params: { days_back: daysBack } }).then((r) => r.data),
}
