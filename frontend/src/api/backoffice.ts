import api from './client'

export interface RegimeBreakdown {
  das: number; pis: number; cofins: number; irpj: number; csll: number
  iss: number; ibs_bruto: number; cbs_bruto: number; credito_ibs: number
  credito_cbs: number; ibs_liquido: number; cbs_liquido: number
  inss_patronal: number; fgts: number; total_tributos: number; total_com_folha: number
}

export interface Regime {
  nome: string; slug: string; ranking: number
  carga_efetiva_pct: number; credito_cliente: number; obs: string
  breakdown: RegimeBreakdown
}

export interface Decisao {
  mes: string; vencedor: string
  regimes: Regime[]
  totais: {
    receita_total: number; folha_total: number; despesas_total: number
    despesas_elegiveis: number; credito_ibs: number; credito_cbs: number
    credito_total: number; retencoes_sofridas: number
  }
  premissas: {
    rbt12: number; aliquota_iss: number; ibs_saida_pct: number
    cbs_saida_pct: number; ibs_entrada_pct: number; cbs_entrada_pct: number
    credito_modo: string; override_ativo: boolean
  }
  nfs_sincronizadas: number
}

export interface Receita {
  id: string; cliente_nome: string; tipo_cliente: string
  valor: number; retencoes: number; credito_interesse: boolean
  modo_tributacao: string; is_manual: boolean; nota_fiscal_id: string | null
}

export interface Despesa {
  id: string; categoria: string; fornecedor: string; descricao: string | null
  valor: number; tem_nota: boolean; elegivel: boolean; base_legal: string | null
  status: string; last_check: string | null
  credito: { ibs: number; cbs: number; total: number }
}

export interface Folha {
  salarios: number; prolabore: number; inss_patronal: number
  rat: number; fgts: number; beneficios: number; outros: number
}

export interface Lancamentos {
  mes: string; receitas: Receita[]; folha: Folha; despesas: Despesa[]
}

export interface MesAnual {
  mes: string; vencedor: string; vencedor_nome: string
  receita_total: number; credito_total: number; carga_efetiva_pct: number
}

export interface RegraCredito {
  id: string; categoria: string; descricao: string | null; base_legal: string
  status: string; elegivel: boolean; last_check: string | null
  next_check: string | null; notas: string | null
}

export interface Fornecedor {
  id: string; nome: string; cnpj: string | null; categoria_padrao: string | null
}

export interface DespesaRecorrente {
  id: string; categoria: string; fornecedor: string; descricao: string | null
  valor_padrao: number; tem_nota: boolean; elegivel: boolean
}

export interface ParsedExpense {
  fornecedor: string; valor: number; data: string; descricao: string; categoria: string
}

export const backofficeApi = {
  decisao: (mes: string) =>
    api.get<Decisao>(`/backoffice/decisao/${mes}`).then(r => r.data),
  lancamentos: (mes: string) =>
    api.get<Lancamentos>(`/backoffice/lancamentos/${mes}`).then(r => r.data),
  anual: () =>
    api.get<MesAnual[]>('/backoffice/anual').then(r => r.data),
  regras: () =>
    api.get<RegraCredito[]>('/backoffice/regras').then(r => r.data),

  upsertFolha: (mes: string, data: Partial<Folha>) =>
    api.put(`/backoffice/folha/${mes}`, data).then(r => r.data),
  addDespesa: (mes: string, data: object) =>
    api.post(`/backoffice/despesas/${mes}`, data).then(r => r.data),
  patchDespesa: (id: string, data: object) =>
    api.patch(`/backoffice/despesas/${id}`, data).then(r => r.data),
  deleteDespesa: (id: string) =>
    api.delete(`/backoffice/despesas/${id}`).then(r => r.data),
  addReceita: (mes: string, data: object) =>
    api.post(`/backoffice/receitas/${mes}`, data).then(r => r.data),
  deleteReceita: (id: string) =>
    api.delete(`/backoffice/receitas/${id}`).then(r => r.data),
  upsertPremissas: (mes: string, data: object) =>
    api.put(`/backoffice/premissas/${mes}`, data).then(r => r.data),
  createRegra: (data: object) =>
    api.post('/backoffice/regras', data).then(r => r.data),
  patchRegra: (id: string, data: object) =>
    api.patch(`/backoffice/regras/${id}`, data).then(r => r.data),

  // Fornecedores
  fornecedores: () =>
    api.get<Fornecedor[]>('/backoffice/fornecedores').then(r => r.data),
  upsertFornecedor: (data: { nome: string; cnpj?: string; categoria_padrao?: string }) =>
    api.post('/backoffice/fornecedores', data).then(r => r.data),
  categorias: () =>
    api.get<string[]>('/backoffice/categorias').then(r => r.data),

  // Recorrentes
  recorrentes: () =>
    api.get<DespesaRecorrente[]>('/backoffice/recorrentes').then(r => r.data),
  createRecorrente: (data: object) =>
    api.post('/backoffice/recorrentes', data).then(r => r.data),
  patchRecorrente: (id: string, data: object) =>
    api.patch(`/backoffice/recorrentes/${id}`, data).then(r => r.data),
  deleteRecorrente: (id: string) =>
    api.delete(`/backoffice/recorrentes/${id}`).then(r => r.data),

  // Batch
  addDespesasBatch: (mes: string, items: object[]) =>
    api.post(`/backoffice/despesas/batch/${mes}`, items).then(r => r.data),

  // Parse extrato
  parseExtrato: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post<{ linhas: ParsedExpense[] }>('/backoffice/despesas/parse-extrato', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  // Sync NFs históricas
  syncNfsHistorico: () =>
    api.post('/backoffice/sync-nfs-historico').then(r => r.data),

  // Despesas por mês (para página dedicada)
  despesas: (mes: string) =>
    api.get<{ despesas: Despesa[]; premissas: Lancamentos['folha'] }>(`/backoffice/lancamentos/${mes}`)
      .then(r => ({ despesas: r.data.despesas })),
}
