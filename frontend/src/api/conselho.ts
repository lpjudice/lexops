import api from './client'

export type CategoriaDiretriz = 'operacional' | 'juridico' | 'comercial' | 'parcerias'
export type StatusDiretriz = 'Não iniciado' | 'Em andamento' | 'Bloqueado' | 'Concluído' | 'Atrasado'
export type TipoParceiro = 'Advogado' | 'Contador' | 'Assessor de investimentos' | 'Outro'
export type StatusParceiro = 'Quente' | 'Frio' | 'Reativado'

export interface Subtask {
  id: string
  texto: string
  concluida: boolean
  ordem: number
}

export interface Anexo {
  id: string
  nome_arquivo: string
  storage_path?: string | null
  created_at: string
}

export interface Diretriz {
  id: string
  categoria: CategoriaDiretriz
  titulo: string
  descricao?: string | null
  prazo?: string | null
  status: StatusDiretriz
  notas?: string | null
  created_at: string
  updated_at: string
  subtasks: Subtask[]
  anexos: Anexo[]
}

export interface DiretrizCreate {
  categoria: CategoriaDiretriz
  titulo: string
  descricao?: string
  prazo?: string
  status?: StatusDiretriz
  notas?: string
  subtasks?: { texto: string; concluida?: boolean; ordem?: number }[]
}

export interface PipelineItem {
  id: string
  nome: string
  origem?: string | null
  tema?: string | null
  estagio: string
  ultimo_contato?: string | null
  proxima_acao?: string | null
  proxima_data?: string | null
  ticket?: number | null
  probabilidade?: number | null
  created_at: string
  updated_at: string
}

export interface PipelineCreate {
  nome: string
  origem?: string
  tema?: string
  estagio?: string
  ultimo_contato?: string
  proxima_acao?: string
  proxima_data?: string
  ticket?: number
  probabilidade?: number
}

export interface ContatoNota {
  id: string
  contato_id: string
  evento_id?: string | null
  evento_nome?: string | null
  texto: string
  data?: string | null
  created_at: string
}

export interface Contato {
  id: string
  primeiro_nome: string
  sobrenome?: string | null
  empresa?: string | null
  email?: string | null
  whatsapp?: string | null
  mensagem_global?: string | null
  created_at: string
  updated_at: string
  notas: ContatoNota[]
  eventos: string[]
}

export interface ContatoCreate {
  primeiro_nome: string
  sobrenome?: string
  empresa?: string
  email?: string
  whatsapp?: string
  mensagem_global?: string
  evento_id?: string
}

export interface Convidado {
  id: string
  evento_id: string
  contato_id: string
  presenca_confirmada: boolean
  participacao_confirmada: boolean
  recusou: boolean
  pendente: boolean
  pendente_obs?: string | null
  followup_data?: string | null
  mensagem_pessoal?: string | null
  contato: Contato
}

export interface Evento {
  id: string
  nome: string
  data?: string | null
  cohost?: string | null
  custo?: number | null
  receita?: number | null
  reunioes?: number | null
  propostas?: number | null
  fechados?: number | null
  mensagem_master?: string | null
  dias_lembrete: number
  created_at: string
  updated_at: string
  convidados: Convidado[]
}

export interface EventoCreate {
  nome: string
  data?: string
  cohost?: string
  custo?: number
  receita?: number
  mensagem_master?: string
  dias_lembrete?: number
}

export interface Parceiro {
  id: string
  nome: string
  tipo: TipoParceiro
  status: StatusParceiro
  ultimo_encaminhamento?: string | null
  plano?: string | null
  proximo_contato?: string | null
  created_at: string
  updated_at: string
}

export interface ParceiroCreate {
  nome: string
  tipo: TipoParceiro
  status?: StatusParceiro
  ultimo_encaminhamento?: string
  plano?: string
  proximo_contato?: string
}

export interface LogDiario {
  id: string
  data: string
  numero: number
  nota?: string | null
  created_at: string
}

export interface Metricas {
  media_logs_7d: number
  total_contatos: number
  contatos_participaram_ao_menos_uma_vez: number
  contatos_reconvidados: number
  contatos_reiterados: number
}

export interface AnexoLib {
  id: string
  nome_arquivo: string
  content_type?: string | null
  created_at: string
}

export type ModoDisparo = 'individual' | 'bcc_unico'

export interface DispararEmailRequest {
  destinatarios: { contato_id: string; evento_id?: string }[]
  assunto: string
  corpo_template: string
  modo: ModoDisparo
  evento_nome?: string
  anexo_id?: string
}

export interface DisparoResultadoItem {
  contato_id: string
  nome: string
  email?: string | null
  sucesso: boolean
  erro?: string | null
}

export interface DispararEmailResponse {
  enviado_por: string
  resultados: DisparoResultadoItem[]
}

export const conselhoApi = {
  // Diretrizes
  listarDiretrizes: (categoria?: string) =>
    api.get<Diretriz[]>('/conselho/diretrizes', { params: { categoria } }).then((r) => r.data),
  criarDiretriz: (data: DiretrizCreate) =>
    api.post<Diretriz>('/conselho/diretrizes', data).then((r) => r.data),
  atualizarDiretriz: (id: string, data: Partial<DiretrizCreate>) =>
    api.patch<Diretriz>(`/conselho/diretrizes/${id}`, data).then((r) => r.data),
  deletarDiretriz: (id: string) => api.delete(`/conselho/diretrizes/${id}`),
  addSubtask: (diretrizId: string, texto: string) =>
    api.post<Diretriz>(`/conselho/diretrizes/${diretrizId}/subtasks`, null, { params: { texto } }).then((r) => r.data),
  toggleSubtask: (subtaskId: string, concluida: boolean) =>
    api.patch<Diretriz>(`/conselho/diretrizes/subtasks/${subtaskId}`, null, { params: { concluida } }).then((r) => r.data),
  editarSubtask: (subtaskId: string, texto: string) =>
    api.patch<Diretriz>(`/conselho/diretrizes/subtasks/${subtaskId}`, null, { params: { texto } }).then((r) => r.data),
  deletarSubtask: (subtaskId: string) => api.delete(`/conselho/diretrizes/subtasks/${subtaskId}`),

  // Pipeline
  listarPipeline: () => api.get<PipelineItem[]>('/conselho/pipeline').then((r) => r.data),
  criarPipeline: (data: PipelineCreate) => api.post<PipelineItem>('/conselho/pipeline', data).then((r) => r.data),
  atualizarPipeline: (id: string, data: Partial<PipelineCreate>) =>
    api.patch<PipelineItem>(`/conselho/pipeline/${id}`, data).then((r) => r.data),
  deletarPipeline: (id: string) => api.delete(`/conselho/pipeline/${id}`),

  // Contatos
  listarContatos: (params?: { evento_id?: string; presenca_confirmada?: boolean; participacao_confirmada?: boolean }) =>
    api.get<Contato[]>('/conselho/contatos', { params }).then((r) => r.data),
  buscarContatos: (q: string) => api.get<Contato[]>('/conselho/contatos/buscar', { params: { q } }).then((r) => r.data),
  criarContato: (data: ContatoCreate) => api.post<Contato>('/conselho/contatos', data).then((r) => r.data),
  atualizarContato: (id: string, data: Partial<ContatoCreate>) =>
    api.patch<Contato>(`/conselho/contatos/${id}`, data).then((r) => r.data),
  deletarContato: (id: string) => api.delete(`/conselho/contatos/${id}`),
  addNotaContato: (contatoId: string, texto: string, eventoId?: string) =>
    api.post<Contato>(`/conselho/contatos/${contatoId}/notas`, { texto, evento_id: eventoId }).then((r) => r.data),
  deletarNotaContato: (notaId: string) => api.delete(`/conselho/contatos/notas/${notaId}`),

  // Eventos
  listarEventos: () => api.get<Evento[]>('/conselho/eventos').then((r) => r.data),
  criarEvento: (data: EventoCreate) => api.post<Evento>('/conselho/eventos', data).then((r) => r.data),
  obterEvento: (id: string) => api.get<Evento>(`/conselho/eventos/${id}`).then((r) => r.data),
  atualizarEvento: (id: string, data: Partial<EventoCreate & { reunioes: number; propostas: number; fechados: number }>) =>
    api.patch<Evento>(`/conselho/eventos/${id}`, data).then((r) => r.data),
  deletarEvento: (id: string) => api.delete(`/conselho/eventos/${id}`),
  addConvidado: (eventoId: string, contatoId: string) =>
    api.post<Evento>(`/conselho/eventos/${eventoId}/convidados`, { contato_id: contatoId }).then((r) => r.data),
  atualizarConvidado: (convidadoId: string, data: { presenca_confirmada?: boolean; participacao_confirmada?: boolean; recusou?: boolean; pendente?: boolean; pendente_obs?: string; followup_data?: string | null; mensagem_pessoal?: string }) =>
    api.patch<Convidado>(`/conselho/eventos/convidados/${convidadoId}`, data).then((r) => r.data),
  removerConvidado: (convidadoId: string) => api.delete(`/conselho/eventos/convidados/${convidadoId}`),

  // Parceiros
  listarParceiros: () => api.get<Parceiro[]>('/conselho/parceiros').then((r) => r.data),
  criarParceiro: (data: ParceiroCreate) => api.post<Parceiro>('/conselho/parceiros', data).then((r) => r.data),
  atualizarParceiro: (id: string, data: Partial<ParceiroCreate>) =>
    api.patch<Parceiro>(`/conselho/parceiros/${id}`, data).then((r) => r.data),
  deletarParceiro: (id: string) => api.delete(`/conselho/parceiros/${id}`),

  // Logs / Métricas
  listarLogs: () => api.get<LogDiario[]>('/conselho/logs').then((r) => r.data),
  criarLog: (data: { data: string; numero: number; nota?: string }) =>
    api.post<LogDiario>('/conselho/logs', data).then((r) => r.data),
  deletarLog: (id: string) => api.delete(`/conselho/logs/${id}`),
  obterMetricas: () => api.get<Metricas>('/conselho/metricas').then((r) => r.data),

  // IA
  melhorarIA: (campo: string, texto: string) =>
    api.post<{ texto: string }>('/conselho/ia/melhorar', { campo, texto }).then((r) => r.data),

  // Anexos
  listarAnexos: () => api.get<AnexoLib[]>('/conselho/anexos').then((r) => r.data),
  uploadAnexo: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<AnexoLib>('/conselho/anexos', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data)
  },
  deletarAnexo: (id: string) => api.delete(`/conselho/anexos/${id}`),

  // Disparo de e-mail real
  dispararEmail: (data: DispararEmailRequest) =>
    api.post<DispararEmailResponse>('/conselho/disparar-email', data).then((r) => r.data),
}
