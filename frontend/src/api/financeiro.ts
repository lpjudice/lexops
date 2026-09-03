import api from './client'

export type TipoHonorario = 'fixo' | 'percentual' | 'exito'
export type StatusHonorario = 'pendente' | 'parcial' | 'pago' | 'cancelado'
export type FormaPagamento = 'pix' | 'ted' | 'boleto' | 'cheque' | 'dinheiro' | 'outro'
export type StatusParcela = 'pendente' | 'pago' | 'cancelado'

export interface Recebimento {
  id: string
  honorario_id: string
  parcela_id?: string | null
  valor: number
  data_recebimento: string
  forma_pagamento: FormaPagamento
  observacao?: string
}

export interface Parcela {
  id: string
  honorario_id: string
  numero: number
  valor: number
  data_vencimento: string
  status: StatusParcela
  data_pagamento?: string | null
  observacao?: string
  ultimo_lembrete_em?: string | null
}

/** Uma parcela no cronograma enviado ao criar o recebível. */
export interface ParcelaInput {
  numero: number
  valor: number
  data_vencimento: string
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
  cobranca_ativa?: boolean
  cobranca_email?: string | null
  cobranca_emails?: string[]
  recebimentos: Recebimento[]
  parcelas: Parcela[]
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
  contrato_id?: string | null
  cobranca_ativa?: boolean
  cobranca_emails?: string[]
  parcelas?: ParcelaInput[]
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

  // ── Parcelas ──
  adicionarParcela: (honorarioId: string, data: ParcelaInput) =>
    api.post<Parcela>(`/financeiro/honorarios/${honorarioId}/parcelas/`, data).then((r) => r.data),

  editarParcela: (parcelaId: string, data: Partial<Pick<ParcelaInput, 'valor' | 'data_vencimento' | 'observacao'>>) =>
    api.patch<Parcela>(`/financeiro/parcelas/${parcelaId}`, data).then((r) => r.data),

  removerParcela: (parcelaId: string) =>
    api.delete(`/financeiro/parcelas/${parcelaId}`),

  pagarParcela: (parcelaId: string, data: { data_recebimento?: string; forma_pagamento?: FormaPagamento; valor?: number; observacao?: string }) =>
    api.post<Parcela>(`/financeiro/parcelas/${parcelaId}/pagar`, data).then((r) => r.data),

  reabrirParcela: (parcelaId: string) =>
    api.post<Parcela>(`/financeiro/parcelas/${parcelaId}/reabrir`).then((r) => r.data),

  enviarCobranca: (honorarioId: string) =>
    api.post<{ enviados: number; pulados: number; erros: string[] }>(`/financeiro/honorarios/${honorarioId}/enviar-cobranca`).then((r) => r.data),

  resumo: () =>
    api.get<ResumoFinanceiro>('/financeiro/resumo/').then((r) => r.data),

  fluxoCaixa: () =>
    api.get<FluxoCaixa>('/financeiro/fluxo-caixa/').then((r) => r.data),
}

export interface FluxoEntrada {
  data: string
  descricao: string
  cliente: string
  valor: number
  forma: string
  origem: 'recebimento' | 'nf_so'
  nf_conciliada?: string | null
  nf_tomador?: string | null
  nf_id?: string
}
export interface FluxoSaida {
  data: string
  descricao: string
  fornecedor: string
  categoria: string
  valor: number
  eh_reembolso: boolean
}
export interface FluxoMes {
  competencia: string
  total: number
  total_saidas: number
  saldo: number
  entradas: FluxoEntrada[]
  saidas: FluxoSaida[]
}
export interface CreditoItem {
  tipo: 'honorario' | 'nf'
  descricao: string
  cliente: string
  valor: number
  vencimento?: string | null
  nf_id?: string
}
export interface FluxoCaixa {
  meses: FluxoMes[]
  credito_a_receber: {
    total: number
    honorarios_pendentes: number
    nfs_nao_pagas: number
    itens: CreditoItem[]
  }
}
