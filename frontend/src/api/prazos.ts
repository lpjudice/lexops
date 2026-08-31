import api from './client'

export type TipoPrazo =
  | 'contestacao' | 'recurso' | 'contrarrazoes' | 'manifestacao'
  | 'audiencia' | 'pericia' | 'outro'
export type TipoContagem = 'uteis' | 'corridos'
export type StatusPrazo = 'pendente' | 'cumprido' | 'perdido' | 'ignorado' | 'nada_a_fazer'

export interface PublicacaoOrigem {
  id: string
  fonte: string
  origem_menu: 'diario' | 'recorte'
  data_publicacao: string
  data_disponibilizacao?: string | null
  numero_cnj?: string | null
  tribunal?: string | null
  texto_resumo?: string | null
  url_fonte?: string | null
  disposicao?: string | null
}

export interface Prazo {
  id: string
  processo_id: string
  tipo: TipoPrazo
  descricao?: string
  peca_necessaria?: string
  responsavel?: string | null
  responsavel_id?: string | null
  data_publicacao: string
  dias_prazo: number
  tipo_contagem: TipoContagem
  data_limite?: string
  data_limite_sem_feriado?: string
  status: StatusPrazo
  google_event_id?: string
  criado_automaticamente?: boolean
  tarefas_vinculadas?: { id: string; titulo: string }[]
  peca_doc_url?: string | null
  publicacao_origem?: PublicacaoOrigem | null
  ultimo_lembrete_em?: string | null
  created_at: string
  updated_at: string
}

/** Campos editáveis do prazo — a tela de Prazos, o Diário Oficial e o Recorte
 * Digital usam todos o mesmo PATCH, então editar em qualquer um reflete nos
 * outros (é a mesma linha da tabela). */
export interface PrazoEdit {
  processo_id?: string
  tipo?: TipoPrazo
  descricao?: string
  peca_necessaria?: string
  responsavel?: string | null
  responsavel_id?: string | null
  data_publicacao?: string
  dias_prazo?: number
  tipo_contagem?: TipoContagem
  status?: StatusPrazo
}

export interface LembretesResultado {
  data: string
  prazos_ativos: number
  emails_enviados: number
  pulados_hoje: number
  erros: number
  telegram_enviado: boolean
}

export interface PrazoCreate {
  processo_id: string
  tipo: TipoPrazo
  descricao?: string
  peca_necessaria?: string
  responsavel?: string | null
  responsavel_id?: string | null
  data_publicacao: string
  dias_prazo: number
  tipo_contagem?: TipoContagem
  status?: StatusPrazo
}

export const prazosApi = {
  listar: (params?: { processo_id?: string; status?: string }) =>
    api.get<Prazo[]>('/prazos/', { params }).then((r) => r.data),
  criar: (data: PrazoCreate) => api.post<Prazo>('/prazos/', data).then((r) => r.data),
  atualizar: (id: string, data: PrazoEdit) =>
    api.patch<Prazo>(`/prazos/${id}`, data).then((r) => r.data),
  deletar: (id: string) => api.delete(`/prazos/${id}`),
  enviarLembretes: (forcar = false) =>
    api.post<LembretesResultado>('/prazos/lembretes/enviar', null, { params: { forcar } }).then((r) => r.data),
}
