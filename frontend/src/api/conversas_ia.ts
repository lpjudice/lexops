import api from './client'
import type { ChatMessage } from './clientes'

export interface ConversaIA {
  id: string
  cliente_id: string
  processo_id: string | null
  titulo: string | null
  modelo: string
  historico: ChatMessage[]
  resumo: string | null
  parent_conversa_id: string | null
  created_at: string
  updated_at: string
}

export const conversasIaApi = {
  listar: (params: { cliente_id?: string; processo_id?: string }) =>
    api.get<ConversaIA[]>('/conversas-ia/', { params }).then((r) => r.data),

  criar: (
    clienteId: string,
    modelo: string,
    historico: ChatMessage[],
    titulo?: string,
    processoId?: string,
  ) =>
    api.post<ConversaIA>('/conversas-ia/', {
      cliente_id: clienteId,
      modelo,
      historico,
      titulo: titulo ?? null,
      processo_id: processoId ?? null,
    }).then((r) => r.data),

  atualizar: (id: string, data: { historico?: ChatMessage[]; titulo?: string | null; modelo?: string }) =>
    api.patch<ConversaIA>(`/conversas-ia/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/conversas-ia/${id}`),

  compactar: (id: string) =>
    api.post<ConversaIA>(`/conversas-ia/${id}/compactar`).then((r) => r.data),

  downloadPdf: (id: string) =>
    api.get(`/conversas-ia/${id}/pdf`, { responseType: 'blob' }).then((r) => r.data as Blob),
}
