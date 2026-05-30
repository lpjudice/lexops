import api from './client'

export interface Usuario {
  id: string
  email: string
  nome: string
  role: 'super_admin' | 'admin' | 'membro'
  ativo: boolean
  pode_ver_financeiro: boolean
  pode_ver_contratos: boolean
  pode_ver_tarefas_outros: boolean
  clientes_restritos: boolean
  created_at: string
  clientes_ids: string[]
  primeiro_acesso: boolean
  google_email?: string | null
  google_email_extra?: string | null
}

export interface LoginRequest {
  email: string
  senha: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  usuario: Usuario
}

export interface UsuarioCreate {
  email: string
  nome: string
  role?: string
  pode_ver_financeiro?: boolean
  pode_ver_contratos?: boolean
  pode_ver_tarefas_outros?: boolean
  clientes_restritos?: boolean
}

export interface ConviteInfo {
  nome: string
  email: string
}

export interface AcceptInviteRequest {
  senha: string
}

export interface UsuarioUpdate {
  nome?: string
  role?: string
  ativo?: boolean
  pode_ver_financeiro?: boolean
  pode_ver_contratos?: boolean
  pode_ver_tarefas_outros?: boolean
  clientes_restritos?: boolean
  senha?: string
}

export const usuariosApi = {
  login: (data: LoginRequest) =>
    api.post<TokenResponse>('/usuarios/login', data).then((r) => r.data),

  me: (token: string) =>
    api.get<Usuario>(`/usuarios/me?token=${encodeURIComponent(token)}`).then((r) => r.data),

  listar: () => api.get<Usuario[]>('/usuarios/').then((r) => r.data),

  criar: (data: UsuarioCreate) =>
    api.post<Usuario>('/usuarios/', data).then((r) => r.data),

  atualizar: (id: string, data: UsuarioUpdate) =>
    api.patch<Usuario>(`/usuarios/${id}`, data).then((r) => r.data),

  deletar: (id: string) => api.delete(`/usuarios/${id}`),

  vincularCliente: (usuarioId: string, clienteId: string) =>
    api.post(`/usuarios/${usuarioId}/clientes`, { cliente_id: clienteId }),

  desvincularCliente: (usuarioId: string, clienteId: string) =>
    api.delete(`/usuarios/${usuarioId}/clientes/${clienteId}`),

  reenviarConvite: (usuarioId: string) =>
    api.post(`/usuarios/${usuarioId}/reenviar-convite`),

  validarConvite: (token: string) =>
    api.get<ConviteInfo>(`/usuarios/aceitar-convite/${token}`).then((r) => r.data),

  aceitarConvite: (token: string, senha: string) =>
    api.post<TokenResponse>(`/usuarios/aceitar-convite/${token}`, { senha }).then((r) => r.data),
}
