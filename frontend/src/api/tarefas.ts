import api from './client'

export type StatusTarefa = 'pendente' | 'em_andamento' | 'concluido' | 'cancelado'

export interface PedidoAcessoTarefa {
  usuario_id: string
  nome: string
}

export interface AnexoTarefa {
  id: string
  tarefa_id: string
  nome_arquivo: string
  drive_link: string | null
  content_type: string | null
  created_at: string
}

export interface Tarefa {
  id: string
  cliente_id: string | null
  processo_id: string | null
  anotacao_id: string | null
  projeto_id: string | null
  projeto_nome: string | null
  projeto_cor: string | null
  criado_por_id: string | null
  criado_por_nome: string | null
  cliente_nome: string | null
  titulo: string
  descricao: string | null
  responsavel: string | null
  responsavel_email: string | null
  responsavel_id?: string | null
  tags: string | null
  data_limite: string | null
  status: StatusTarefa
  resumo_ia: string | null
  google_event_id: string | null
  ordem: number | null
  confidencial: boolean
  usuarios_com_acesso: string[] | null
  criado_automaticamente?: boolean
  prazo_id?: string | null
  arquivada?: boolean
  arquivada_em?: string | null
  codigo?: string | null
  anexos?: AnexoTarefa[]
  acesso_restrito: boolean
  pedidos_acesso: PedidoAcessoTarefa[]
  ja_solicitou: boolean
  usuarios_com_acesso_nomes: { id: string; nome: string }[]
  created_at: string
  updated_at: string
}

export interface TarefaCreate {
  cliente_id?: string | null
  processo_id?: string | null
  anotacao_id?: string | null
  projeto_id?: string | null
  titulo: string
  descricao?: string | null
  responsavel?: string | null
  responsavel_email?: string | null
  responsavel_id?: string | null
  tags?: string | null
  data_limite?: string | null
  status?: StatusTarefa
  confidencial?: boolean
}

export const tarefasApi = {
  listar: (params?: { cliente_id?: string; status?: StatusTarefa; arquivada?: boolean }) =>
    api.get<Tarefa[]>('/tarefas/', { params }).then((r) => r.data),

  arquivar: (id: string) => api.post<Tarefa>(`/tarefas/${id}/arquivar`).then((r) => r.data),
  desarquivar: (id: string) => api.post<Tarefa>(`/tarefas/${id}/desarquivar`).then((r) => r.data),

  uploadAnexo: (tarefaId: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return api.post<Tarefa>(`/tarefas/${tarefaId}/anexos`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data)
  },
  deletarAnexo: (anexoId: string) => api.delete(`/tarefas/anexos/${anexoId}`),

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

  reordenar: (ids: string[]) =>
    api.post('/tarefas/reordenar', ids),
}
