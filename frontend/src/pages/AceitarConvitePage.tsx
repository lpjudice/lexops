import { useEffect, useState, FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import api from '../api/client'
import styles from './AceitarConvitePage.module.css'

interface ConviteInfo {
  nome: string
  email: string
}

export default function AceitarConvitePage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const { loginComToken } = useAuth()

  const [info, setInfo] = useState<ConviteInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [tokenInvalido, setTokenInvalido] = useState(false)
  const [senha, setSenha] = useState('')
  const [confirmar, setConfirmar] = useState('')
  const [erro, setErro] = useState('')
  const [salvando, setSalvando] = useState(false)

  useEffect(() => {
    if (!token) { setTokenInvalido(true); setLoading(false); return }
    api.get(`/usuarios/aceitar-convite/${token}`)
      .then((r) => setInfo(r.data))
      .catch(() => setTokenInvalido(true))
      .finally(() => setLoading(false))
  }, [token])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setErro('')
    if (senha.length < 8) { setErro('A senha deve ter pelo menos 8 caracteres.'); return }
    if (senha !== confirmar) { setErro('As senhas não coincidem.'); return }
    setSalvando(true)
    try {
      const r = await api.post(`/usuarios/aceitar-convite/${token}`, { senha })
      loginComToken(r.data.access_token, r.data.usuario)
      navigate('/configuracoes?convite=1', { replace: true })
    } catch (err: any) {
      setErro(err?.response?.data?.detail ?? 'Erro ao ativar conta.')
    } finally {
      setSalvando(false)
    }
  }

  if (loading) return (
    <div className={styles.page}>
      <div className={styles.card}>
        <p className={styles.loadingText}>Verificando convite...</p>
      </div>
    </div>
  )

  if (tokenInvalido) return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logoArea}>
          <span className={styles.logoMain}>PIMENTA JUDICE</span>
          <span className={styles.logoSub}>Advogados</span>
        </div>
        <div className={styles.errorBox}>
          <p className={styles.errorTitle}>Link inválido ou expirado</p>
          <p className={styles.errorDesc}>Este link de convite não é válido ou já expirou (48h). Peça ao administrador para reenviar o convite.</p>
        </div>
      </div>
    </div>
  )

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logoArea}>
          <span className={styles.logoMain}>PIMENTA JUDICE</span>
          <span className={styles.logoSub}>Advogados</span>
        </div>

        <div className={styles.welcomeBox}>
          <p className={styles.welcomeHi}>Olá, {info?.nome}!</p>
          <p className={styles.welcomeDesc}>
            Você foi convidado para o Gestor Jurídico. Defina uma senha para ativar sua conta.
          </p>
          <p className={styles.welcomeEmail}>{info?.email}</p>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label}>Senha</label>
            <input
              type="password"
              className={styles.input}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              placeholder="Mínimo 8 caracteres"
              required
              autoFocus
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Confirmar senha</label>
            <input
              type="password"
              className={styles.input}
              value={confirmar}
              onChange={(e) => setConfirmar(e.target.value)}
              placeholder="Repita a senha"
              required
            />
          </div>
          {erro && <p className={styles.erro}>{erro}</p>}
          <button type="submit" className={styles.btn} disabled={salvando}>
            {salvando ? 'Ativando...' : 'Ativar conta e entrar →'}
          </button>
        </form>
      </div>
    </div>
  )
}
