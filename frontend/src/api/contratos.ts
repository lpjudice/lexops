import api, { getToken } from './client'

export type StatusContrato =
  | 'rascunho' | 'aguardando_assinatura' | 'parcialmente_assinado' | 'assinado' | 'cancelado'
export type PapelSignatario = 'contratante' | 'contratado' | 'testemunha' | 'outro'
export type StatusAssinatura = 'pendente' | 'assinado' | 'recusado'

export interface Signatario {
  id: string
  contrato_id: string
  nome: string
  email: string
  papel: PapelSignatario
  clicksign_signer_key?: string
  status_assinatura: StatusAssinatura
  assinado_em?: string
}

export interface ContratoArquivo {
  filename: string
  path: string
  clicksign_key?: string
  drive_link?: string | null
}

export interface Contrato {
  id: string
  cliente_id: string
  processo_id?: string
  titulo: string
  descricao?: string
  arquivo_path?: string
  arquivo_assinado_path?: string
  arquivos: ContratoArquivo[]
  status: StatusContrato
  assinatura_manual?: boolean
  drive_link_cliente?: string | null
  drive_link_master?: string | null
  clicksign_document_key?: string
  signatarios: Signatario[]
  created_at: string
  updated_at: string
}

export interface GerarPdfRequest {
  contratante_nome: string
  contratante_qualificacao?: string
  contratante_cpf_cnpj?: string
  contratante_endereco?: string
  contratante_email?: string
  objeto_tipo?: string
  objeto_texto_livre?: string
  valor_honorarios?: string
  valor_honorarios_num?: number | null
  valor_causa?: number | null
  data_vencimento?: string
  condicao_pagamento?: string
  percentual_exito?: string
  percentual_exito_num?: number | null
  data_contrato?: string
}

export interface ContratoCreate {
  cliente_id: string
  processo_id?: string
  titulo: string
  descricao?: string
}

export interface SignatarioCreate {
  nome: string
  email: string
  papel: PapelSignatario
}

export const contratosApi = {
  listar: (params?: { cliente_id?: string }) =>
    api.get<Contrato[]>('/contratos/', { params }).then((r) => r.data),

  criar: (data: ContratoCreate) =>
    api.post<Contrato>('/contratos/', data).then((r) => r.data),

  obter: (id: string) =>
    api.get<Contrato>(`/contratos/${id}`).then((r) => r.data),

  atualizar: (id: string, data: Partial<ContratoCreate>) =>
    api.patch<Contrato>(`/contratos/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/contratos/${id}`),

  uploadPdfs: (id: string, files: File[]) => {
    const form = new FormData()
    for (const f of files) form.append('arquivos', f)
    return api.post<Contrato>(`/contratos/${id}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  removerArquivo: (id: string, filename: string) =>
    api.delete<Contrato>(`/contratos/${id}/arquivo`, { params: { filename } }).then((r) => r.data),

  verArquivoUrl: (id: string, filename: string) =>
    `/api/contratos/${id}/arquivo/${encodeURIComponent(filename)}?token=${encodeURIComponent(getToken() ?? '')}`,

  downloadAssinadoUrl: (id: string) =>
    `/api/contratos/${id}/download-assinado?token=${encodeURIComponent(getToken() ?? '')}`,

  gerarPdf: (id: string, data: GerarPdfRequest) =>
    api.post<Contrato>(`/contratos/${id}/gerar-pdf`, data).then((r) => r.data),

  adicionarSignatario: (id: string, data: SignatarioCreate) =>
    api.post<Signatario>(`/contratos/${id}/signatarios`, data).then((r) => r.data),

  removerSignatario: (contratoId: string, sigId: string) =>
    api.delete(`/contratos/${contratoId}/signatarios/${sigId}`),

  enviar: (id: string) =>
    api.post<Contrato>(`/contratos/${id}/enviar`).then((r) => r.data),

  cancelar: (id: string) =>
    api.post<Contrato>(`/contratos/${id}/cancelar`).then((r) => r.data),

  confirmarAssinatura: (id: string) =>
    api.post<Contrato>(`/contratos/${id}/confirmar-assinatura`).then((r) => r.data),

  finalizarAssinadoManual: (id: string) =>
    api.post<Contrato>(`/contratos/${id}/finalizar-assinado-manual`).then((r) => r.data),

  sincronizarStatus: (id: string) =>
    api.post<Contrato>(`/contratos/${id}/sincronizar-status`).then((r) => r.data),

  pastaMestra: () =>
    api.get<{ link: string | null }>('/contratos/pasta-mestra').then((r) => r.data),
}
