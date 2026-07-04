import api from './client'

export interface MemoriaEstrategica {
  id: string
  cliente_id: string | null
  processo_id: string | null
  texto: string
  autor_id: string | null
  created_at: string
}

export const memoriaEstrategicaApi = {
  listar: (params: { cliente_id?: string; processo_id?: string }) =>
    api.get<MemoriaEstrategica[]>('/memoria-estrategica/', { params }).then((r) => r.data),

  criar: (data: { cliente_id?: string; processo_id?: string; texto: string }) =>
    api.post<MemoriaEstrategica>('/memoria-estrategica/', data).then((r) => r.data),
}
