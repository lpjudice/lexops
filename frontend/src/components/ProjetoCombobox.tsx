import { useState, useRef, useEffect } from 'react'
import type { TarefaProjeto } from '../api/tarefaProjetos'

const CORES = [
  '#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f97316',
  '#eab308', '#22c55e', '#14b8a6', '#3b82f6', '#64748b',
]

interface Props {
  projetos: TarefaProjeto[]
  value: string               // projeto_id selecionado
  onChange: (id: string) => void
  onCriar: (nome: string, cor: string) => Promise<TarefaProjeto>
  disabled?: boolean
}

export default function ProjetoCombobox({ projetos, value, onChange, onCriar, disabled }: Props) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [criando, setCriando] = useState(false)
  const [novaCor, setNovaCor] = useState(CORES[0])
  const [loading, setLoading] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const visiveis = projetos.filter(p => !p.oculto)
  const selecionado = visiveis.find(p => p.id === value) ?? null

  const filtrados = query.trim()
    ? visiveis.filter(p => p.nome.toLowerCase().includes(query.toLowerCase()))
    : visiveis

  const queryNaoExiste = query.trim() && !visiveis.some(p => p.nome.toLowerCase() === query.trim().toLowerCase())

  // Fecha ao clicar fora
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setCriando(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function handleCriar() {
    if (!query.trim() || loading) return
    setLoading(true)
    try {
      const novo = await onCriar(query.trim(), novaCor)
      onChange(novo.id)
      setOpen(false)
      setCriando(false)
      setQuery('')
      setNovaCor(CORES[0])
    } finally {
      setLoading(false)
    }
  }

  const inputDisplay = open ? query : (selecionado?.nome ?? '')

  return (
    <div ref={ref} style={{ position: 'relative', width: '100%' }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          border: '1px solid #e5e7eb', borderRadius: 8, padding: '6px 10px',
          background: disabled ? '#f9fafb' : '#fff', cursor: disabled ? 'default' : 'pointer',
          borderLeft: selecionado ? `4px solid ${selecionado.cor}` : undefined,
        }}
        onClick={() => { if (!disabled) { setOpen(true); setQuery('') } }}
      >
        {selecionado && !open && (
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: selecionado.cor, flexShrink: 0 }} />
        )}
        <input
          value={inputDisplay}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setCriando(false) }}
          onFocus={() => { setOpen(true); setQuery('') }}
          placeholder="Projeto (opcional)"
          disabled={disabled}
          style={{
            flex: 1, border: 'none', outline: 'none', fontSize: 13, background: 'transparent',
            color: selecionado && !open ? (selecionado.cor) : '#1d1e20', fontFamily: 'inherit',
            fontWeight: selecionado && !open ? 600 : 400,
          }}
        />
        {value && !open && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onChange(''); setQuery('') }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 14, padding: 0, lineHeight: 1 }}
          >×</button>
        )}
      </div>

      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
          background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10,
          boxShadow: '0 8px 24px rgba(0,0,0,.12)', marginTop: 4, overflow: 'hidden',
        }}>
          {filtrados.length === 0 && !queryNaoExiste && (
            <div style={{ padding: '10px 14px', fontSize: 13, color: '#9ca3af' }}>
              Nenhum projeto. Digite para criar.
            </div>
          )}
          {filtrados.map(p => (
            <div
              key={p.id}
              onClick={() => { onChange(p.id); setOpen(false); setQuery('') }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px',
                cursor: 'pointer', fontSize: 13,
                background: p.id === value ? '#f5f3ff' : '#fff',
                color: p.id === value ? p.cor : '#1d1e20',
                fontWeight: p.id === value ? 600 : 400,
              }}
              onMouseEnter={e => (e.currentTarget.style.background = '#f9fafb')}
              onMouseLeave={e => (e.currentTarget.style.background = p.id === value ? '#f5f3ff' : '#fff')}
            >
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: p.cor, flexShrink: 0 }} />
              {p.nome}
              {p.id === value && <span style={{ marginLeft: 'auto', fontSize: 11 }}>✓</span>}
            </div>
          ))}

          {queryNaoExiste && !criando && (
            <div
              onClick={() => setCriando(true)}
              style={{
                padding: '9px 14px', fontSize: 13, cursor: 'pointer', color: '#6366f1', fontWeight: 600,
                borderTop: filtrados.length > 0 ? '1px solid #f3f4f6' : undefined,
                display: 'flex', alignItems: 'center', gap: 8,
              }}
              onMouseEnter={e => (e.currentTarget.style.background = '#f5f3ff')}
              onMouseLeave={e => (e.currentTarget.style.background = '#fff')}
            >
              <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
              Criar projeto "{query.trim()}"
            </div>
          )}

          {criando && (
            <div style={{ padding: '12px 14px', borderTop: '1px solid #f3f4f6' }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', margin: '0 0 8px' }}>Escolha a cor:</p>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                {CORES.map(c => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setNovaCor(c)}
                    style={{
                      width: 20, height: 20, borderRadius: '50%', background: c, cursor: 'pointer', padding: 0,
                      border: novaCor === c ? '3px solid #1d1e20' : '2px solid transparent',
                    }}
                  />
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  onClick={handleCriar}
                  disabled={loading}
                  style={{
                    flex: 1, fontSize: 13, background: novaCor, color: '#fff', border: 'none',
                    borderRadius: 8, padding: '7px 0', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600,
                  }}
                >
                  {loading ? 'Criando...' : `Criar "${query.trim()}"`}
                </button>
                <button
                  type="button"
                  onClick={() => setCriando(false)}
                  style={{ fontSize: 13, background: 'none', border: '1px solid #e5e7eb', borderRadius: 8, padding: '7px 12px', cursor: 'pointer', color: '#6b7280', fontFamily: 'inherit' }}
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
