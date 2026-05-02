import api from './client'

export type StatusReuniao = 'pendente' | 'em_revisao' | 'processada'
export type FonteReuniao = 'drive_auto' | 'manual'
export type TipoAcao = 'tarefa' | 'contrato' | 'anotacao'

export interface AcaoSugerida {
  tipo: TipoAcao
  aprovada: boolean | null
  titulo: string
  descricao?: string | null
  // tarefa
  data_limite?: string | null
  responsavel?: string | null
  // contrato
  valor_mencionado?: number | null
  // anotacao
  conteudo?: string | null
}

export interface Reuniao {
  id: string
  titulo: string
  data_reuniao: string | null
  duracao_minutos: number | null
  google_meet_url: string | null
  cliente_id: string | null
  cliente_nome: string | null
  processo_id: string | null
  processo_numero: string | null
  drive_transcricao_file_id: string | null
  drive_notas_file_id: string | null
  drive_tldr_file_id: string | null
  transcricao_texto: string | null
  resumo_ia: string | null
  acoes_sugeridas: AcaoSugerida[] | null
  status: StatusReuniao
  fonte: FonteReuniao
  created_at: string
  updated_at: string
}

export interface ReuniaoCreate {
  titulo: string
  data_reuniao?: string | null
  duracao_minutos?: number | null
  google_meet_url?: string | null
  transcricao_texto?: string | null
  cliente_id?: string | null
  processo_id?: string | null
  fonte?: FonteReuniao
}

export const reunioesApi = {
  listar: (params?: { cliente_id?: string; status?: StatusReuniao }) =>
    api.get<Reuniao[]>('/reunioes/', { params }).then((r) => r.data),

  criar: (data: ReuniaoCreate) =>
    api.post<Reuniao>('/reunioes/', data).then((r) => r.data),

  syncDrive: () =>
    api.post<Reuniao[]>('/reunioes/sync-drive').then((r) => r.data),

  obter: (id: string) =>
    api.get<Reuniao>(`/reunioes/${id}`).then((r) => r.data),

  atualizar: (id: string, data: Partial<ReuniaoCreate & { status: StatusReuniao; acoes_sugeridas: AcaoSugerida[]; resumo_ia: string }>) =>
    api.patch<Reuniao>(`/reunioes/${id}`, data).then((r) => r.data),

  processar: (id: string) =>
    api.post<Reuniao>(`/reunioes/${id}/processar`).then((r) => r.data),

  confirmarAcoes: (id: string, acoes_sugeridas: AcaoSugerida[]) =>
    api.post<Reuniao>(`/reunioes/${id}/confirmar-acoes`, { acoes_sugeridas }).then((r) => r.data),

  deletar: (id: string) => api.delete(`/reunioes/${id}`),
}
