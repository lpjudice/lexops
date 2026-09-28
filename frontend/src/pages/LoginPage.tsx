import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import { useAuth } from '../contexts/AuthContext'
import styles from './LoginPage.module.css'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setErro('')
    setLoading(true)
    try {
      await login(email.trim(), senha)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      // 401 é credencial errada de verdade; qualquer outro erro (timeout,
      // 500, sem resposta) é o backend/banco com problema — mostrar "senha
      // incorreta" nesse caso engana quem está tentando entrar (já
      // aconteceu: o banco ficou indisponível por alguns minutos e a tela
      // só dizia "senha incorreta", escondendo o problema real).
      if (isAxiosError(err) && err.response?.status === 401) {
        setErro('Email ou senha incorretos.')
      } else {
        setErro('Não foi possível conectar ao servidor. Tente novamente em instantes.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logoArea}>
          <span className={styles.logoMain}>PIMENTA JUDICE</span>
          <span className={styles.logoSub}>Advogados</span>
        </div>

        <h1 className={styles.title}>Entrar no sistema</h1>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label}>Email</label>
            <input
              type="email"
              className={styles.input}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="seu@email.com.br"
              required
              autoFocus
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Senha</label>
            <input
              type="password"
              className={styles.input}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>
          {erro && <p className={styles.erro}>{erro}</p>}
          <button type="submit" className={styles.btn} disabled={loading}>
            {loading ? 'Entrando...' : 'Entrar'}
          </button>
        </form>
      </div>
    </div>
  )
}
