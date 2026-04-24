import { useState } from 'react'
import styles from './ImportarJusBRModal.module.css'

interface Props {
  onClose: () => void
  onImportar: (json: string) => void
  isLoading?: boolean
}

const STEPS_CHROME_MAC = [
  'Abra o portal e faça login: <strong>portaldeservicos.pdpj.jus.br</strong>',
  'Navegue até o processo desejado.',
  'Abra o DevTools: <kbd>Cmd ⌘</kbd> + <kbd>Option ⌥</kbd> + <kbd>I</kbd>',
  'Clique na aba <strong>Network</strong> e recarregue a página do processo (<kbd>Cmd ⌘</kbd> + <kbd>R</kbd>).',
  'Na lista de requisições, procure uma que contenha <strong>"movimentos"</strong> ou <strong>"andamentos"</strong> na URL.',
  'Clique nessa requisição → aba <strong>Response</strong> → selecione tudo (<kbd>Cmd ⌘</kbd> + <kbd>A</kbd>) → copie (<kbd>Cmd ⌘</kbd> + <kbd>C</kbd>).',
  'Cole abaixo e clique em <strong>Importar</strong>.',
]

const STEPS_CHROME_WIN = [
  'Abra o portal e faça login: <strong>portaldeservicos.pdpj.jus.br</strong>',
  'Navegue até o processo desejado.',
  'Abra o DevTools: <kbd>F12</kbd>',
  'Clique na aba <strong>Network</strong> e recarregue a página do processo (<kbd>F5</kbd>).',
  'Na lista de requisições, procure uma que contenha <strong>"movimentos"</strong> ou <strong>"andamentos"</strong> na URL.',
  'Clique nessa requisição → aba <strong>Response</strong> → selecione tudo (<kbd>Ctrl</kbd> + <kbd>A</kbd>) → copie (<kbd>Ctrl</kbd> + <kbd>C</kbd>).',
  'Cole abaixo e clique em <strong>Importar</strong>.',
]

type OS = 'macos' | 'windows'

export default function ImportarJusBRModal({ onClose, onImportar, isLoading }: Props) {
  const [os, setOs] = useState<OS>('macos')
  const [json, setJson] = useState('')

  const steps = os === 'macos' ? STEPS_CHROME_MAC : STEPS_CHROME_WIN

  function handleImportar() {
    const t = json.trim()
    if (!t) return
    onImportar(t)
  }

  // Quick sanity check
  const parece_json = json.trim().startsWith('{') || json.trim().startsWith('[')

  return (
    <div className={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={styles.modal}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={styles.headerIcon}>📋</span>
            <div>
              <h2 className={styles.title}>Importar andamentos do jus.br</h2>
              <p className={styles.subtitle}>Cole o JSON da aba Response do DevTools</p>
            </div>
          </div>
          <button className={styles.btnClose} onClick={onClose}>×</button>
        </div>

        {/* OS tabs */}
        <div className={styles.tabsRow}>
          <span className={styles.tabLabel}>Sistema:</span>
          <button className={`${styles.tab} ${os === 'macos' ? styles.tabActive : ''}`} onClick={() => setOs('macos')}>macOS</button>
          <button className={`${styles.tab} ${os === 'windows' ? styles.tabActive : ''}`} onClick={() => setOs('windows')}>Windows</button>
        </div>

        <div className={styles.body}>
          {/* Steps */}
          <ol className={styles.stepList}>
            {steps.map((step, i) => (
              <li key={i} className={styles.step}>
                <span className={styles.stepNum}>{i + 1}</span>
                <span className={styles.stepText} dangerouslySetInnerHTML={{ __html: step }} />
              </li>
            ))}
          </ol>

          {/* Portal link */}
          <a
            href="https://portaldeservicos.pdpj.jus.br"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.btnPortal}
          >
            Abrir portal jus.br ↗
          </a>

          {/* Paste area */}
          <div className={styles.pasteSection}>
            <label className={styles.pasteLabel}>
              Cole o JSON aqui:
            </label>
            <textarea
              className={`${styles.pasteArea} ${json && !parece_json ? styles.pasteAreaErro : ''}`}
              placeholder={'{\n  "movimentos": [...]\n}'}
              value={json}
              onChange={(e) => setJson(e.target.value)}
              rows={6}
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
            />
            {json && !parece_json && (
              <p className={styles.pasteErro}>Isso não parece um JSON válido. Certifique-se de copiar da aba Response (não Headers).</p>
            )}
            {parece_json && (
              <p className={styles.pasteOk}>✓ JSON detectado ({json.length.toLocaleString('pt-BR')} caracteres)</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <button className={styles.btnCancel} onClick={onClose}>Cancelar</button>
          <button
            className={styles.btnImportar}
            onClick={handleImportar}
            disabled={!parece_json || isLoading}
          >
            {isLoading ? 'Importando…' : 'Importar andamentos'}
          </button>
        </div>
      </div>
    </div>
  )
}
