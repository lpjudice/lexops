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
  doc_url?: string | null
}

export interface PublicacaoPendente {
  id: string
  fonte: string
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
  peca_doc_url: string | null
  rejeitada: boolean
  prazo_id: string | null
  tarefas_criadas: { id: string; titulo: string; responsavel: string | null }[]
}

export const despachoApi = {
  listarPendentes: () => api.get<PublicacaoPendente[]>('/despacho/pendentes').then((r) => r.data),

  listarTratadas: (params?: { data_inicio?: string; data_fim?: string; dias?: number }) =>
    api.get<PublicacaoPendente[]>('/despacho/tratadas', { params }).then((r) => r.data),

  obter: (id: string) => api.get<PublicacaoPendente>(`/despacho/${id}`).then((r) => r.data),

  confirmar: (id: string, processoId: string | null, confirmado: boolean) =>
    api.post(`/despacho/${id}/confirmar`, { processo_id: processoId, confirmado }).then((r) => r.data),

  rejeitar: (id: string) => api.post(`/despacho/${id}/rejeitar`).then((r) => r.data),

  reverter: (id: string) => api.post(`/despacho/${id}/reverter`).then((r) => r.data),

  sugerir: (id: string) =>
    api.post<SugestaoAcao>(`/despacho/${id}/sugerir`, undefined, { timeout: 90000 }).then((r) => r.data),

  gerarPeca: (id: string, opcaoPrazo: OpcaoPrazo, promptExtra: string) =>
    // IA (Opus) + cópia do timbrado + 2 chamadas ao Docs API somadas podem
    // passar dos 30s padrão — isso já aconteceu e o front achou que tinha
    // falhado quando na verdade só demorou (a peça foi criada normalmente).
    api.post<PecaGerada>(`/despacho/${id}/gerar-peca`, { opcao_prazo: opcaoPrazo, prompt_extra: promptExtra }, { timeout: 90000 }).then((r) => r.data),

  aprovar: (id: string, body: {
    criar_prazo?: boolean
    peca_necessaria?: string | null
    dias_prazo?: number | null
    tipo_contagem?: string
    responsavel_prazo?: string | null
    tarefas?: TarefaSugerida[]
  }) => api.post<{ prazo_id?: string; tarefa_ids?: string[]; ok: boolean }>(`/despacho/${id}/aprovar`, body).then((r) => r.data),
}
