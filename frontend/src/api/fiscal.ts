import api from './client'

// ─── Types ────────────────────────────────────────────────────────────────────

export type StatusNF = 'rascunho' | 'emitida' | 'cancelada' | 'erro'

export interface EnderecoIn {
  logradouro: string
  numero: string
  bairro: string
  cod_municipio: string
  cep: string
  complemento?: string
}

export interface EmitirNFSeIn {
  intermediario?: IntermediarioIn
  tomador_no_exterior?: boolean
  natureza_operacao?: string
  regime_tributario?: string
  reg_apuracao_sn?: string
  iss_retido?: boolean
  contrato_id?: string
  competencia: string            // YYYY-MM
  tomador_cpf_cnpj: string
  tomador_nome: string
  tomador_email?: string
  tomador_telefone?: string
  tomador_endereco?: EnderecoIn
  descricao_servico: string
  cod_tributacao_nacional?: string
  valor_servicos: number
  retencao_ir?: number
  retencao_inss?: number
  retencao_csll?: number
  retencao_cofins?: number
  retencao_pis?: number
  ibs_valor?: number
  cbs_valor?: number
  honorario_id?: string
  recebimento_id?: string
  serie?: string
}

export interface NotaFiscalResumo {
  id: string
  numero_nfse?: string
  competencia: string
  data_emissao?: string
  tomador_nome: string
  valor_servicos: number
  valor_liquido: number
  status: StatusNF
  honorario_id?: string
}

export interface NotaFiscalOut {
  id: string
  numero_nfse?: string
  chave_acesso?: string
  serie: string
  competencia: string
  data_emissao?: string
  prestador_cnpj: string
  tomador_cpf_cnpj: string
  tomador_nome: string
  tomador_email?: string
  cod_tributacao_nacional: string
  descricao_servico: string
  valor_servicos: number
  retencao_ir?: number
  retencao_inss?: number
  retencao_csll?: number
  retencao_cofins?: number
  retencao_pis?: number
  ibs_valor?: number
  cbs_valor?: number
  valor_liquido: number
  status: StatusNF
  erro_mensagem?: string
  xml_nfse?: string
  honorario_id?: string
  recebimento_id?: string
  created_at: string
  updated_at: string
}

export interface PreFillNFSeOut {
  competencia: string
  tomador_cpf_cnpj?: string
  tomador_nome?: string
  tomador_email?: string
  tomador_telefone?: string
  valor_servicos: number
  descricao_servico: string
  honorario_id: string
  recebimento_id?: string
  contrato_id?: string
}

export interface CodigoTributacao { codigo: string; label: string; descricao: string }
export interface OpcaoFiscal { valor: string; label: string; descricao: string }
export interface IntermediarioIn { nome: string; cpf_cnpj: string; inscricao_municipal?: string }

// ─── API calls ────────────────────────────────────────────────────────────────

export const fiscalApi = {
  listar: (params?: { status?: string; competencia?: string }) =>
    api.get<NotaFiscalResumo[]>('/fiscal/notas', { params }).then((r) => r.data),

  obter: (id: string) =>
    api.get<NotaFiscalOut>(`/fiscal/notas/${id}`).then((r) => r.data),

  emitir: (body: EmitirNFSeIn) =>
    api.post<NotaFiscalOut>('/fiscal/notas', body).then((r) => r.data),

  cancelar: (id: string, motivo: string) =>
    api.post<NotaFiscalOut>(`/fiscal/notas/${id}/cancelar`, { motivo }).then((r) => r.data),

  prefillDeHonorario: (honorarioId: string, recebimentoId?: string) =>
    api
      .get<PreFillNFSeOut>(`/fiscal/notas/prefill/honorario/${honorarioId}`, {
        params: recebimentoId ? { recebimento_id: recebimentoId } : undefined,
      })
      .then((r) => r.data),

  parametrosMunicipais: () =>
    api.get('/fiscal/parametros-municipais').then((r) => r.data),

  historicoCliente: (clienteId: string) =>
    api.get<NotaFiscalResumo[]>(`/fiscal/clientes/${clienteId}/historico`).then((r) => r.data),

  listarCodigosTributacao: () =>
    api.get<CodigoTributacao[]>('/fiscal/opcoes/codigos-tributacao').then((r) => r.data),

  listarNaturezaOperacao: () =>
    api.get<OpcaoFiscal[]>('/fiscal/opcoes/natureza-operacao').then((r) => r.data),

  listarRegApuracaoSN: () =>
    api.get<OpcaoFiscal[]>('/fiscal/opcoes/reg-apuracao-sn').then((r) => r.data),
}
