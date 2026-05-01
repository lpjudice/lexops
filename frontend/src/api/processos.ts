import api from './client'

export type EstadoProcesso = 'ES' | 'SP' | 'AM' | 'RJ' | 'outro'
export type FaseProcesso =
  | 'conhecimento'
  | 'recursal'
  | 'execucao'
  | 'cumprimento_sentenca'
  | 'outro'
export type StatusProcesso = 'ativo' | 'suspenso' | 'arquivado' | 'encerrado'
export type PoloProcesso =
  | 'autor' | 'reu' | 'litisconsorte' | 'assistente' | 'opoente'
  | 'interveniente' | 'perito' | 'avaliador' | 'interessado'
  | 'embargante' | 'embargado' | 'apelante' | 'apelado'
  | 'agravante' | 'agravado' | 'recorrente' | 'recorrido'
  | 'outro'

export type SistemaJuridico = 'esaj' | 'projudi' | 'ejud' | 'pje'
export type GrauProcesso = '1grau' | '2grau' | 'stj' | 'stf' | 'outro'
export type OrgaoJulgadorTipo = 'vara' | 'camara' | 'turma' | 'pleno' | 'orgao_especial' | 'gabinete' | 'secao' | 'outro'

export interface ProcessoClienteRef {
  cliente_id: string
  nome: string
  polo?: string | null
  principal?: boolean
}

export interface Processo {
  id: string
  numero_cnj: string
  cliente_id: string
  vara?: string
  comarca?: string
  estado: EstadoProcesso
  tribunal?: string
  materia?: string
  fase?: FaseProcesso
  status: StatusProcesso
  objeto?: string
  polo?: PoloProcesso
  orgao_julgador_tipo?: OrgaoJulgadorTipo | null
  serventia?: string | null
  foro?: string | null
  sistema_juridico?: SistemaJuridico | null
  grau?: GrauProcesso | null
  grau_texto?: string | null
  clientes_litisconsorcio?: ProcessoClienteRef[]
  // Sync fields
  ultimo_andamento_data?: string | null
  ultimo_andamento_desc?: string | null
  ultimo_check?: string | null
  tentativas_falha?: number
  andamentos_nao_lidos?: number
  created_at: string
  updated_at: string
}

export interface ProcessoClienteIn {
  cliente_id: string
  polo?: string | null
  principal?: boolean
}

export interface ProcessoCreate {
  numero_cnj: string
  cliente_id: string
  vara?: string
  comarca?: string
  estado: EstadoProcesso
  tribunal?: string
  materia?: string
  fase?: FaseProcesso
  status?: StatusProcesso
  objeto?: string
  polo?: PoloProcesso
  orgao_julgador_tipo?: OrgaoJulgadorTipo | null
  serventia?: string | null
  foro?: string | null
  sistema_juridico?: SistemaJuridico | null
  grau?: GrauProcesso | null
  grau_texto?: string | null
  clientes_litisconsorcio?: ProcessoClienteIn[]
}


export interface ProcessoJusbrPrefill {
  numero_cnj: string
  estado: EstadoProcesso
  tribunal?: string | null
  vara?: string | null
  orgao_julgador_tipo?: OrgaoJulgadorTipo | null
  comarca?: string | null
  materia?: string | null
  objeto?: string | null
  serventia?: string | null
  foro?: string | null
  sistema_juridico?: SistemaJuridico | null
  grau?: GrauProcesso | null
  grau_texto?: string | null
  status?: StatusProcesso
  polo?: PoloProcesso | null
  cliente_nome_sugerido?: string | null
  parte_ativa_principal?: string | null
  parte_passiva_principal?: string | null
  resumo_encontrado?: string | null
}

export interface Documento {
  filename: string
  size: number
}

export interface ChatMessage {
  role: 'user' | 'model'
  content: string
}

export const processosApi = {
  listar: (params?: { cliente_id?: string; status?: string; estado?: string }) =>
    api.get<Processo[]>('/processos/', { params }).then((r) => r.data),
  criar: (data: ProcessoCreate) =>
    api.post<Processo>('/processos/', data).then((r) => r.data),
  obter: (id: string) => api.get<Processo>(`/processos/${id}`).then((r) => r.data),
  atualizar: (id: string, data: Partial<ProcessoCreate>) =>
    api.patch<Processo>(`/processos/${id}`, data).then((r) => r.data),
  deletar: (id: string) => api.delete(`/processos/${id}`),

  preencherViaJusbr: (numeroCnj: string) =>
    api.get<ProcessoJusbrPrefill>(`/processos/preencher-jusbr/${encodeURIComponent(numeroCnj)}`).then((r) => r.data),

  uploadPdf: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{ filename: string; size: number; drive_link: string | null }>(`/processos/${id}/upload-pdf`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
  listarDocumentos: (id: string) =>
    api.get<Documento[]>(`/processos/${id}/documentos`).then((r) => r.data),
  removerDocumento: (id: string, filename: string) =>
    api.delete(`/processos/${id}/documentos/${filename}`),

  chat: (id: string, pergunta: string, historico: ChatMessage[]) =>
    api.post<{ resposta: string }>(`/processos/${id}/chat`, { pergunta, historico }).then((r) => r.data),
}
