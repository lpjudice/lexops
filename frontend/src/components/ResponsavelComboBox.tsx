/**
 * ComboBox de responsável — unifica usuários do sistema e responsáveis
 * "manuais" (advogados/terceiros sem login) numa lista só, pesquisável.
 *
 * - Busca em /responsaveis (inclui usuários sincronizados automaticamente).
 * - "+ Novo responsável" cria um responsável manual (nome, email, telefone,
 *   OAB/UF, categoria) sem sair do combobox.
 * - Emite { id, nome, email } — `id` é o Responsavel.id (fonte de verdade
 *   pra evitar duplicidade); nome/email seguem sendo gravados também, pra
 *   manter compatibilidade com telas que só leem essas duas colunas.
 */
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { responsaveisApi } from '../api/responsaveis'
import type { CategoriaResponsavel, Responsavel } from '../api/responsaveis'

export interface ResponsavelValue {
  nome: string
  email: string
  id?: string | null
}

interface Props {
  value: ResponsavelValue
  onChange: (v: ResponsavelValue) => void
  disabled?: boolean
}

const CATEGORIA_LABEL: Record<CategoriaResponsavel, string> = {
  advogado: '⚖️ Advogado',
  terceiro: '🤝 Terceiro',
  colaborador: '👥 Colaborador',
  financeiro: '💰 Financeiro',
}

export default function ResponsavelComboBox({ value, onChange, disabled }: Props) {
  const qc = useQueryClient()
  const { data: responsaveis = [] } = useQuery({
    queryKey: ['responsaveis'],
    queryFn: () => responsaveisApi.listar(),
    staleTime: 30_000,
  })

  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const [criando, setCriando] = useState(false)
  const [novo, setNovo] = useState({ nome: '', email: '', telefone: '', oab_numero: '', oab_uf: '', categoria: 'terceiro' as CategoriaResponsavel })
  const [salvando, setSalvando] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const selecionado = value.id ? responsaveis.find((r) => r.id === value.id) : undefined

  useEffect(() => {
    if (!focused) setQuery(value.nome || '')
  }, [value.nome, focused])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setFocused(false)
        setCriando(false)
        setQuery(value.nome || '')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [value.nome])

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
    boxShadow: '0 4px 16px rgba(0,0,0,.1)', maxHeight: 300, overflowY: 'auto',
    marginTop: 2,
  }

  const optStyle = (sel: boolean): React.CSSProperties => ({
    padding: '8px 12px', cursor: 'pointer', fontSize: 13,
    background: sel ? '#eff6ff' : '#fff',
    borderBottom: '1px solid #f9fafb',
    color: '#1d1e20',
  })

  const filtrados = responsaveis.filter(
    (r) =>
      !query ||
      r.nome.toLowerCase().includes(query.toLowerCase()) ||
      (r.email || '').toLowerCase().includes(query.toLowerCase())
  )

  const handleSelect = (r: Responsavel) => {
    onChange({ id: r.id, nome: r.nome, email: r.email || '' })
    setQuery(r.nome)
    setOpen(false)
    setFocused(false)
  }

  const handleClear = () => {
    onChange({ id: null, nome: '', email: '' })
    setQuery('')
  }

  const handleCriar = async () => {
    if (!novo.nome.trim()) return
    setSalvando(true)
    try {
      const criado = await responsaveisApi.criar({
        nome: novo.nome.trim(),
        email: novo.email.trim() || null,
        telefone: novo.telefone.trim() || null,
        oab_numero: novo.oab_numero.trim() || null,
        oab_uf: novo.oab_uf.trim() || null,
        categoria: novo.categoria,
      })
      qc.invalidateQueries({ queryKey: ['responsaveis'] })
      onChange({ id: criado.id, nome: criado.nome, email: criado.email || '' })
      setQuery(criado.nome)
      setCriando(false)
      setOpen(false)
      setNovo({ nome: '', email: '', telefone: '', oab_numero: '', oab_uf: '', categoria: 'terceiro' })
    } finally {
      setSalvando(false)
    }
  }

  if (criando) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, border: '1px solid #e5e7eb', borderRadius: 8, padding: 10, background: '#fafafa' }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <input style={{ ...inputStyle, flex: 1 }} placeholder="Nome *" value={novo.nome}
            onChange={(e) => setNovo({ ...novo, nome: e.target.value })} autoFocus />
          <button type="button" onClick={() => setCriando(false)}
            style={{ padding: '0 10px', fontSize: 13, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', cursor: 'pointer', color: '#6b7280' }}>✕</button>
        </div>
        <input style={inputStyle} placeholder="Email (opcional, para notificações)" type="email" value={novo.email}
          onChange={(e) => setNovo({ ...novo, email: e.target.value })} />
        <div style={{ display: 'flex', gap: 6 }}>
          <input style={{ ...inputStyle, flex: 1 }} placeholder="Telefone/WhatsApp (opcional)" value={novo.telefone}
            onChange={(e) => setNovo({ ...novo, telefone: e.target.value })} />
          <input style={{ ...inputStyle, width: 100 }} placeholder="OAB nº" value={novo.oab_numero}
            onChange={(e) => setNovo({ ...novo, oab_numero: e.target.value })} />
          <input style={{ ...inputStyle, width: 55 }} placeholder="UF" maxLength={2} value={novo.oab_uf}
            onChange={(e) => setNovo({ ...novo, oab_uf: e.target.value.toUpperCase() })} />
        </div>
        <select style={inputStyle} value={novo.categoria} onChange={(e) => setNovo({ ...novo, categoria: e.target.value as CategoriaResponsavel })}>
          {(Object.keys(CATEGORIA_LABEL) as CategoriaResponsavel[]).map((c) => (
            <option key={c} value={c}>{CATEGORIA_LABEL[c]}</option>
          ))}
        </select>
        <button type="button" onClick={handleCriar} disabled={salvando || !novo.nome.trim()}
          style={{ fontSize: 13, fontWeight: 600, color: '#fff', background: 'var(--teal, #0d9488)', border: 'none', borderRadius: 8, padding: '8px 12px', cursor: 'pointer' }}>
          {salvando ? 'Salvando...' : 'Criar e selecionar'}
        </button>
      </div>
    )
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <input
        style={inputStyle}
        value={query}
        placeholder="Buscar responsável..."
        disabled={disabled}
        autoComplete="off"
        onChange={(e) => { setQuery(e.target.value); setOpen(true); if (!e.target.value) onChange({ id: null, nome: '', email: '' }) }}
        onFocus={() => { setQuery(''); setOpen(true); setFocused(true) }}
        onBlur={() => { setFocused(false); setTimeout(() => setQuery(value.nome || ''), 150) }}
      />
      {open && (
        <div style={dropStyle}>
          {filtrados.length === 0 && (
            <div style={{ padding: '8px 12px', fontSize: 13, color: '#9ca3af' }}>Nenhum responsável encontrado</div>
          )}
          {filtrados.map((r) => (
            <div key={r.id} style={optStyle(r.id === selecionado?.id)} onMouseDown={() => handleSelect(r)}>
              <div style={{ fontWeight: 500 }}>
                {r.nome} {r.eh_usuario_sistema && <span style={{ fontSize: 10, color: '#0d9488' }}>· sistema</span>}
              </div>
              <div style={{ fontSize: 11, color: '#6b7280' }}>
                {CATEGORIA_LABEL[r.categoria]}{r.email ? ` · ${r.email}` : ''}
              </div>
            </div>
          ))}
          <div
            style={{ ...optStyle(false), borderTop: '1px solid #e5e7eb', color: '#6b7280', fontStyle: 'italic' }}
            onMouseDown={(e) => { e.preventDefault(); setCriando(true); setNovo((n) => ({ ...n, nome: query })) }}
          >
            + Novo responsável
          </div>
          {value.nome && (
            <div style={{ ...optStyle(false), color: '#dc2626', fontSize: 12 }} onMouseDown={handleClear}>
              ✕ Remover responsável
            </div>
          )}
        </div>
      )}
    </div>
  )
}
