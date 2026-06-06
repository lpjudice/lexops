/**
 * ComboBox de responsável por tarefa.
 *
 * - Mostra usuários ativos do sistema como opções pesquisáveis.
 * - Opção "Terceiros" expande campos de nome e email manuais.
 * - Emite { nome, email } ao selecionar.
 */
import { useEffect, useRef, useState } from 'react'
import type { Usuario } from '../api/usuarios'

interface ResponsavelValue {
  nome: string
  email: string
}

interface Props {
  value: ResponsavelValue
  onChange: (v: ResponsavelValue) => void
  usuarios: Usuario[]
  disabled?: boolean
}


export default function ResponsavelComboBox({ value, onChange, usuarios, disabled }: Props) {
  const ativos = usuarios.filter((u) => u.ativo)

  // Resolve se o valor atual é um usuário do sistema ou "Terceiros"
  const isSystemUser = ativos.some((u) => u.nome === value.nome && u.email === value.email)
  const isTerceiros = !isSystemUser && value.nome !== ''

  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const [mode, setMode] = useState<'system' | 'terceiros'>(isTerceiros ? 'terceiros' : 'system')
  const ref = useRef<HTMLDivElement>(null)

  // Sync query when value changes externally
  useEffect(() => {
    if (!focused) {
      if (isSystemUser) setQuery(value.nome)
      else if (!value.nome) setQuery('')
    }
  }, [value, focused, isSystemUser])

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setFocused(false)
        if (!focused) {
          // Restore label
          if (isSystemUser) setQuery(value.nome)
          else if (!value.nome) setQuery('')
        }
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [focused, isSystemUser, value.nome])

  const inputStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box',
    padding: '8px 12px', fontSize: 14, borderRadius: 8,
    border: '1px solid #e5e7eb', outline: 'none', fontFamily: 'inherit',
    background: disabled ? '#f9fafb' : '#fff',
    color: '#1d1e20',
  }

  const dropStyle: React.CSSProperties = {
    position: 'absolute', left: 0, right: 0, top: '100%', zIndex: 50,
    background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
    boxShadow: '0 4px 16px rgba(0,0,0,.1)', maxHeight: 260, overflowY: 'auto',
    marginTop: 2,
  }

  const optStyle = (selected: boolean): React.CSSProperties => ({
    padding: '8px 12px', cursor: 'pointer', fontSize: 13,
    background: selected ? '#eff6ff' : '#fff',
    borderBottom: '1px solid #f9fafb',
    color: '#1d1e20',
  })

  const filtered = ativos.filter(
    (u) =>
      !query ||
      u.nome.toLowerCase().includes(query.toLowerCase()) ||
      u.email.toLowerCase().includes(query.toLowerCase())
  )

  const handleSelectUser = (u: Usuario) => {
    onChange({ nome: u.nome, email: u.email })
    setQuery(u.nome)
    setOpen(false)
    setFocused(false)
    setMode('system')
  }

  const handleSelectTerceiros = () => {
    setMode('terceiros')
    setOpen(false)
    setQuery('')
    onChange({ nome: '', email: '' })
  }

  const handleClear = () => {
    onChange({ nome: '', email: '' })
    setQuery('')
    setMode('system')
  }

  // ── Terceiros mode ────────────────────────────────────────────────────
  if (mode === 'terceiros') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            style={{ ...inputStyle, flex: 1 }}
            placeholder="Nome do responsável *"
            value={value.nome}
            onChange={(e) => onChange({ ...value, nome: e.target.value })}
            disabled={disabled}
          />
          <button
            type="button"
            onClick={handleClear}
            style={{ padding: '0 10px', fontSize: 13, border: '1px solid #e5e7eb', borderRadius: 8, background: '#f9fafb', cursor: 'pointer', color: '#6b7280' }}
            title="Voltar para usuários do sistema"
          >✕</button>
        </div>
        <input
          style={inputStyle}
          placeholder="Email (para notificação)"
          type="email"
          value={value.email}
          onChange={(e) => onChange({ ...value, email: e.target.value })}
          disabled={disabled}
        />
      </div>
    )
  }

  // ── System user mode ─────────────────────────────────────────────────
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <input
        style={inputStyle}
        value={query}
        placeholder="Buscar usuário do sistema..."
        disabled={disabled}
        autoComplete="off"
        onChange={(e) => { setQuery(e.target.value); setOpen(true); if (!e.target.value) onChange({ nome: '', email: '' }) }}
        onFocus={() => { setQuery(''); setOpen(true); setFocused(true) }}
        onBlur={() => {
          setFocused(false)
          setTimeout(() => {
            if (isSystemUser) setQuery(value.nome)
            else if (!value.nome) setQuery('')
          }, 150)
        }}
      />
      {open && (
        <div style={dropStyle}>
          {filtered.length === 0 && (
            <div style={{ padding: '8px 12px', fontSize: 13, color: '#9ca3af' }}>Nenhum usuário encontrado</div>
          )}
          {filtered.map((u) => (
            <div
              key={u.id}
              style={optStyle(u.nome === value.nome)}
              onMouseDown={() => handleSelectUser(u)}
            >
              <div style={{ fontWeight: 500 }}>{u.nome}</div>
              <div style={{ fontSize: 11, color: '#6b7280' }}>{u.email}</div>
            </div>
          ))}
          <div
            style={{ ...optStyle(false), borderTop: '1px solid #e5e7eb', color: '#6b7280', fontStyle: 'italic' }}
            onMouseDown={handleSelectTerceiros}
          >
            + Terceiros (nome e email manual)
          </div>
          {value.nome && (
            <div
              style={{ ...optStyle(false), color: '#dc2626', fontSize: 12 }}
              onMouseDown={handleClear}
            >
              ✕ Remover responsável
            </div>
          )}
        </div>
      )}
    </div>
  )
}
