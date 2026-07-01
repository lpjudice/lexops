import api from './client'

export type StatusTarefaCard = 'pendente' | 'em_andamento' | 'concluido' | 'cancelado'

export interface SubtaskCard {
  id: string
  texto: string
  concluida: boolean
  ordem: number
}

export interface PedidoAcessoCard {
  usuario_id: string
  nome: string
}

export interface TarefaCard {
  id: string
  projeto_id: string | null
  projeto_nome: string | null
  projeto_cor: string | null
  cliente_id: string | null
  cliente_nome: string | null
  processo_id: string | null
  processo_numero: string | null
  criado_por_id: string | null
  criado_por_nome: string | null
  titulo: string
  descricao: string | null
  notas: string | null
  responsavel: string | null
  responsavel_email: string | null
  status: StatusTarefaCard
  data_limite: string | null
  google_event_id: string | null
  ordem: number | null
  confidencial: boolean
  usuarios_com_acesso: string[] | null
  created_at: string
  updated_at: string
  subtasks: SubtaskCard[]
  acesso_restrito: boolean
  pedidos_acesso: PedidoAcessoCard[]
  ja_solicitou: boolean
  usuarios_com_acesso_nomes: { id: string; nome: string }[]
}

export interface TarefaCardCreate {
  projeto_id?: string | null
  cliente_id?: string | null
  processo_id?: string | null
  titulo: string
  descricao?: string | null
  notas?: string | null
  responsavel?: string | null
  responsavel_email?: string | null
  status?: StatusTarefaCard
  data_limite?: string | null
  confidencial?: boolean
  subtasks?: { texto: string; concluida?: boolean; ordem?: number }[]
}

export const tarefaCardsApi = {
  listar: (params?: { projeto_id?: string; cliente_id?: string; status?: StatusTarefaCard }) =>
    api.get<TarefaCard[]>('/tarefa-cards/', { params }).then((r) => r.data),

  criar: (data: TarefaCardCreate) =>
    api.post<TarefaCard>('/tarefa-cards/', data).then((r) => r.data),

  atualizar: (id: string, data: Partial<TarefaCardCreate & { status: StatusTarefaCard; confidencial: boolean }>) =>
    api.patch<TarefaCard>(`/tarefa-cards/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/tarefa-cards/${id}`),

  reordenar: (ids: string[]) => api.post('/tarefa-cards/reordenar', ids),

  addSubtask: (cardId: string, texto: string) =>
    api.post<TarefaCard>(`/tarefa-cards/${cardId}/subtasks`, null, { params: { texto } }).then((r) => r.data),
  toggleSubtask: (subtaskId: string, concluida: boolean) =>
    api.patch<TarefaCard>(`/tarefa-cards/subtasks/${subtaskId}`, null, { params: { concluida } }).then((r) => r.data),
  editarSubtask: (subtaskId: string, texto: string) =>
    api.patch<TarefaCard>(`/tarefa-cards/subtasks/${subtaskId}`, null, { params: { texto } }).then((r) => r.data),
  deletarSubtask: (subtaskId: string) => api.delete(`/tarefa-cards/subtasks/${subtaskId}`),

  agendarCalendario: (id: string) =>
    api.post<TarefaCard>(`/tarefa-cards/${id}/agendar-calendario`).then((r) => r.data),

  solicitarAcesso: (id: string) =>
    api.post<{ ok: boolean; mensagem: string }>(`/tarefa-cards/${id}/solicitar-acesso`).then((r) => r.data),
  concederAcesso: (cardId: string, usuarioId: string) =>
    api.post<TarefaCard>(`/tarefa-cards/${cardId}/conceder-acesso/${usuarioId}`).then((r) => r.data),
  revogarAcesso: (cardId: string, usuarioId: string) =>
    api.post<TarefaCard>(`/tarefa-cards/${cardId}/revogar-acesso/${usuarioId}`).then((r) => r.data),
}
