import api from './client'

export type ModeloIA = 'claude' | 'gpt' | 'gemini'

export interface Tese {
  id: string
  titulo: string
  texto_input: string
  resposta_claude?: string
  resposta_gpt?: string
  resposta_gemini?: string
  modelo_ativo: ModeloIA
  cliente_id?: string
  processo_id?: string
  created_at: string
}

export interface TeseCreate {
  titulo: string
  texto_input: string
  modelo_ativo: ModeloIA
  cliente_id?: string
  processo_id?: string
}

export const tesesApi = {
  listar: (params?: { cliente_id?: string; processo_id?: string }) =>
    api.get<Tese[]>('/teses/', { params }).then((r) => r.data),

  criar: (data: TeseCreate) =>
    api.post<Tese>('/teses/', data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/teses/${id}`),

  gerar: (id: string, modelo: ModeloIA) =>
    api.post<Tese>(`/teses/${id}/gerar/${modelo}`).then((r) => r.data),
}
