import api from './client'

export type TipoPrazo =
  | 'contestacao' | 'recurso' | 'contrarrazoes' | 'manifestacao'
  | 'audiencia' | 'pericia' | 'outro'
export type TipoContagem = 'uteis' | 'corridos'
export type StatusPrazo = 'pendente' | 'cumprido' | 'perdido' | 'ignorado' | 'nada_a_fazer'

export interface ComentarioPrazo {
  id: string
  texto: string
  autor_nome?: string | null
  andamento_id?: string | null
  created_at: string
}

/** Mesmo comentário, pela ótica do PROCESSO — alimenta o painel "Anotações de
 * Prazos" em Processos e a nota interleaved em Andamentos. Vem achatado do
 * backend (ver ComentarioPrazoProcessoOut). */
export interface ComentarioPrazoDoProcesso {
  id: string
  texto: string
  autor_nome?: string | null
  created_at: string
  andamento_id?: string | null
  andamento_tipo?: string | null
  andamento_data?: string | null
  prazo_id: string
  prazo_tipo: TipoPrazo
  prazo_peca?: string | null
  prazo_status: StatusPrazo
  prazo_data_limite?: string | null
}

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
  motivo_perda?: string | null
  google_event_id?: string
  criado_automaticamente?: boolean
  tarefas_vinculadas?: { id: string; titulo: string }[]
  peca_doc_url?: string | null
  publicacao_origem?: PublicacaoOrigem | null
  ultimo_lembrete_em?: string | null
  comentarios?: ComentarioPrazo[]
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
  motivo_perda?: string | null
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
  criarComentario: (prazoId: string, texto: string, andamentoId?: string | null) =>
    api.post<ComentarioPrazo>(`/prazos/${prazoId}/comentarios`, {
      texto,
      andamento_id: andamentoId ?? null,
    }).then((r) => r.data),
  deletarComentario: (prazoId: string, comentarioId: string) =>
    api.delete(`/prazos/${prazoId}/comentarios/${comentarioId}`),
  listarComentariosDoProcesso: (processoId: string) =>
    api.get<ComentarioPrazoDoProcesso[]>(`/prazos/processo/${processoId}/comentarios`).then((r) => r.data),
}
