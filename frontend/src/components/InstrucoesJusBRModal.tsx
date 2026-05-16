import { useState } from 'react'
import styles from './InstrucoesJusBRModal.module.css'
import {
  canSubmitJusbrCapture,
  detectJusbrInputKind,
  extractJusbrTokenFromText,
  formatTokenExpiry,
} from '../utils/jusbrToken'

interface Props {
  onClose: () => void
  onToken: (capture: string) => void
  initialToken?: string
  isSubmitting?: boolean
  error?: string | null
}

type OS = 'macos' | 'windows'
type Browser = 'chrome' | 'firefox'

interface StepGroup {
  before: string[]
  after: string[]
}

const STEPS: Record<OS, Record<Browser, StepGroup>> = {
  macos: {
    chrome: {
      before: [
        'Abra o Chrome e acesse o portal:<br><strong>portaldeservicos.pdpj.jus.br</strong><br>(botão abaixo já abre)',
        'Faça login com <strong>Certificado Digital</strong> ou <strong>gov.br</strong> e aguarde carregar o portal.',
        'Abra as ferramentas do desenvolvedor:<br><kbd>Cmd ⌘</kbd> + <kbd>Option ⌥</kbd> + <kbd>I</kbd>',
        'Clique na aba <strong>Network</strong> (Rede) e marque <strong>Preserve log</strong>.',
        'No portal, faça uma ação que carregue seus dados e filtre a aba Network/Rede por <strong>portaldeservicos.pdpj.jus.br/api</strong>.',
        'Copie o <strong>cURL</strong> ou os <strong>headers</strong> de uma requisição autenticada do portal. Não use a requisição de login <strong>/protocol/openid-connect/token</strong>, porque ela tem código descartável.',
        'Você pode colar abaixo o <strong>cURL</strong>, os <strong>headers</strong>, o <strong>JSON do token</strong> ou o <strong>token puro</strong>. O app extrai tudo automaticamente, mas o token sozinho pode não bastar para baixar documentos.',
      ],
      after: [],
    },
    firefox: {
      before: [
        'Abra o Firefox e acesse o portal:<br><strong>portaldeservicos.pdpj.jus.br</strong><br>(botão abaixo já abre)',
        'Faça login com <strong>Certificado Digital</strong> ou <strong>gov.br</strong> e aguarde carregar o portal.',
        'Abra as ferramentas do desenvolvedor:<br><kbd>Cmd ⌘</kbd> + <kbd>Option ⌥</kbd> + <kbd>I</kbd>',
        'Clique na aba <strong>Rede</strong> e marque <strong>Persistir logs</strong>, se disponível.',
        'No portal, faça uma ação que carregue seus dados e filtre a aba Rede por <strong>portaldeservicos.pdpj.jus.br/api</strong>.',
        'Copie o <strong>cURL</strong> ou os <strong>headers</strong> de uma requisição autenticada do portal. Não use a requisição de login <strong>/protocol/openid-connect/token</strong>, porque ela tem código descartável.',
        'Você pode colar abaixo o <strong>cURL</strong>, os <strong>headers</strong>, o <strong>JSON do token</strong> ou o <strong>token puro</strong>. O app extrai tudo automaticamente, mas o token sozinho pode não bastar para baixar documentos.',
      ],
      after: [],
    },
  },
  windows: {
    chrome: {
      before: [
        'Abra o Chrome e acesse o portal:<br><strong>portaldeservicos.pdpj.jus.br</strong><br>(botão abaixo já abre)',
        'Faça login com <strong>Certificado Digital</strong> ou <strong>gov.br</strong> e aguarde carregar o portal.',
        'Abra as ferramentas do desenvolvedor:<br><kbd>F12</kbd> ou <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>I</kbd>',
        'Clique na aba <strong>Network</strong> (Rede) e marque <strong>Preserve log</strong>.',
        'No portal, faça uma ação que carregue seus dados e filtre a aba Network/Rede por <strong>portaldeservicos.pdpj.jus.br/api</strong>.',
        'Copie o <strong>cURL</strong> ou os <strong>headers</strong> de uma requisição autenticada do portal. Não use a requisição de login <strong>/protocol/openid-connect/token</strong>, porque ela tem código descartável.',
        'Você pode colar abaixo o <strong>cURL</strong>, os <strong>headers</strong>, o <strong>JSON do token</strong> ou o <strong>token puro</strong>. O app extrai tudo automaticamente, mas o token sozinho pode não bastar para baixar documentos.',
      ],
      after: [],
    },
    firefox: {
      before: [
        'Abra o Firefox e acesse o portal:<br><strong>portaldeservicos.pdpj.jus.br</strong><br>(botão abaixo já abre)',
        'Faça login com <strong>Certificado Digital</strong> ou <strong>gov.br</strong> e aguarde carregar o portal.',
        'Abra as ferramentas do desenvolvedor:<br><kbd>F12</kbd> ou <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>I</kbd>',
        'Clique na aba <strong>Rede</strong> e marque <strong>Persistir logs</strong>, se disponível.',
        'No portal, faça uma ação que carregue seus dados e filtre a aba Rede por <strong>portaldeservicos.pdpj.jus.br/api</strong>.',
        'Copie o <strong>cURL</strong> ou os <strong>headers</strong> de uma requisição autenticada do portal. Não use a requisição de login <strong>/protocol/openid-connect/token</strong>, porque ela tem código descartável.',
        'Você pode colar abaixo o <strong>cURL</strong>, os <strong>headers</strong>, o <strong>JSON do token</strong> ou o <strong>token puro</strong>. O app extrai tudo automaticamente, mas o token sozinho pode não bastar para baixar documentos.',
      ],
      after: [],
    },
  },
}

export default function InstrucoesJusBRModal({ onClose, onToken, initialToken = '', isSubmitting = false, error = null }: Props) {
  const [os, setOs] = useState<OS>('macos')
  const [browser, setBrowser] = useState<Browser>('chrome')
  const [token, setToken] = useState(initialToken)
  const [clipboardMsg, setClipboardMsg] = useState<string | null>(null)

  const { before, after } = STEPS[os][browser]
  const allSteps = [...before, ...after]

  const networkStepIdx = allSteps.findIndex(s => s.includes('token'))

  function handleConfirm() {
    if (!canSubmitJusbrCapture(token) || isSubmitting) return
    onToken(token)
  }

  async function handlePasteClipboard() {
    try {
      const text = await navigator.clipboard.readText()
      setToken(text)
      const kind = detectJusbrInputKind(text)
      setClipboardMsg(
        kind === 'token_json'
          ? 'JSON de token detectado. Ele conecta a sessão, mas para baixar documentos o ideal continua sendo colar um cURL ou headers autenticados.'
          : kind === 'process_response'
          ? 'Resposta de /processos detectada. Ela ajuda no diagnóstico, mas não conecta a sessão. Copie cURL ou headers de uma chamada portaldeservicos.pdpj.jus.br/api/...'
          : kind === 'sso_curl'
          ? 'cURL de login detectado. Esse não serve para documentos; copie uma requisição autenticada portaldeservicos.pdpj.jus.br/api/... depois do login.'
          : kind === 'curl'
          ? 'cURL detectado. O token será extraído automaticamente.'
          : kind === 'headers'
          ? 'Headers detectados. O token será extraído automaticamente.'
          : kind === 'token'
          ? 'Token detectado.'
          : 'Conteúdo colado. Se houver uma sessão válida do jus.br, ela será extraída automaticamente.'
      )
    } catch {
      setClipboardMsg('Não foi possível ler a área de transferência. Cole manualmente no campo abaixo.')
    }
  }

  const extractedToken = token.trim() ? extractJusbrTokenFromText(token) : ''
  const tokenExpiry = extractedToken ? formatTokenExpiry(extractedToken) : null
  const inputKind = token.trim() ? detectJusbrInputKind(token) : 'unknown'
  const canSubmit = canSubmitJusbrCapture(token)

  return (
    <div className={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <span className={styles.headerIcon}>🔑</span>
            <div>
              <h2 className={styles.title}>Conectar jus.br</h2>
              <p className={styles.subtitle}>v4: prefira cURL ou headers autenticados para baixar documentos; resposta de /processos não substitui a sessão</p>
            </div>
          </div>
          <button className={styles.btnClose} onClick={onClose}>×</button>
        </div>

        <div className={styles.tabsRow}>
          <div className={styles.tabGroup}>
            <span className={styles.tabLabel}>Sistema:</span>
            <button className={`${styles.tab} ${os === 'macos' ? styles.tabActive : ''}`} onClick={() => setOs('macos')}>macOS</button>
            <button className={`${styles.tab} ${os === 'windows' ? styles.tabActive : ''}`} onClick={() => setOs('windows')}>Windows</button>
          </div>
          <div className={styles.tabGroup}>
            <span className={styles.tabLabel}>Navegador:</span>
            <button className={`${styles.tab} ${browser === 'chrome' ? styles.tabActive : ''}`} onClick={() => setBrowser('chrome')}>Chrome</button>
            <button className={`${styles.tab} ${browser === 'firefox' ? styles.tabActive : ''}`} onClick={() => setBrowser('firefox')}>Firefox</button>
          </div>
        </div>

        <div className={styles.body}>
          <ol className={styles.stepList}>
            {allSteps.map((step, i) => (
              <li key={i} className={styles.step}>
                <span className={styles.stepNum}>{i + 1}</span>
                <span className={styles.stepText} dangerouslySetInnerHTML={{ __html: step }} />
              </li>
            ))}
          </ol>

          {networkStepIdx >= 0 && (
            <div className={styles.networkHint}>
              <span className={styles.networkHintIcon}>💡</span>
              <span>
                Para baixar <strong>documentos reais</strong>, copie o <strong>cURL</strong> ou os <strong>headers</strong> de uma requisição autenticada em <strong>portaldeservicos.pdpj.jus.br/api/...</strong>, depois do login.
                Não use a chamada <strong>/protocol/openid-connect/token</strong>.
                O <strong>JSON de token</strong> continua aceito, mas pode sincronizar andamentos sem conseguir abrir o arquivo.
              </span>
            </div>
          )}

          <a
            href="https://portaldeservicos.pdpj.jus.br"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.btnJusbr}
          >
            Abrir portal jus.br ↗
          </a>

          <div className={styles.tokenSection}>
            <label className={styles.tokenLabel}>
              Cole aqui o <strong>JSON do token</strong>, o <strong>cURL</strong>, os <strong>headers</strong> ou o <strong>token</strong>:
            </label>
            <textarea
              className={styles.tokenInput}
              placeholder={`{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 28799
}`}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              rows={6}
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
            />
            <button className={styles.btnCancel} onClick={handlePasteClipboard}>
              Colar da área de transferência
            </button>
            {clipboardMsg && (
              <p className={styles.tokenHint}>
                {clipboardMsg}
              </p>
            )}
            <p className={styles.tokenHint}>
              Quando houver <strong>refresh_token</strong>, o app tenta renovar a sessão automaticamente. Para os <strong>documentos</strong>, prefira uma captura com <strong>cookies</strong> do portal, como cURL ou headers completos.
            </p>
            {inputKind !== 'unknown' && (
              <p className={styles.tokenHint}>
                Entrada detectada: {
                  inputKind === 'token_json'
                    ? 'JSON de token'
                    : inputKind === 'process_response'
                    ? 'Resposta de /processos'
                    : inputKind === 'sso_curl'
                    ? 'cURL de login descartável'
                    : inputKind === 'curl'
                    ? 'cURL'
                    : inputKind === 'headers'
                    ? 'Headers'
                    : 'Token'
                }.
              </p>
            )}
            {inputKind === 'sso_curl' && (
              <p className={styles.tokenError}>
                Esse é o cURL da etapa de login. Ele é descartável e não salva a sessão. Copie uma chamada autenticada do portal depois do login, com URL portaldeservicos.pdpj.jus.br/api/...
              </p>
            )}
            {tokenExpiry && (
              <p className={styles.tokenHint}>
                Expiração detectada no access token: {tokenExpiry}
              </p>
            )}
            {error && (
              <p className={styles.tokenError}>
                {error}
              </p>
            )}
          </div>
        </div>

        <div className={styles.footer}>
          <button className={styles.btnCancel} onClick={onClose}>Cancelar</button>
          <button
            className={styles.btnConfirm}
            onClick={handleConfirm}
            disabled={!canSubmit || isSubmitting}
          >
            {isSubmitting ? 'Salvando sessão...' : 'Conectar sessão do jus.br'}
          </button>
        </div>
      </div>
    </div>
  )
}
