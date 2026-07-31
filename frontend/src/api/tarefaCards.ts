import api from './client'

export type StatusTarefaCard = 'pendente' | 'em_andamento' | 'concluido' | 'cancelado'

export interface AnexoCard {
  id: string
  card_id: string
  subtask_id: string | null
  nome_arquivo: string
  drive_link: string | null
  content_type: string | null
  created_at: string
}

export interface SubtaskCard {
  id: string
  texto: string
  concluida: boolean
  ordem: number
  responsavel?: string | null
  responsavel_email?: string | null
  data_limite?: string | null
  anexos?: AnexoCard[]
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
  responsavel_id?: string | null
  status: StatusTarefaCard
  data_limite: string | null
  google_event_id: string | null
  ordem: number | null
  confidencial: boolean
  usuarios_com_acesso: string[] | null
  arquivada?: boolean
  arquivada_em?: string | null
  codigo?: string | null
  anexos?: AnexoCard[]
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
  responsavel_id?: string | null
  status?: StatusTarefaCard
  data_limite?: string | null
  confidencial?: boolean
  subtasks?: { texto: string; concluida?: boolean; ordem?: number }[]
}

export const tarefaCardsApi = {
  listar: (params?: { projeto_id?: string; cliente_id?: string; status?: StatusTarefaCard; arquivada?: boolean }) =>
    api.get<TarefaCard[]>('/tarefa-cards/', { params }).then((r) => r.data),

  arquivar: (id: string) => api.post<TarefaCard>(`/tarefa-cards/${id}/arquivar`).then((r) => r.data),
  desarquivar: (id: string) => api.post<TarefaCard>(`/tarefa-cards/${id}/desarquivar`).then((r) => r.data),

  uploadAnexoCard: (cardId: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return api.post<TarefaCard>(`/tarefa-cards/${cardId}/anexos`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data)
  },
  uploadAnexoSubtask: (subtaskId: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return api.post<TarefaCard>(`/tarefa-cards/subtasks/${subtaskId}/anexos`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data)
  },
  deletarAnexo: (anexoId: string) => api.delete(`/tarefa-cards/anexos/${anexoId}`),

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
  setSubtaskPrazo: (subtaskId: string, data_limite: string | null) =>
    api.patch<TarefaCard>(`/tarefa-cards/subtasks/${subtaskId}`, null, {
      params: data_limite ? { data_limite } : { limpar_data: true },
    }).then((r) => r.data),
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
