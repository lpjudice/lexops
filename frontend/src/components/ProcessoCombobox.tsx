import { useEffect, useRef, useState } from 'react'
import type { Cliente } from '../api/clientes'
import type { EstadoProcesso, Processo } from '../api/processos'
import styles from './ClienteCombobox.module.css'

const ESTADOS: EstadoProcesso[] = ['ES', 'SP', 'AM', 'RJ', 'outro']

interface Props {
  value: string
  onChange: (id: string) => void
  processos: Processo[]
  clientes: Cliente[]
  onCreateProcesso: (data: { numero_cnj: string; cliente_id: string; estado: EstadoProcesso }) => Promise<string>
}

export default function ProcessoCombobox({ value, onChange, processos, clientes, onCreateProcesso }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [cnjNovo, setCnjNovo] = useState('')
  const [clienteNovo, setClienteNovo] = useState('')
  const [estadoNovo, setEstadoNovo] = useState<EstadoProcesso>('ES')
  const [saving, setSaving] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const clienteNome = (clienteId: string) => clientes.find((c) => c.id === clienteId)?.nome

  const selected = processos.find((p) => p.id === value)

  const filtered = processos.filter((p) =>
    p.numero_cnj.toLowerCase().includes(query.toLowerCase()) ||
    (clienteNome(p.cliente_id)?.toLowerCase().includes(query.toLowerCase()) ?? false)
  )

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

  const select = (id: string) => {
    onChange(id)
    setOpen(false)
    setQuery('')
  }

  const handleCreate = async () => {
    if (!cnjNovo.trim() || !clienteNovo) return
    setSaving(true)
    try {
      const id = await onCreateProcesso({ numero_cnj: cnjNovo.trim(), cliente_id: clienteNovo, estado: estadoNovo })
      select(id)
      setCreating(false)
      setCnjNovo('')
      setClienteNovo('')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={styles.root} ref={ref}>
      <div
        className={`${styles.trigger} ${open ? styles.triggerOpen : ''} ${!value ? styles.triggerEmpty : ''}`}
        onClick={() => { setOpen(!open); setQuery('') }}
      >
        <span className={styles.triggerText}>
          {selected ? selected.numero_cnj : 'Selecione ou pesquise...'}
        </span>
        <span className={styles.arrow}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className={styles.dropdown}>
          <input
            className={styles.search}
            autoFocus
            placeholder="Buscar por CNJ ou cliente..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          <ul className={styles.list}>
            {filtered.length === 0 && !creating && (
              <li className={styles.empty}>Nenhum processo encontrado</li>
            )}
            {filtered.map((p) => (
              <li
                key={p.id}
                className={`${styles.item} ${p.id === value ? styles.itemSelected : ''}`}
                onClick={() => select(p.id)}
              >
                <span className={styles.itemNome}>{p.numero_cnj}</span>
                <span className={styles.itemTipo}>{clienteNome(p.cliente_id) ?? '-'}</span>
              </li>
            ))}
          </ul>

          {!creating && (
            <button
              className={styles.btnNovo}
              onClick={() => { setCreating(true); setCnjNovo(query) }}
            >
              + Novo processo{query ? `: "${query}"` : ''}
            </button>
          )}

          {creating && (
            <div className={styles.createForm}>
              <input
                className={styles.createInput}
                placeholder="Número CNJ *"
                value={cnjNovo}
                autoFocus
                onChange={(e) => setCnjNovo(e.target.value)}
              />
              <div className={styles.createRow}>
                <select
                  className={styles.createSelect}
                  value={clienteNovo}
                  onChange={(e) => setClienteNovo(e.target.value)}
                >
                  <option value="">Cliente...</option>
                  {clientes.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                </select>
                <select
                  className={styles.createSelect}
                  value={estadoNovo}
                  onChange={(e) => setEstadoNovo(e.target.value as EstadoProcesso)}
                >
                  {ESTADOS.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
              </div>
              <div className={styles.createRow}>
                <button
                  className={styles.btnCriar}
                  disabled={!cnjNovo.trim() || !clienteNovo || saving}
                  onClick={handleCreate}
                >
                  {saving ? '...' : 'Criar'}
                </button>
                <button
                  className={styles.btnCancelarCreate}
                  onClick={() => setCreating(false)}
                >
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
