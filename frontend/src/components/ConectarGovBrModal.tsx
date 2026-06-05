import { useState } from 'react'
import styles from './ConectarGovBrModal.module.css'
import { andamentosApi } from '../api/andamentos'

interface Props {
  onClose: () => void
  onSuccess?: () => void
}

type Status = {
  ok: boolean
  expires_at: string | null
  refresh_type: string | null
  refresh_scope: string | null
  refresh_expires_at: string | null
}

export default function ConectarGovBrModal({ onClose, onSuccess }: Props) {
  const [step, setStep] = useState<'intro' | 'aguardando_colar' | 'concluido'>('intro')
  const [loginUrl, setLoginUrl] = useState<string>('')
  const [stateId, setStateId] = useState<string>('')
  const [pasted, setPasted] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status | null>(null)

  const iniciar = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await andamentosApi.iniciarPkceJusBR()
      setLoginUrl(r.url)
      setStateId(r.state_id)
      setStep('aguardando_colar')
      window.open(r.url, '_blank', 'noopener,noreferrer')
    } catch (e) {
      setError('Não consegui gerar o link de login. Tente de novo em instantes.')
    } finally {
      setBusy(false)
    }
  }

  const finalizar = async () => {
    if (!pasted.trim()) {
      setError('Cole a URL que apareceu no navegador depois do login.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const r = await andamentosApi.finalizarPkceJusBR(stateId, pasted.trim())
      setStatus(r)
      setStep('concluido')
      onSuccess?.()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Falha ao concluir o login.'
      setError(typeof msg === 'string' ? msg : 'Falha ao concluir o login.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true">
      <div className={styles.modal}>
        <div className={styles.header}>
          <div>
            <h2 className={styles.title}>🔐 Conectar via gov.br</h2>
            <p className={styles.subtitle}>Login PKCE com offline_access — sessão renovada automaticamente, sem expirar.</p>
          </div>
          <button className={styles.close} onClick={onClose} aria-label="Fechar">×</button>
        </div>

        <div className={styles.body}>
          {step === 'intro' && (
            <>
              <p>
                Em vez de colar o JSON do token (que expira), você loga UMA VEZ no gov.br
                e a sessão fica viva indefinidamente (renovada por trás).
              </p>
              <ol>
                <li>Toque em <strong>Abrir login gov.br</strong> abaixo.</li>
                <li>No seu navegador, faça login no gov.br normalmente.</li>
                <li>O navegador vai para <em>portaldeservicos.pdpj.jus.br/home?code=...</em> (pode mostrar “Solicitação inválida” — é normal).</li>
                <li>Copie a URL INTEIRA da barra de endereço e cole aqui.</li>
              </ol>
              {error && <div className={styles.error}>{error}</div>}
              <div className={styles.actions}>
                <button className={`${styles.cta} ${styles.secondary}`} onClick={onClose} disabled={busy}>Cancelar</button>
                <button className={styles.cta} onClick={iniciar} disabled={busy}>
                  {busy ? 'Gerando…' : 'Abrir login gov.br ↗'}
                </button>
              </div>
            </>
          )}

          {step === 'aguardando_colar' && (
            <>
              <p>
                A janela do gov.br abriu em outra aba. Depois do login, copie a URL da barra de
                endereço da página final (com <code>?code=...</code>) e cole aqui:
              </p>
              <div className={styles.linkBox}>
                <a href={loginUrl} target="_blank" rel="noopener noreferrer">{loginUrl}</a>
              </div>
              <textarea
                className={styles.textarea}
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                placeholder="https://portaldeservicos.pdpj.jus.br/home?state=...&session_state=...&code=..."
                spellCheck={false}
              />
              <p className={styles.hint}>O link de login expira em 10 minutos.</p>
              {error && <div className={styles.error}>{error}</div>}
              <div className={styles.actions}>
                <button className={`${styles.cta} ${styles.secondary}`} onClick={onClose} disabled={busy}>Cancelar</button>
                <button className={styles.cta} onClick={finalizar} disabled={busy || !pasted.trim()}>
                  {busy ? 'Trocando…' : 'Concluir login'}
                </button>
              </div>
            </>
          )}

          {step === 'concluido' && status && (
            <>
              <div className={styles.success}>
                <strong>✅ Conexão concluída!</strong>
                {status.refresh_type === 'Offline' ? (
                  <p style={{ margin: '6px 0 0' }}>
                    Sessão renovará automaticamente.<span className={styles.tagOffline}>OFFLINE</span>
                  </p>
                ) : (
                  <p style={{ margin: '6px 0 0' }}>
                    Tipo do refresh: <strong>{status.refresh_type || '?'}</strong>
                    {status.refresh_expires_at ? ` (expira em ${new Date(status.refresh_expires_at).toLocaleString('pt-BR')})` : ''}
                  </p>
                )}
                <p style={{ margin: '6px 0 0', fontSize: 12, color: '#374151' }}>
                  Access token expira em: {status.expires_at ? new Date(status.expires_at).toLocaleString('pt-BR') : '—'}
                </p>
              </div>
              <div className={styles.actions}>
                <button className={styles.cta} onClick={onClose}>Fechar</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
