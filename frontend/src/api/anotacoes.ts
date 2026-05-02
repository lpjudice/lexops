import api from './client'

export type TipoAnotacao = 'reuniao' | 'ligacao' | 'whatsapp' | 'email' | 'documento' | 'anamnese' | 'reuniao_todo' | 'outro'

export interface Anotacao {
  id: string
  cliente_id: string
  processo_id?: string
  tipo: TipoAnotacao
  data_evento: string
  titulo?: string
  texto: string
  created_at: string
  updated_at: string
}

export interface AnotacaoCreate {
  cliente_id: string
  processo_id?: string
  tipo: TipoAnotacao
  data_evento: string
  titulo?: string
  texto: string
}

export type TimelineTipo = 'anotacao' | 'prazo' | 'publicacao' | 'email' | 'reuniao'

export interface TimelineItem {
  tipo: TimelineTipo
  data: string
  titulo: string
  subtitulo?: string
  texto?: string
  referencia_id?: string
  meta: Record<string, unknown>
}

export const anotacoesApi = {
  listar: (params?: { cliente_id?: string; processo_id?: string }) =>
    api.get<Anotacao[]>('/anotacoes/', { params }).then((r) => r.data),

  criar: (data: AnotacaoCreate) =>
    api.post<Anotacao>('/anotacoes/', data).then((r) => r.data),

  atualizar: (id: string, data: Partial<AnotacaoCreate>) =>
    api.patch<Anotacao>(`/anotacoes/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/anotacoes/${id}`),

  timeline: (clienteId: string, incluirEmails = true) =>
    api
      .get<TimelineItem[]>(`/anotacoes/cliente/${clienteId}/timeline`, {
        params: { incluir_emails: incluirEmails },
      })
      .then((r) => r.data),
}
