import api from './client'

/** Campos cadastrais estendidos (PF + PJ), preenchíveis no autocadastro. */
export interface ClienteCadastroFields {
  whatsapp?: string
  // Endereço estruturado
  cep?: string
  logradouro?: string
  numero?: string
  complemento?: string
  bairro?: string
  cidade?: string
  uf?: string
  // Pessoa Física
  data_nascimento?: string | null
  rg?: string
  estado_civil?: string
  profissao?: string
  empresas_vinculadas?: string
  // Pessoa Jurídica
  nome_fantasia?: string
  responsavel_nome?: string
  responsavel_cpf?: string
  responsavel_email?: string
  responsavel_telefone?: string
}

export interface Cliente extends ClienteCadastroFields {
  id: string
  nome: string
  tipo: 'PF' | 'PJ'
  cpf_cnpj?: string
  email?: string
  telefone?: string
  endereco?: string
  observacoes?: string
  incompleto?: boolean
  monitorar_diario?: boolean
  origem_cadastro?: string
  projeto_nome?: string
  worktree_nome?: string
  created_at: string
  updated_at: string
}

export interface ClienteCreate extends ClienteCadastroFields {
  nome: string
  tipo: 'PF' | 'PJ'
  cpf_cnpj?: string
  email?: string
  telefone?: string
  endereco?: string
  observacoes?: string
  incompleto?: boolean
  monitorar_diario?: boolean
}

export interface Documento {
  filename: string
  size: number
  subpasta?: string | null
  drive_link?: string | null
  source?: 'drive' | 'local'
}

export interface PastaArquivo {
  nome: string
  tamanho: number
  modificado: string
  tipo: string
  subpasta: string | null
  caminho: string
}

export interface ChatMessage {
  role: 'user' | 'model'
  content: string
}

export interface EmailCliente {
  id: string
  gmail_message_id: string
  conta_google: string
  conta_email: string | null
  remetente: string | null
  destinatarios: string | null
  assunto: string | null
  snippet: string | null
  thread_id: string | null
  data: string | null
  lido: boolean
  privado: boolean
  privado_por: string | null
  created_at: string
}

export const clientesApi = {
  listar: () => api.get<Cliente[]>('/clientes/').then((r) => r.data),
  criar: (data: ClienteCreate) => api.post<Cliente>('/clientes/', data).then((r) => r.data),
  obter: (id: string) => api.get<Cliente>(`/clientes/${id}`).then((r) => r.data),
  atualizar: (id: string, data: Partial<ClienteCreate>) =>
    api.patch<Cliente>(`/clientes/${id}`, data).then((r) => r.data),
  deletar: (id: string) => api.delete(`/clientes/${id}`),

  uploadPdf: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{ filename: string; size: number; drive_link?: string | null }>(`/clientes/${id}/upload-pdf`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
  listarDocumentos: (id: string) =>
    api.get<Documento[]>(`/clientes/${id}/documentos`).then((r) => r.data),
  removerDocumento: (id: string, filename: string) =>
    api.delete(`/clientes/${id}/documentos/${filename}`),

  chat: (id: string, pergunta: string, historico: ChatMessage[], modelo: string) =>
    api.post<{ resposta: string }>(`/clientes/${id}/chat`, { pergunta, historico, modelo })
      .then((r) => r.data),
  obterContexto: (id: string) =>
    api.get<{ contexto: string }>(`/clientes/${id}/contexto`).then((r) => r.data),
  classificarEmailsPendentes: (id: string) =>
    api.post<{ classificados: number }>(`/clientes/${id}/emails/classificar-pendentes`).then((r) => r.data),

  pastaArquivos: (clienteId: string) =>
    api.get<PastaArquivo[]>(`/clientes/${clienteId}/pasta-arquivos/refresh`).then(r => r.data),

  listarEmails: (clienteId: string) =>
    api.get<EmailCliente[]>(`/clientes/${clienteId}/emails`).then(r => r.data),

  sincronizarEmails: (clienteId: string, contas: string[]) =>
    api.post<{ synced: number; new: number; error: string | null }>(
      `/clientes/${clienteId}/emails/sync`,
      { contas },
    ).then(r => r.data),

  marcarEmailPrivacidade: (clienteId: string, emailId: string, privado: boolean) =>
    api.patch<{ id: string; privado: boolean }>(
      `/clientes/${clienteId}/emails/${emailId}/privacidade`,
      { privado },
    ).then(r => r.data),
}

// ── Links de autocadastro (Fase 2) ────────────────────────────────────────────

export interface CadastroLink {
  id: string
  token: string
  cliente_id: string | null
  rotulo?: string
  reutilizavel: boolean
  expira_em: string | null
  revogado: boolean
  usos: number
  caminho: string
  created_at: string | null
}

export const cadastroLinksApi = {
  listar: () => api.get<CadastroLink[]>('/cadastro-links').then((r) => r.data),
  criar: (data: { cliente_id?: string | null; rotulo?: string; expira_em_dias?: number | null }) =>
    api.post<CadastroLink>('/cadastro-links', data).then((r) => r.data),
  revogar: (id: string) => api.post(`/cadastro-links/${id}/revogar`),
}
