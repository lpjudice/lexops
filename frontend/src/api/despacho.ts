import api from './client'

export type Confianca = 'alta' | 'media' | 'baixa' | 'sem_vinculo'

export interface OpcaoPrazo {
  label: string
  peca_necessaria: string
  dias_prazo: number
  tipo_contagem: 'uteis' | 'corridos'
}

export interface TarefaSugerida {
  titulo: string
  responsavel: string | null
}

export interface SugestaoAcao {
  resumo_raciocinio: string
  requer_prazo: boolean
  opcoes_prazo: OpcaoPrazo[]
  tarefas_sugeridas: TarefaSugerida[]
  rascunho_sugerido: string | null
}

export interface PecaGerada {
  titulo_peca: string
  enderecamento: string
  qualificacao: string
  paragrafos: string[]
  fechamento: string
  itens_faltantes: string[]
}

export interface PublicacaoPendente {
  id: string
  data_publicacao: string | null
  tribunal: string | null
  tipo_ato: string | null
  texto_resumo: string | null
  numero_cnj: string | null
  cliente_nome_pub: string | null
  match_oab: string | null
  confianca: Confianca
  processo_id: string | null
  processo_numero_cnj: string | null
  cliente_id: string | null
  cliente_nome: string | null
  vinculo_confirmado: boolean
  sugestao_acao: SugestaoAcao | null
  peca_gerada: PecaGerada | null
}

export const despachoApi = {
  listarPendentes: () => api.get<PublicacaoPendente[]>('/despacho/pendentes').then((r) => r.data),

  confirmar: (id: string, processoId: string | null, confirmado: boolean) =>
    api.post(`/despacho/${id}/confirmar`, { processo_id: processoId, confirmado }).then((r) => r.data),

  rejeitar: (id: string) => api.post(`/despacho/${id}/rejeitar`).then((r) => r.data),

  sugerir: (id: string) => api.post<SugestaoAcao>(`/despacho/${id}/sugerir`).then((r) => r.data),

  gerarPeca: (id: string, opcaoPrazo: OpcaoPrazo, promptExtra: string) =>
    api.post<PecaGerada>(`/despacho/${id}/gerar-peca`, { opcao_prazo: opcaoPrazo, prompt_extra: promptExtra }).then((r) => r.data),

  aprovar: (id: string, body: {
    criar_prazo?: boolean
    peca_necessaria?: string | null
    dias_prazo?: number | null
    tipo_contagem?: string
    tarefas?: TarefaSugerida[]
  }) => api.post(`/despacho/${id}/aprovar`, body).then((r) => r.data),
}
