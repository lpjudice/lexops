import api from './client'

export type TipoPrazo =
  | 'contestacao' | 'recurso' | 'contrarrazoes' | 'manifestacao'
  | 'audiencia' | 'pericia' | 'outro'
export type TipoContagem = 'uteis' | 'corridos'
export type StatusPrazo = 'pendente' | 'cumprido' | 'perdido'

export interface Prazo {
  id: string
  processo_id: string
  tipo: TipoPrazo
  descricao?: string
  peca_necessaria?: string
  responsavel?: string | null
  data_publicacao: string
  dias_prazo: number
  tipo_contagem: TipoContagem
  data_limite?: string
  data_limite_sem_feriado?: string
  status: StatusPrazo
  google_event_id?: string
  criado_automaticamente?: boolean
  created_at: string
  updated_at: string
}

export interface PrazoCreate {
  processo_id: string
  tipo: TipoPrazo
  descricao?: string
  peca_necessaria?: string
  responsavel?: string | null
  data_publicacao: string
  dias_prazo: number
  tipo_contagem?: TipoContagem
  status?: StatusPrazo
}

export const prazosApi = {
  listar: (params?: { processo_id?: string; status?: string }) =>
    api.get<Prazo[]>('/prazos/', { params }).then((r) => r.data),
  criar: (data: PrazoCreate) => api.post<Prazo>('/prazos/', data).then((r) => r.data),
  atualizar: (id: string, data: Partial<PrazoCreate>) =>
    api.patch<Prazo>(`/prazos/${id}`, data).then((r) => r.data),
  deletar: (id: string) => api.delete(`/prazos/${id}`),
}
