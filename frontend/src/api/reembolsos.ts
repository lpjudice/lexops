import api from './client'

export type StatusReembolso = 'rascunho' | 'aguardando_pagamento' | 'enviado' | 'pago' | 'cancelado'

export interface ItemReembolso {
  id: string
  reembolso_id: string
  data: string
  descricao: string
  natureza: string
  documento_comprobatorio?: string
  comprovante_path?: string | null
  comprovante_drive_link?: string | null
  valor: number
}

export interface Reembolso {
  id: string
  cliente_id: string
  processo_id?: string
  titulo: string
  data_emissao: string
  data_vencimento?: string
  status: StatusReembolso
  tratar_como_perda?: boolean
  total: number
  pdf_path?: string
  drive_link?: string
  email_destinatario?: string | null
  ultimo_lembrete_em?: string | null
  itens: ItemReembolso[]
  created_at: string
  updated_at: string
}

export interface ReembolsoCreate {
  cliente_id: string
  processo_id?: string
  titulo: string
  data_emissao: string
  data_vencimento?: string
}

export interface ItemReembolsoCreate {
  data: string
  descricao: string
  natureza: string
  documento_comprobatorio?: string
  valor: number
}

export const reembolsosApi = {
  listar: (params?: { cliente_id?: string }) =>
    api.get<Reembolso[]>('/reembolsos/', { params }).then((r) => r.data),

  criar: (data: ReembolsoCreate) =>
    api.post<Reembolso>('/reembolsos/', data).then((r) => r.data),

  atualizar: (id: string, data: Partial<ReembolsoCreate & { status: StatusReembolso; tratar_como_perda: boolean }>) =>
    api.patch<Reembolso>(`/reembolsos/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/reembolsos/${id}`),

  cancelar: (id: string) =>
    api.post<Reembolso>(`/reembolsos/${id}/cancelar`).then((r) => r.data),

  marcarPago: (id: string) =>
    api.post<Reembolso>(`/reembolsos/${id}/marcar-pago`).then((r) => r.data),

  reverterPagamento: (id: string) =>
    api.post<Reembolso>(`/reembolsos/${id}/reverter-pagamento`).then((r) => r.data),

  duplicar: (id: string) =>
    api.post<Reembolso>(`/reembolsos/${id}/duplicar`).then((r) => r.data),

  adicionarItem: (id: string, data: ItemReembolsoCreate) =>
    api.post<ItemReembolso>(`/reembolsos/${id}/itens`, data).then((r) => r.data),

  atualizarItem: (reembolsoId: string, itemId: string, data: Partial<ItemReembolsoCreate>) =>
    api.patch<ItemReembolso>(`/reembolsos/${reembolsoId}/itens/${itemId}`, data).then((r) => r.data),

  removerItem: (reembolsoId: string, itemId: string) =>
    api.delete(`/reembolsos/${reembolsoId}/itens/${itemId}`),

  uploadComprovante: (reembolsoId: string, itemId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post<ItemReembolso>(
      `/reembolsos/${reembolsoId}/itens/${itemId}/upload-comprovante`,
      fd,
      { headers: { 'Content-Type': undefined } }
    ).then((r) => r.data)
  },

  removerComprovante: (reembolsoId: string, itemId: string) =>
    api.delete<ItemReembolso>(`/reembolsos/${reembolsoId}/itens/${itemId}/comprovante`).then((r) => r.data),

  gerarPdf: (id: string) =>
    api.post(`/reembolsos/${id}/gerar-pdf`, null, { responseType: 'blob' }).then((r) => r.data as Blob),

  enviarEmail: (id: string, destinatario: string, copiarUsuario = false) =>
    api.post(`/reembolsos/${id}/enviar-email`, null, { params: { destinatario, copiar_usuario: copiarUsuario } }).then((r) => r.data),
}
