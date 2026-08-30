/**
 * Combobox de peça processual — lista fixa + peças customizadas salvas localmente.
 * Ao criar uma peça nova, pergunta o prazo padrão (dias + contagem) e devolve
 * esse padrão via onApplyDefault para atualizar os outros campos do formulário.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import styles from './ClienteCombobox.module.css'

export interface PecaCustom {
  label: string
  dias_prazo: number
  tipo_contagem: 'uteis' | 'corridos'
}

const STORAGE_KEY = 'gj_pecas_customizadas_v1'

function loadCustom(): PecaCustom[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveCustom(entry: PecaCustom) {
  const atual = loadCustom().filter((p) => p.label.toLowerCase() !== entry.label.toLowerCase())
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...atual, entry]))
}

interface Props {
  value: string
  onChange: (label: string) => void
  baseOptions: string[]
  onApplyDefault?: (diasPrazo: number, tipoContagem: 'uteis' | 'corridos') => void
}

export default function PecaCombobox({ value, onChange, baseOptions, onApplyDefault }: Props) {
  const [customPecas, setCustomPecas] = useState<PecaCustom[]>(() => loadCustom())
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [diasNovo, setDiasNovo] = useState(5)
  const [tipoContagemNovo, setTipoContagemNovo] = useState<'uteis' | 'corridos'>('uteis')
  const ref = useRef<HTMLDivElement>(null)

  const options = useMemo(() => {
    const customLabels = customPecas.map((p) => p.label)
    const merged = Array.from(new Set([...baseOptions, ...customLabels]))
    return merged.sort((a, b) => a.localeCompare(b, 'pt-BR'))
  }, [baseOptions, customPecas])

  const filtered = query
    ? options.filter((o) => o.toLowerCase().includes(query.toLowerCase()))
    : options

  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setCreating(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  const select = (label: string) => {
    onChange(label)
    setOpen(false)
    setCreating(false)
    setQuery('')
    const custom = customPecas.find((p) => p.label.toLowerCase() === label.toLowerCase())
    if (custom) onApplyDefault?.(custom.dias_prazo, custom.tipo_contagem)
  }

  const handleCreate = () => {
    const label = query.trim()
    if (!label) return
    const entry: PecaCustom = { label, dias_prazo: diasNovo, tipo_contagem: tipoContagemNovo }
    saveCustom(entry)
    setCustomPecas(loadCustom())
    onChange(label)
    onApplyDefault?.(diasNovo, tipoContagemNovo)
    setCreating(false)
    setOpen(false)
    setQuery('')
  }

  const showCreate = query.trim().length > 1 && filtered.length === 0

  return (
    <div className={styles.root} ref={ref}>
      <div
        className={`${styles.trigger} ${open ? styles.triggerOpen : ''} ${!value ? styles.triggerEmpty : ''}`}
        onClick={() => { setOpen(!open); setQuery(''); setCreating(false) }}
      >
        <span className={styles.triggerText}>{value || 'Peça...'}</span>
        <span className={styles.arrow}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className={styles.dropdown}>
          <input
            className={styles.search}
            autoFocus
            placeholder="Buscar peça..."
            value={query}
            onChange={(e) => { setQuery(e.target.value); setCreating(false) }}
          />

          <ul className={styles.list}>
            {filtered.length === 0 && !showCreate && (
              <li className={styles.empty}>Nenhuma peça encontrada</li>
            )}
            {filtered.map((label) => (
              <li
                key={label}
                className={`${styles.item} ${label === value ? styles.itemSelected : ''}`}
                onClick={() => select(label)}
              >
                <span className={styles.itemNome}>{label}</span>
              </li>
            ))}
          </ul>

          {showCreate && !creating && (
            <button className={styles.btnNovo} onClick={() => setCreating(true)}>
              + Criar peça "{query.trim()}"
            </button>
          )}

          {creating && (
            <div className={styles.createForm}>
              <div className={styles.createRow}>
                <input
                  className={styles.createInput}
                  type="number"
                  min={1}
                  placeholder="Prazo padrão (dias)"
                  value={diasNovo}
                  onChange={(e) => setDiasNovo(Number(e.target.value))}
                />
                <select
                  className={styles.createSelect}
                  value={tipoContagemNovo}
                  onChange={(e) => setTipoContagemNovo(e.target.value as 'uteis' | 'corridos')}
                >
                  <option value="uteis">úteis</option>
                  <option value="corridos">corridos</option>
                </select>
              </div>
              <div className={styles.createRow}>
                <button className={styles.btnCriar} onClick={handleCreate}>
                  Criar "{query.trim()}"
                </button>
                <button className={styles.btnCancelarCreate} onClick={() => setCreating(false)}>
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
