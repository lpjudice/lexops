import api from './client'

export interface FiltrosCreditos {
  categoria?: string[]; subcategoria?: string[]; classe?: string[]; devedor?: string[]; nivel_devedor?: string[]; credor?: string[]
  credor_q?: string; natureza_q?: string; q?: string
  intragrupo?: boolean; vencidos?: boolean; com_coobrigado?: boolean; no_organograma?: boolean
  valor_min?: number; valor_max?: number; venc_de?: string; venc_ate?: string; lote?: string
}

export interface Credito {
  id: string; linha: number | null
  devedor: string; devedor_cnpj: string | null; devedor_cnpj_fmt: string | null; devedor_cnpj_grupo: string | null; devedor_no_organograma: boolean; nivel_devedor: string | null
  credor: string; credor_cnpj: string | null; credor_cnpj_fmt: string | null; credor_email: string | null; credor_endereco: string | null
  credor_cnpj_grupo: string | null; intragrupo: boolean; nivel_credor: string | null
  natureza: string | null; classe: string | null; categoria: string; subcategoria: string | null
  valor_centavos: number; valor: string; data_base: string | null; vencimento: string | null; vencido: boolean
  coobrigados: string | null; pagina_pdf: number | null
}

export interface Quebra { chave: string; rotulo: string; n: number; valor_centavos: number; valor: string; pct: number }
export interface ResumoCreditos {
  total_centavos: number; total: string; n: number; devedoras: number; credores: number
  intragrupo: { n: number; valor_centavos: number; valor: string; pct: number }
  vencidos: { n: number; valor_centavos: number }
  com_coobrigado: { n: number; valor_centavos: number }
  fora_do_organograma: { n: number; valor_centavos: number }
  por_categoria: Quebra[]; por_classe: Quebra[]; por_devedora: Quebra[]; por_credor: Quebra[]; por_nivel_devedora: Quebra[]; por_origem: Quebra[]
}
export interface OpcoesCreditos {
  categorias: string[]; subcategorias: string[]; classes: string[]; niveis: string[]
  devedoras: { chave: string; rotulo: string }[]; credores: { chave: string; rotulo: string }[]
}
export type Dimensao = 'devedora' | 'credor' | 'categoria' | 'subcategoria' | 'classe' | 'origem' | 'nivel_devedora' | 'vencimento_mes'
export interface Pivot {
  linhas_dim: string; colunas_dim: string | null; total_centavos: number; outras_colunas: number; outras_linhas: number
  colunas: { chave: string; rotulo: string; valor_centavos: number; valor: string }[]
  linhas: { chave: string; rotulo: string; valor_centavos: number; valor: string; n: number; celulas: Record<string, { n: number; valor_centavos: number; valor: string }> }[]
}
export interface Lote { id: string; nome_arquivo: string | null; total_linhas: number; total_centavos: number; total: string; ativo: boolean; notas: string | null; importado_em: string }

export interface EmpresaGrupo {
  cnpj: string; cnpj_fmt: string; nome: string; nivel: string | null; descricao: string | null; origem: string; n_filhos: number
  deve_centavos: number; n_creditos: number; a_receber_centavos: number; intragrupo_deve_centavos: number
}
export interface Participacao { id: string; pai: string; filho: string; pct: number | null; tracejado: boolean; status: string; nota: string | null; origem: string }
export interface DividaIntragrupo {
  devedora: string; credora: string; valor_centavos: number; valor: string; n: number; categorias: { categoria: string; valor_centavos: number; valor: string }[]
}
export interface Organograma {
  resumo: { empresas: number; vinculos: number; raizes: number; com_divida: number; intragrupo_total_centavos: number; devedoras_fora_do_organograma: number }
  empresas: EmpresaGrupo[]; participacoes: Participacao[]; dividas_intragrupo: DividaIntragrupo[]; niveis: string[]
}

const base = (casoId: string) => `/autos-ia/casos/${casoId}/estrutura`
const params = (f: FiltrosCreditos) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(f)) {
    if (v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0)) continue
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x)); else p.set(k, String(v))
  }
  return p
}

export const estrutura = {
  creditos: (casoId: string, f: FiltrosCreditos = {}, extra: { ordem?: string; limite?: number; offset?: number } = {}) => {
    const p = params(f)
    Object.entries(extra).forEach(([k, v]) => v !== undefined && p.set(k, String(v)))
    return api.get<{ total: number; total_centavos: number; itens: Credito[] }>(`${base(casoId)}/creditos`, { params: p }).then((r) => r.data)
  },
  resumo: (casoId: string, f: FiltrosCreditos = {}) => api.get<ResumoCreditos>(`${base(casoId)}/creditos/resumo`, { params: params(f) }).then((r) => r.data),
  opcoes: (casoId: string) => api.get<OpcoesCreditos>(`${base(casoId)}/creditos/opcoes`).then((r) => r.data),
  agrupar: (casoId: string, linhas: Dimensao, colunas: Dimensao | '', f: FiltrosCreditos = {}) => {
    const p = params(f); p.set('linhas', linhas); p.set('colunas', colunas)
    return api.get<Pivot>(`${base(casoId)}/creditos/agrupar`, { params: p }).then((r) => r.data)
  },
  lotes: (casoId: string) => api.get<Lote[]>(`${base(casoId)}/creditos/lotes`).then((r) => r.data),
  importarPlanilha: (casoId: string, arquivo: File, notas?: string) => {
    const fd = new FormData(); fd.append('arquivo', arquivo); if (notas) fd.append('notas', notas)
    return api.post<Lote>(`${base(casoId)}/creditos/importar`, fd).then((r) => r.data)
  },
  ativarLote: (casoId: string, id: string) => api.post<Lote>(`${base(casoId)}/creditos/lotes/${id}/ativar`).then((r) => r.data),
  excluirLote: (casoId: string, id: string) => api.delete(`${base(casoId)}/creditos/lotes/${id}`).then((r) => r.data),
  organograma: (casoId: string) => api.get<Organograma>(`${base(casoId)}/organograma`).then((r) => r.data),
  importarOrganograma: (casoId: string, arquivo?: File) => {
    const fd = new FormData(); if (arquivo) fd.append('arquivo', arquivo)
    return api.post<{ empresas: number; empresas_novas: number; vinculos: number; vinculos_novos: number; vinculos_removidos: number; niveis_lidos: number; avisos: string[] }>(`${base(casoId)}/organograma/importar`, fd).then((r) => r.data)
  },
  atualizarParticipacao: (casoId: string, id: string, body: { pct?: number | null; status?: string; nota?: string | null }) =>
    api.patch<Participacao>(`${base(casoId)}/participacoes/${id}`, body).then((r) => r.data),
  criarParticipacao: (casoId: string, body: { pai: string; filho: string; pct?: number | null; tracejado?: boolean }) =>
    api.post<Participacao>(`${base(casoId)}/participacoes`, body).then((r) => r.data),
  atualizarEmpresa: (casoId: string, cnpj: string, body: { nome?: string; nivel?: string | null }) =>
    api.patch<{ cnpj: string; nome: string; nivel: string | null }>(`${base(casoId)}/empresas/${cnpj}`, body).then((r) => r.data),
}
