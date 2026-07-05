import api from './client'

export type CategoriaResponsavel = 'advogado' | 'terceiro' | 'colaborador' | 'financeiro'

export interface Responsavel {
  id: string
  nome: string
  email: string | null
  telefone: string | null
  oab_numero: string | null
  oab_uf: string | null
  categoria: CategoriaResponsavel
  usuario_id: string | null
  eh_usuario_sistema: boolean
  ativo: boolean
}

export interface ResponsavelCreate {
  nome: string
  email?: string | null
  telefone?: string | null
  oab_numero?: string | null
  oab_uf?: string | null
  categoria?: CategoriaResponsavel
}

export interface ResponsavelUpdate {
  nome?: string
  email?: string | null
  telefone?: string | null
  oab_numero?: string | null
  oab_uf?: string | null
  categoria?: CategoriaResponsavel
  ativo?: boolean
}

export const responsaveisApi = {
  listar: (params?: { q?: string; categoria?: CategoriaResponsavel; apenas_ativos?: boolean }) =>
    api.get<Responsavel[]>('/responsaveis', { params }).then((r) => r.data),

  criar: (data: ResponsavelCreate) =>
    api.post<Responsavel>('/responsaveis', data).then((r) => r.data),

  atualizar: (id: string, data: ResponsavelUpdate) =>
    api.patch<Responsavel>(`/responsaveis/${id}`, data).then((r) => r.data),

  mesclar: (sobreviventeId: string, mesclados: string[]) =>
    api.post('/responsaveis/mesclar', { sobrevivente_id: sobreviventeId, mesclados }).then((r) => r.data),
}
