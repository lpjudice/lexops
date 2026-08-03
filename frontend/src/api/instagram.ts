import api from './client'

export type Formato = 'carrossel' | 'estatico'
export type TipoSlide = 'capa' | 'conteudo' | 'fechamento'
export type FonteTipo = 'insight' | 'publicacao' | 'andamento' | 'peca' | 'tese' | 'evergreen'
export type StatusSugestao = 'sugerido' | 'aprovado' | 'rejeitado' | 'publicado'

export type Layout =
  | 'capa_teal' | 'capa_offwhite' | 'capa_split' | 'capa_cream' | 'capa_keyword'
  | 'editorial' | 'numero' | 'icones' | 'citacao' | 'imagem'
  | 'fechamento'

export type IconeNome =
  | 'usuario' | 'balanca' | 'check' | 'escudo' | 'casa' | 'familia'
  | 'documento' | 'acordo' | 'grafico' | 'engrenagem' | 'cofre' | 'arvore'

export interface IconeItem { icone: IconeNome; label: string }

export interface SlideBlock {
  tipo: TipoSlide
  layout: Layout
  kicker?: string | null
  titulo?: string | null
  frase?: string | null
  numero?: string | null
  citacao?: string | null
  icones?: IconeItem[]
  imagem_hint?: string | null
  destaque?: string | null
  cta?: string | null
}

export interface Sugestao {
  id: string
  titulo: string
  tema: string
  formato: Formato
  tema_capa: string
  slides: SlideBlock[]
  legenda: string
  hashtags: string
  fonte_tipo: FonteTipo
  fonte_ref?: string | null
  motivo_ia: string
  status: StatusSugestao
  data_sugerida?: string | null
  enviado_assessoria_em?: string | null
  data_geracao: string
  created_at: string
  updated_at: string
}

export interface GerarResponse {
  criadas: number
  sugestoes: Sugestao[]
  aviso?: string | null
}

export interface SugestaoUpdate {
  status?: StatusSugestao
  data_sugerida?: string | null
  titulo?: string
  legenda?: string
  hashtags?: string
  slides?: SlideBlock[]
}

export interface EnviarAssessoriaResponse {
  enviado_para: string[]
  enviado_assessoria_em: string
}

export interface InstagramConfig {
  assessoria_emails: string
}

export const instagramApi = {
  listar: (status?: StatusSugestao) =>
    api
      .get<Sugestao[]>('/instagram/sugestoes', { params: status ? { status } : undefined })
      .then((r) => r.data),

  gerar: (quantidade = 3, formato?: Formato) =>
    api
      .post<GerarResponse>(
        '/instagram/gerar',
        { quantidade, formato },
        { timeout: 180000 }, // geração pode levar mais que o default de 30s
      )
      .then((r) => r.data),

  atualizar: (id: string, patch: SugestaoUpdate) =>
    api.patch<Sugestao>(`/instagram/sugestoes/${id}`, patch).then((r) => r.data),

  excluir: (id: string) => api.delete(`/instagram/sugestoes/${id}`).then(() => undefined),

  enviarAssessoria: (id: string, emails?: string[], observacao?: string) =>
    api
      .post<EnviarAssessoriaResponse>(`/instagram/sugestoes/${id}/enviar-assessoria`, {
        emails: emails && emails.length ? emails : undefined,
        observacao: observacao || undefined,
      })
      .then((r) => r.data),

  ajustar: (id: string, instrucao: string, slide_index?: number) =>
    api
      .post<Sugestao>(
        `/instagram/sugestoes/${id}/ajustar`,
        { instrucao, slide_index: slide_index ?? null },
        { timeout: 120000 },
      )
      .then((r) => r.data),

  obterConfig: () => api.get<InstagramConfig>('/instagram/config').then((r) => r.data),

  salvarConfig: (assessoria_emails: string) =>
    api.put<InstagramConfig>('/instagram/config', { assessoria_emails }).then((r) => r.data),

  buscarPublico: (id: string) =>
    api.get<CardPublico>(`/publico/instagram/${id}`).then((r) => r.data),
}

export interface CardPublico {
  id: string
  titulo: string
  formato: Formato
  slides: SlideBlock[]
  legenda: string
  hashtags: string
  status: StatusSugestao
  data_sugerida?: string | null
}
