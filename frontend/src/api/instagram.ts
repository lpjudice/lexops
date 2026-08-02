import api from './client'

export type Formato = 'carrossel' | 'estatico'
export type TemaCapa = 'A' | 'B' | 'C' | 'D'
export type Variante = 'dark' | 'light' | 'white' | 'cream'
export type TipoSlide = 'capa' | 'conteudo' | 'cta'
export type FonteTipo = 'insight' | 'publicacao' | 'andamento' | 'peca' | 'tese' | 'evergreen'
export type StatusSugestao = 'sugerido' | 'aprovado' | 'rejeitado' | 'publicado'

export interface CardBlock {
  destaque?: string | null
  texto: string
}

export interface SlideBlock {
  variante: Variante
  tipo: TipoSlide
  tag?: string | null
  titulo?: string | null
  subtitulo?: string | null
  corpo?: string | null
  bullets: string[]
  cards: CardBlock[]
  cta?: string | null
}

export interface Sugestao {
  id: string
  titulo: string
  tema: string
  formato: Formato
  tema_capa: TemaCapa
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

  obterConfig: () => api.get<InstagramConfig>('/instagram/config').then((r) => r.data),

  salvarConfig: (assessoria_emails: string) =>
    api.put<InstagramConfig>('/instagram/config', { assessoria_emails }).then((r) => r.data),
}
