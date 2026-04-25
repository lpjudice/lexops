import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { type Usuario, usuariosApi } from '../api/usuarios'

const TOKEN_KEY = 'gestor_jwt'

interface AuthContextValue {
  usuario: Usuario | null
  token: string | null
  loading: boolean
  login: (email: string, senha: string) => Promise<void>
  loginComToken: (token: string, usuario: Usuario) => void
  logout: () => void
  clearPrimeiroAcesso: () => void
  refreshMe: () => Promise<void>
  isSuperAdmin: boolean
  isAdmin: boolean
  canSeeFinanceiro: boolean
  canSeeContratos: boolean
  canSeeOthersTasks: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_KEY)
    if (!saved) { setLoading(false); return }
    usuariosApi.me(saved)
      .then((u) => { setToken(saved); setUsuario(u) })
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, senha: string) => {
    const data = await usuariosApi.login({ email, senha })
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setToken(data.access_token)
    setUsuario(data.usuario)
  }

  const loginComToken = (t: string, u: Usuario) => {
    localStorage.setItem(TOKEN_KEY, t)
    setToken(t)
    setUsuario(u)
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUsuario(null)
  }

  const clearPrimeiroAcesso = () => {
    if (usuario) setUsuario({ ...usuario, primeiro_acesso: false })
  }

  const refreshMe = async () => {
    const saved = localStorage.getItem(TOKEN_KEY)
    if (!saved) return
    try {
      const u = await usuariosApi.me(saved)
      setUsuario(u)
    } catch {
      // silently ignore
    }
  }

  const value: AuthContextValue = {
    usuario, token, loading, login, loginComToken, logout, clearPrimeiroAcesso, refreshMe,
    isSuperAdmin: usuario?.role === 'super_admin',
    isAdmin: usuario?.role === 'super_admin' || usuario?.role === 'admin',
    canSeeFinanceiro: usuario?.pode_ver_financeiro ?? false,
    canSeeContratos: usuario?.pode_ver_contratos ?? false,
    canSeeOthersTasks: usuario?.pode_ver_tarefas_outros ?? false,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
