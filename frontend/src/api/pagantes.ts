import api from './client'

export interface PaganteIn {
  nome: string
  cpf_cnpj?: string
  email?: string
  telefone?: string
  logradouro?: string
  numero?: string
  complemento?: string
  bairro?: string
  cidade?: string
  estado?: string
  cod_municipio?: string
  cep?: string
  cliente_id?: string
  observacoes?: string
}

export interface PaganteOut {
  id: string
  nome: string
  cpf_cnpj?: string
  email?: string
  telefone?: string
  logradouro?: string
  numero?: string
  complemento?: string
  bairro?: string
  cidade?: string
  estado?: string
  cod_municipio?: string
  cep?: string
  cliente_id?: string
  cliente_nome?: string
  observacoes?: string
  origem: string
  qtd_nfs: number
  valor_total: number
}

export const pagantesApi = {
  listar: () => api.get<PaganteOut[]>('/pagantes').then((r) => r.data),
  criar: (body: PaganteIn) => api.post<PaganteOut>('/pagantes', body).then((r) => r.data),
  atualizar: (id: string, body: PaganteIn) =>
    api.patch<PaganteOut>(`/pagantes/${id}`, body).then((r) => r.data),
  deletar: (id: string) => api.delete(`/pagantes/${id}`).then((r) => r.data),
}
