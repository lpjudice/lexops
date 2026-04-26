import { useState } from 'react'
import styles from './InstrucoesJusBRModal.module.css'
import { formatTokenExpiry, sanitizeJusbrToken } from '../utils/jusbrToken'

interface Props {
  onClose: () => void
  onToken: (token: string) => void
  initialToken?: string
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
        'Clique na aba <strong>Network</strong> (Rede).',
        'No portal, <strong>faça qualquer ação</strong> — pesquise um processo, clique em um menu. Isso dispara chamadas de API.',
        'Na lista de requisições, clique em qualquer item que contenha <strong>"api/"</strong> na URL.',
        'No painel lateral, clique em <strong>"Headers"</strong> → role até <strong>"Request Headers"</strong>.<br>Localize a linha <strong>authorization: Bearer eyJ…</strong>',
        'Copie <strong>somente o trecho após "Bearer "</strong> (começa com <em>eyJ</em>) e cole no campo abaixo.',
      ],
      after: [],
    },
    firefox: {
      before: [
        'Abra o Firefox e acesse o portal:<br><strong>portaldeservicos.pdpj.jus.br</strong><br>(botão abaixo já abre)',
        'Faça login com <strong>Certificado Digital</strong> ou <strong>gov.br</strong> e aguarde carregar o portal.',
        'Abra as ferramentas do desenvolvedor:<br><kbd>Cmd ⌘</kbd> + <kbd>Option ⌥</kbd> + <kbd>I</kbd>',
        'Clique na aba <strong>Rede</strong>.',
        'No portal, <strong>faça qualquer ação</strong> — pesquise um processo, clique em um menu.',
        'Na lista de requisições, clique em qualquer item que contenha <strong>"api/"</strong> na URL.',
        'Clique na aba <strong>Cabeçalhos</strong> → role até <strong>"Cabeçalhos da solicitação"</strong>.<br>Localize a linha <strong>authorization: Bearer eyJ…</strong>',
        'Copie <strong>somente o trecho após "Bearer "</strong> (começa com <em>eyJ</em>) e cole no campo abaixo.',
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
        'Clique na aba <strong>Network</strong> (Rede).',
        'No portal, <strong>faça qualquer ação</strong> — pesquise um processo, clique em um menu. Isso dispara chamadas de API.',
        'Na lista de requisições, clique em qualquer item que contenha <strong>"api/"</strong> na URL.',
        'No painel lateral, clique em <strong>"Headers"</strong> → role até <strong>"Request Headers"</strong>.<br>Localize a linha <strong>authorization: Bearer eyJ…</strong>',
        'Copie <strong>somente o trecho após "Bearer "</strong> (começa com <em>eyJ</em>) e cole no campo abaixo.',
      ],
      after: [],
    },
    firefox: {
      before: [
        'Abra o Firefox e acesse o portal:<br><strong>portaldeservicos.pdpj.jus.br</strong><br>(botão abaixo já abre)',
        'Faça login com <strong>Certificado Digital</strong> ou <strong>gov.br</strong> e aguarde carregar o portal.',
        'Abra as ferramentas do desenvolvedor:<br><kbd>F12</kbd> ou <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>I</kbd>',
        'Clique na aba <strong>Rede</strong>.',
        'No portal, <strong>faça qualquer ação</strong> — pesquise um processo, clique em um menu.',
        'Na lista de requisições, clique em qualquer item que contenha <strong>"api/"</strong> na URL.',
        'Clique na aba <strong>Cabeçalhos</strong> → role até <strong>"Cabeçalhos da solicitação"</strong>.<br>Localize a linha <strong>authorization: Bearer eyJ…</strong>',
        'Copie <strong>somente o trecho após "Bearer "</strong> (começa com <em>eyJ</em>) e cole no campo abaixo.',
      ],
      after: [],
    },
  },
}

export default function InstrucoesJusBRModal({ onClose, onToken, initialToken = '' }: Props) {
  const [os, setOs] = useState<OS>('macos')
  const [browser, setBrowser] = useState<Browser>('chrome')
  const [token, setToken] = useState(initialToken)

  const { before, after } = STEPS[os][browser]
  const allSteps = [...before, ...after]

  // Index after which to show the reference image hint
  const networkStepIdx = allSteps.findIndex(s => s.includes('authorization'))

  function handleConfirm() {
    const t = sanitizeJusbrToken(token)
    if (!t) return
    onToken(t)
    onClose()
  }

  const tokenExpiry = token.trim() ? formatTokenExpiry(sanitizeJusbrToken(token)) : null

  return (
    <div className={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={styles.modal}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <span className={styles.headerIcon}>🔑</span>
            <div>
              <h2 className={styles.title}>Sincronizar via jus.br</h2>
              <p className={styles.subtitle}>Capture o token de sessão pela aba Network do DevTools</p>
            </div>
          </div>
          <button className={styles.btnClose} onClick={onClose}>×</button>
        </div>

        {/* OS + Browser tabs */}
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

        {/* Body */}
        <div className={styles.body}>
          <ol className={styles.stepList}>
            {allSteps.map((step, i) => (
              <li key={i} className={styles.step}>
                <span className={styles.stepNum}>{i + 1}</span>
                <span className={styles.stepText} dangerouslySetInnerHTML={{ __html: step }} />
              </li>
            ))}
          </ol>

          {/* Visual hint for where to find the token */}
          {networkStepIdx >= 0 && (
            <div className={styles.networkHint}>
              <span className={styles.networkHintIcon}>💡</span>
              <span>
                O valor completo do token é longo (começa com <code>eyJ</code> e tem centenas de caracteres).
                Copie tudo — não só o início. Se o campo mostrar só parte, clique duas vezes nele e use Ctrl+A / Cmd+A para selecionar tudo.
              </span>
            </div>
          )}

          {/* Portal button */}
          <a
            href="https://portaldeservicos.pdpj.jus.br"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.btnJusbr}
          >
            Abrir portal jus.br ↗
          </a>

          {/* Token input */}
          <div className={styles.tokenSection}>
            <label className={styles.tokenLabel}>
              Cole o token aqui (o trecho após "Bearer "):
            </label>
            <textarea
              className={styles.tokenInput}
              placeholder="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6..."
              value={token}
              onChange={(e) => setToken(e.target.value)}
              rows={3}
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
            />
            <p className={styles.tokenHint}>
              O token expira em ~5 minutos. Se a sincronização falhar com erro de autenticação, repita o processo.
            </p>
            {tokenExpiry && (
              <p className={styles.tokenHint}>
                Expiração detectada no token colado: {tokenExpiry}
              </p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <button className={styles.btnCancel} onClick={onClose}>Cancelar</button>
          <button
            className={styles.btnConfirm}
            onClick={handleConfirm}
            disabled={!token.trim()}
          >
            Sincronizar com este token
          </button>
        </div>
      </div>
    </div>
  )
}
