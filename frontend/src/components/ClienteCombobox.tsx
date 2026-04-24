import { useEffect, useRef, useState } from 'react'
import type { Cliente } from '../api/clientes'
import styles from './ClienteCombobox.module.css'

interface Props {
  value: string
  onChange: (id: string) => void
  clientes: Cliente[]
  onCreateCliente: (nome: string) => Promise<string>
}

export default function ClienteCombobox({ value, onChange, clientes, onCreateCliente }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [nomeNovo, setNomeNovo] = useState('')
  const [tipoNovo, setTipoNovo] = useState<'PF' | 'PJ'>('PF')
  const [saving, setSaving] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const selected = clientes.find((c) => c.id === value)

  const filtered = clientes.filter((c) =>
    c.nome.toLowerCase().includes(query.toLowerCase())
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
    if (!nomeNovo.trim()) return
    setSaving(true)
    try {
      // Pass nome|tipo — parent handles API call; incompleto is set by parent
      const id = await onCreateCliente(nomeNovo.trim() + '|' + tipoNovo)
      select(id)
      setCreating(false)
      setNomeNovo('')
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
          {selected ? selected.nome : 'Selecione ou pesquise...'}
        </span>
        <span className={styles.arrow}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className={styles.dropdown}>
          <input
            className={styles.search}
            autoFocus
            placeholder="Buscar cliente..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          <ul className={styles.list}>
            {filtered.length === 0 && !creating && (
              <li className={styles.empty}>Nenhum cliente encontrado</li>
            )}
            {filtered.map((c) => (
              <li
                key={c.id}
                className={`${styles.item} ${c.id === value ? styles.itemSelected : ''}`}
                onClick={() => select(c.id)}
              >
                <span className={styles.itemNome}>{c.nome}</span>
                <span className={styles.itemTipo}>{c.tipo}</span>
              </li>
            ))}
          </ul>

          {!creating && (
            <button
              className={styles.btnNovo}
              onClick={() => { setCreating(true); setNomeNovo(query) }}
            >
              + Novo cliente{query ? `: "${query}"` : ''}
            </button>
          )}

          {creating && (
            <div className={styles.createForm}>
              <input
                className={styles.createInput}
                placeholder="Nome do cliente *"
                value={nomeNovo}
                autoFocus
                onChange={(e) => setNomeNovo(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              />
              <div className={styles.createRow}>
                <select
                  className={styles.createSelect}
                  value={tipoNovo}
                  onChange={(e) => setTipoNovo(e.target.value as 'PF' | 'PJ')}
                >
                  <option value="PF">Pessoa Física</option>
                  <option value="PJ">Pessoa Jurídica</option>
                </select>
                <button
                  className={styles.btnCriar}
                  disabled={!nomeNovo.trim() || saving}
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
