import { useState } from 'react'
import styles from './InstrucoesJusBRModal.module.css'
import {
  detectJusbrInputKind,
  extractJusbrTokenFromText,
  formatTokenExpiry,
} from '../utils/jusbrToken'

interface Props {
  onClose: () => void
  onToken: (capture: string) => void
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
        'Na lista de requisições, clique com o botão direito em qualquer item que contenha <strong>"api/"</strong> na URL.',
        'Escolha <strong>Copy → Copy as cURL</strong> e cole o conteúdo inteiro no campo abaixo.<br>O app extrai o token automaticamente.',
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
        'Na lista de requisições, clique com o botão direito em qualquer item que contenha <strong>"api/"</strong> na URL.',
        'Use <strong>Copiar → Copiar como cURL</strong> e cole o conteúdo inteiro no campo abaixo.<br>O app extrai o token automaticamente.',
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
        'Na lista de requisições, clique com o botão direito em qualquer item que contenha <strong>"api/"</strong> na URL.',
        'Escolha <strong>Copy → Copy as cURL</strong> e cole o conteúdo inteiro no campo abaixo.<br>O app extrai o token automaticamente.',
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
        'Na lista de requisições, clique com o botão direito em qualquer item que contenha <strong>"api/"</strong> na URL.',
        'Use <strong>Copiar → Copiar como cURL</strong> e cole o conteúdo inteiro no campo abaixo.<br>O app extrai o token automaticamente.',
      ],
      after: [],
    },
  },
}

export default function InstrucoesJusBRModal({ onClose, onToken, initialToken = '' }: Props) {
  const [os, setOs] = useState<OS>('macos')
  const [browser, setBrowser] = useState<Browser>('chrome')
  const [token, setToken] = useState(initialToken)
  const [clipboardMsg, setClipboardMsg] = useState<string | null>(null)

  const { before, after } = STEPS[os][browser]
  const allSteps = [...before, ...after]

  // Index after which to show the reference image hint
  const networkStepIdx = allSteps.findIndex(s => s.includes('cURL'))

  function handleConfirm() {
    const t = extractJusbrTokenFromText(token)
    if (!t) return
    onToken(token)
    onClose()
  }

  async function handlePasteClipboard() {
    try {
      const text = await navigator.clipboard.readText()
      setToken(text)
      const kind = detectJusbrInputKind(text)
      setClipboardMsg(
        kind === 'curl'
          ? 'cURL detectado. O token será extraído automaticamente.'
          : kind === 'headers'
          ? 'Headers detectados. O token será extraído automaticamente.'
          : kind === 'token'
          ? 'Token detectado.'
          : 'Conteúdo colado. Se houver um Bearer válido, ele será extraído automaticamente.'
      )
    } catch {
      setClipboardMsg('Não foi possível ler a área de transferência. Cole manualmente no campo abaixo.')
    }
  }

  const extractedToken = token.trim() ? extractJusbrTokenFromText(token) : ''
  const tokenExpiry = extractedToken ? formatTokenExpiry(extractedToken) : null
  const inputKind = token.trim() ? detectJusbrInputKind(token) : 'unknown'

  return (
    <div className={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={styles.modal}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <span className={styles.headerIcon}>🔑</span>
            <div>
              <h2 className={styles.title}>Sincronizar via jus.br</h2>
              <p className={styles.subtitle}>v2: cole o cURL, headers ou token e o app extrai o Bearer</p>
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
                A forma mais fácil agora é copiar o <strong>cURL inteiro</strong> da requisição.
                Se preferir, você ainda pode colar só o token Bearer ou um bloco de headers.
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
              Cole aqui o <strong>cURL</strong>, os <strong>headers</strong> ou o <strong>token</strong>:
            </label>
            <textarea
              className={styles.tokenInput}
              placeholder={`curl 'https://portaldeservicos.pdpj.jus.br/api/...'\n  -H 'authorization: Bearer eyJ...' ...`}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              rows={5}
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
              O token expira em poucos minutos. Depois da primeira captura, o app tenta reutilizá-lo automaticamente enquanto ainda estiver válido.
            </p>
            {inputKind !== 'unknown' && (
              <p className={styles.tokenHint}>
                Entrada detectada: {inputKind === 'curl' ? 'cURL' : inputKind === 'headers' ? 'Headers' : 'Token'}.
              </p>
            )}
            {tokenExpiry && (
              <p className={styles.tokenHint}>
                Expiração detectada no token extraído: {tokenExpiry}
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
            disabled={!extractedToken}
          >
            Sincronizar com o token extraído
          </button>
        </div>
      </div>
    </div>
  )
}
