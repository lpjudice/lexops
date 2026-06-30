import api from './client'

export interface TarefaProjeto {
  id: string
  nome: string
  cor: string
  oculto: boolean
  created_at: string
}

export const tarefaProjetosApi = {
  listar: () => api.get<TarefaProjeto[]>('/tarefa-projetos/').then((r) => r.data),
  criar: (data: { nome: string; cor: string; oculto?: boolean }) =>
    api.post<TarefaProjeto>('/tarefa-projetos/', data).then((r) => r.data),
  atualizar: (id: string, data: Partial<{ nome: string; cor: string; oculto: boolean }>) =>
    api.patch<TarefaProjeto>(`/tarefa-projetos/${id}`, data).then((r) => r.data),
  deletar: (id: string) => api.delete(`/tarefa-projetos/${id}`),
}
