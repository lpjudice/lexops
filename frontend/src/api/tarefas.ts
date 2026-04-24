import api from './client'

export type StatusTarefa = 'pendente' | 'em_andamento' | 'concluido' | 'cancelado'

export interface Tarefa {
  id: string
  cliente_id: string | null
  processo_id: string | null
  anotacao_id: string | null
  titulo: string
  descricao: string | null
  responsavel: string | null
  tags: string | null
  data_limite: string | null
  status: StatusTarefa
  resumo_ia: string | null
  google_event_id: string | null
  created_at: string
  updated_at: string
}

export interface TarefaCreate {
  cliente_id?: string | null
  processo_id?: string | null
  anotacao_id?: string | null
  titulo: string
  descricao?: string | null
  responsavel?: string | null
  tags?: string | null
  data_limite?: string | null
  status?: StatusTarefa
}

export const tarefasApi = {
  listar: (params?: { cliente_id?: string; status?: StatusTarefa }) =>
    api.get<Tarefa[]>('/tarefas/', { params }).then((r) => r.data),

  criar: (data: TarefaCreate) =>
    api.post<Tarefa>('/tarefas/', data).then((r) => r.data),

  atualizar: (id: string, data: Partial<TarefaCreate & { status: StatusTarefa }>) =>
    api.patch<Tarefa>(`/tarefas/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/tarefas/${id}`),

  agendarCalendario: (id: string) =>
    api.post<Tarefa>(`/tarefas/${id}/agendar-calendario`).then((r) => r.data),
}
