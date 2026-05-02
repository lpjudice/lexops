import api from './client'

export type StatusTarefa = 'pendente' | 'em_andamento' | 'concluido' | 'cancelado'

export interface PedidoAcessoTarefa {
  usuario_id: string
  nome: string
}

export interface Tarefa {
  id: string
  cliente_id: string | null
  processo_id: string | null
  anotacao_id: string | null
  criado_por_id: string | null
  criado_por_nome: string | null
  cliente_nome: string | null
  titulo: string
  descricao: string | null
  responsavel: string | null
  tags: string | null
  data_limite: string | null
  status: StatusTarefa
  resumo_ia: string | null
  google_event_id: string | null
  confidencial: boolean
  usuarios_com_acesso: string[] | null
  acesso_restrito: boolean
  pedidos_acesso: PedidoAcessoTarefa[]
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
  confidencial?: boolean
}

export const tarefasApi = {
  listar: (params?: { cliente_id?: string; status?: StatusTarefa }) =>
    api.get<Tarefa[]>('/tarefas/', { params }).then((r) => r.data),

  criar: (data: TarefaCreate) =>
    api.post<Tarefa>('/tarefas/', data).then((r) => r.data),

  atualizar: (id: string, data: Partial<TarefaCreate & { status: StatusTarefa; confidencial: boolean }>) =>
    api.patch<Tarefa>(`/tarefas/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/tarefas/${id}`),

  agendarCalendario: (id: string) =>
    api.post<Tarefa>(`/tarefas/${id}/agendar-calendario`).then((r) => r.data),

  solicitarAcesso: (id: string) =>
    api.post<{ ok: boolean; mensagem: string }>(`/tarefas/${id}/solicitar-acesso`).then((r) => r.data),

  concederAcesso: (tarefaId: string, usuarioId: string) =>
    api.post<Tarefa>(`/tarefas/${tarefaId}/conceder-acesso/${usuarioId}`).then((r) => r.data),

  revogarAcesso: (tarefaId: string, usuarioId: string) =>
    api.post<Tarefa>(`/tarefas/${tarefaId}/revogar-acesso/${usuarioId}`).then((r) => r.data),
}
