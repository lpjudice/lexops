import api from './client'

export type StatusInformativo = 'rascunho' | 'primeiro_draft' | 'revisado' | 'publicado'

export interface Informativo {
  id: string
  mes_referencia: string
  titulo: string
  tema_resumido?: string | null
  tema_sugestao_id?: string | null
  status: StatusInformativo
  responsavel_id?: string | null
  google_doc_id?: string | null
  google_doc_link?: string | null
  conteudo_texto?: string | null
  paginas_estimadas?: number | null
  citacoes_validadas: Record<string, unknown>[]
  arquivos_referencia: { nome: string; link_drive: string; tipo: string }[]
  drive_folder_link?: string | null
  drive_pdf_link?: string | null
  data_prazo_draft?: string | null
  data_prazo_final?: string | null
  lembrete_draft_enviado: boolean
  lembrete_final_enviado: boolean
  publicado_em?: string | null
  created_at: string
  updated_at: string
}

export interface InformativoCriar {
  mes_referencia: string
  titulo: string
  responsavel_id?: string | null
  tema_resumido?: string | null
  tema_sugestao_id?: string | null
}

export interface InformativoAtualizar {
  titulo?: string
  tema_resumido?: string | null
  responsavel_id?: string | null
  status?: StatusInformativo
}

export const informativosApi = {
  listar: () => api.get<Informativo[]>('/informativos').then((r) => r.data),

  obter: (id: string) => api.get<Informativo>(`/informativos/${id}`).then((r) => r.data),

  responsavelPadrao: () =>
    api.get<{ id: string; nome: string; email: string | null } | null>('/informativos/responsavel-padrao').then((r) => r.data),

  criar: (data: InformativoCriar) => api.post<Informativo>('/informativos', data).then((r) => r.data),

  atualizar: (id: string, data: InformativoAtualizar) =>
    api.patch<Informativo>(`/informativos/${id}`, data).then((r) => r.data),

  excluir: (id: string) => api.delete(`/informativos/${id}`),

  uploadArquivo: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<Informativo>(`/informativos/${id}/upload`, form).then((r) => r.data)
  },

  sincronizarDoc: (id: string) =>
    api.post<{ conteudo_texto: string }>(`/informativos/${id}/sincronizar-doc`).then((r) => r.data),

  validarCitacoes: (id: string) =>
    api.post<{ citacoes: Record<string, unknown>[] }>(`/informativos/${id}/validar-citacoes`).then((r) => r.data),

  publicar: (id: string) =>
    api.post<{ paginas: number; aviso: string | null; pdf_link: string | null }>(`/informativos/${id}/publicar`).then((r) => r.data),

  previewHtml: (id: string) =>
    api.get<string>(`/informativos/${id}/preview-html`, { responseType: 'text' }).then((r) => r.data),
}
