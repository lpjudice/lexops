import api from './client'

export interface TemplateDescricao { tipo: string; label: string; texto: string }
export interface CodigoFavorito { codigo: string; label: string; descricao?: string }

export interface ConfigFiscal {
  // Emitente
  razao_social: string
  cnpj: string
  inscricao_municipal?: string
  cnae?: string
  endereco?: string
  municipio_ibge: string
  municipio_nome: string
  uf: string
  email_fiscal?: string
  telefone_fiscal?: string
  regime_tributario: string
  // Bases
  aliquota_iss: number
  regime_especial: string
  anexo_simples: string
  rbt12?: number
  aliquota_efetiva_simples: number
  ret_ir_pct: number
  ret_inss_pct: number
  ret_csll_pct: number
  ret_pis_pct: number
  ret_cofins_pct: number
  iss_retido_padrao: boolean
  // IBS/CBS
  ibs_pct: number
  cbs_pct: number
  piloto_ibscbs: boolean
  // Contabilidade
  emails_contador: string[]
  email_master?: string
  dia_envio_relatorio: number
  enviar_relatorio_auto: boolean
  // Numeração
  serie_padrao: string
  // Catálogos
  codigos_favoritos: CodigoFavorito[]
  templates_descricao: TemplateDescricao[]
  // DANFSe
  rodape_danfse?: string
  // Calculados (read-only)
  aliquota_simples_sugerida?: number
  faixa_simples?: string
  updated_at?: string
}

export const configFiscalApi = {
  obter: () => api.get<ConfigFiscal>('/config-fiscal').then((r) => r.data),
  salvar: (data: ConfigFiscal) => api.put<ConfigFiscal>('/config-fiscal', data).then((r) => r.data),
}
