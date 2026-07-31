import api from './client'

export type TipoBem = 'movel' | 'imovel'
export type ObjetivoBem = 'venda' | 'aluguel' | 'segurar'
export type StatusBem = 'em_validacao' | 'validado' | 'incerto'
export type TipoDocumentoElo =
  | 'contrato_compra_venda'
  | 'escritura_publica'
  | 'cessao_direitos'
  | 'matricula'
  | 'formal_partilha'
  | 'outro'

export interface Anexo {
  id: string
  filename: string
  drive_link?: string | null
  mime?: string | null
  created_at: string
}

export interface CadeiaElo {
  id: string
  ordem: number
  tipo_documento: TipoDocumentoElo
  de_quem?: string | null
  para_quem?: string | null
  data?: string | null
  descricao?: string | null
  arquivo_nome?: string | null
  drive_link?: string | null
  created_at: string
}

export interface Bem {
  id: string
  cliente_id: string
  tipo_bem: TipoBem
  nome: string
  descricao?: string | null
  valor_compra?: number | null
  valor_mercado?: number | null
  valor_ir?: number | null
  data_compra?: string | null
  objetivo?: ObjetivoBem | null
  descricao_matricula?: string | null
  numero_matricula?: string | null
  cartorio?: string | null
  status: StatusBem
  integralizar_holding: boolean
  proprietario_real?: string | null
  proprietario_matricula?: string | null
  tem_gravame: boolean
  gravame_descricao?: string | null
  observacoes?: string | null
  anexos: Anexo[]
  cadeia: CadeiaElo[]
  created_at: string
  updated_at: string
}

export type BemCreate = { cliente_id: string } & Partial<Omit<Bem, 'id' | 'cliente_id' | 'anexos' | 'cadeia' | 'created_at' | 'updated_at'>> & { nome: string }
export type BemUpdate = Partial<Omit<Bem, 'id' | 'cliente_id' | 'anexos' | 'cadeia' | 'created_at' | 'updated_at'>>

export type CadeiaEloCreate = Partial<Omit<CadeiaElo, 'id' | 'arquivo_nome' | 'drive_link' | 'created_at'>>
export type CadeiaEloUpdate = CadeiaEloCreate

export const patrimonioApi = {
  listar: (clienteId: string) =>
    api.get<Bem[]>('/patrimonio/', { params: { cliente_id: clienteId } }).then((r) => r.data),

  criar: (data: BemCreate) => api.post<Bem>('/patrimonio/', data).then((r) => r.data),

  atualizar: (id: string, data: BemUpdate) =>
    api.patch<Bem>(`/patrimonio/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/patrimonio/${id}`),

  uploadAnexo: (bemId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<Anexo>(`/patrimonio/${bemId}/anexos`, form).then((r) => r.data)
  },

  deletarAnexo: (bemId: string, anexoId: string) =>
    api.delete(`/patrimonio/${bemId}/anexos/${anexoId}`),

  criarElo: (bemId: string, data: CadeiaEloCreate) =>
    api.post<CadeiaElo>(`/patrimonio/${bemId}/cadeia`, data).then((r) => r.data),

  atualizarElo: (bemId: string, eloId: string, data: CadeiaEloUpdate) =>
    api.patch<CadeiaElo>(`/patrimonio/${bemId}/cadeia/${eloId}`, data).then((r) => r.data),

  deletarElo: (bemId: string, eloId: string) =>
    api.delete(`/patrimonio/${bemId}/cadeia/${eloId}`),

  uploadAnexoElo: (bemId: string, eloId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<CadeiaElo>(`/patrimonio/${bemId}/cadeia/${eloId}/anexo`, form).then((r) => r.data)
  },

  exportXls: (clienteId: string) =>
    api.get(`/patrimonio/export/xls`, { params: { cliente_id: clienteId }, responseType: 'blob' })
      .then((r) => r.data as Blob),

  exportPdf: (clienteId: string) =>
    api.get(`/patrimonio/export/pdf`, { params: { cliente_id: clienteId }, responseType: 'blob' })
      .then((r) => r.data as Blob),
}
