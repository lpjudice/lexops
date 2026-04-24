import api from './client'

export type TipoHonorario = 'fixo' | 'percentual' | 'exito'
export type StatusHonorario = 'pendente' | 'parcial' | 'pago' | 'cancelado'
export type FormaPagamento = 'pix' | 'ted' | 'boleto' | 'cheque' | 'dinheiro' | 'outro'

export interface Recebimento {
  id: string
  honorario_id: string
  valor: number
  data_recebimento: string
  forma_pagamento: FormaPagamento
  observacao?: string
}

export interface Honorario {
  id: string
  cliente_id: string
  processo_id?: string
  descricao: string
  tipo: TipoHonorario
  valor_total: number
  status: StatusHonorario
  total_recebido: number
  saldo_pendente: number
  data_contrato?: string
  data_vencimento?: string
  observacoes?: string
  valor_causa?: number
  percentual_exito?: number
  data_estimada_sentenca?: string
  contrato_id?: string | null
  pendente_assinatura?: boolean
  contrato_orfao?: boolean
  recebimentos: Recebimento[]
  created_at: string
  updated_at: string
}

export interface HonorarioCreate {
  cliente_id: string
  processo_id?: string
  descricao: string
  tipo: TipoHonorario
  valor_total: number
  data_contrato?: string
  data_vencimento?: string
  observacoes?: string
  valor_causa?: number
  percentual_exito?: number
  data_estimada_sentenca?: string
}

export interface RecebimentoCreate {
  valor: number
  data_recebimento: string
  forma_pagamento: FormaPagamento
  observacao?: string
}

export interface ResumoFinanceiro {
  total_contratado: number
  total_recebido: number
  total_pendente: number
  total_vencido: number
  total_reembolsos_pendentes: number
  total_reembolsos_pagos: number
  projecao_exito: number
  a_vencer_30: number
  a_vencer_60: number
  a_vencer_90: number
  por_cliente: {
    cliente_id: string
    cliente_nome: string
    total_contratado: number
    total_recebido: number
    saldo_pendente: number
  }[]
  por_mes: {
    ano: number
    mes: number
    total_recebido: number
  }[]
}

export const financeiroApi = {
  listarHonorarios: (params?: { cliente_id?: string; status?: string; pendente_assinatura?: boolean }) =>
    api.get<Honorario[]>('/financeiro/honorarios/', { params }).then((r) => r.data),

  criarHonorario: (data: HonorarioCreate) =>
    api.post<Honorario>('/financeiro/honorarios/', data).then((r) => r.data),

  atualizarHonorario: (id: string, data: Partial<HonorarioCreate & { status: StatusHonorario; contrato_orfao: boolean }>) =>
    api.patch<Honorario>(`/financeiro/honorarios/${id}`, data).then((r) => r.data),

  deletarHonorario: (id: string) => api.delete(`/financeiro/honorarios/${id}`),

  adicionarRecebimento: (honorarioId: string, data: RecebimentoCreate) =>
    api.post<Recebimento>(`/financeiro/honorarios/${honorarioId}/recebimentos/`, data).then((r) => r.data),

  removerRecebimento: (honorarioId: string, recId: string) =>
    api.delete(`/financeiro/honorarios/${honorarioId}/recebimentos/${recId}`),

  resumo: () =>
    api.get<ResumoFinanceiro>('/financeiro/resumo/').then((r) => r.data),
}
