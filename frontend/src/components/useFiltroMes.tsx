import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'

/**
 * Filtro de período reutilizável (padrão da tela de Despacho):
 * - "Mês corrente" (default), "últimos 30/60/90 dias" e range manual (pickers).
 * - Colapsável: começa mostrando o mês atual, expande para escolher outro período.
 *
 * Uso:
 *   const filtro = useFiltroMes()
 *   ...
 *   {filtro.node}
 *   lista.filter((x) => filtro.dentro(x.data))
 */
const PRESETS_DIAS = [30, 60, 90] as const

export function useFiltroMes() {
  const [dias, setDias] = useState<number | null>(null) // null = mês corrente
  const [inicio, setInicio] = useState('')
  const [fim, setFim] = useState('')
  const [aberto, setAberto] = useState(false)

  const range = useMemo(() => {
    if (inicio || fim) {
      return {
        de: inicio ? new Date(inicio + 'T00:00:00') : null,
        ate: fim ? new Date(fim + 'T23:59:59') : null,
      }
    }
    if (dias) {
      const de = new Date()
      de.setHours(0, 0, 0, 0)
      de.setDate(de.getDate() - dias)
      return { de, ate: null as Date | null }
    }
    // Mês corrente
    const now = new Date()
    return {
      de: new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0, 0),
      ate: new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59),
    }
  }, [dias, inicio, fim])

  const dentro = (d?: string | null) => {
    if (!d) return false // itens sem data não entram na visão por mês
    const dt = new Date(d.length <= 10 ? d + 'T12:00:00' : d)
    if (range.de && dt < range.de) return false
    if (range.ate && dt > range.ate) return false
    return true
  }

  const ativo = !!(dias || inicio || fim)

  const btn = (on: boolean): CSSProperties => ({
    fontSize: 12, fontWeight: 600, padding: '5px 10px', borderRadius: 6, cursor: 'pointer',
    border: on ? 'none' : '1px solid #ddd',
    background: on ? 'var(--teal, #14b8a6)' : '#fff',
    color: on ? '#fff' : 'var(--dark, #1d1e20)',
    fontFamily: 'inherit',
  })

  const label = (() => {
    if (inicio || fim) return `${inicio || '…'} até ${fim || '…'}`
    if (dias) return `últimos ${dias} dias`
    const now = new Date()
    return now.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
  })()

  const node = (
    <div style={{ marginBottom: 14 }}>
      {!aberto ? (
        <button
          onClick={() => setAberto(true)}
          style={{ fontSize: 12, fontWeight: 600, color: 'var(--teal, #0d9488)', background: '#fff', border: '1px solid var(--teal, #14b8a6)', borderRadius: 999, padding: '5px 12px', cursor: 'pointer', fontFamily: 'inherit' }}
        >
          📅 {ativo ? `Período: ${label} — ajustar` : `Mês atual (${label}) — ver outros períodos`}
        </button>
      ) : (
        <div style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 12, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={() => { setDias(null); setInicio(''); setFim('') }} style={btn(!ativo)}>Mês corrente</button>
          {PRESETS_DIAS.map((d) => (
            <button key={d} onClick={() => { setDias(d); setInicio(''); setFim('') }} style={btn(dias === d)}>
              últimos {d} dias
            </button>
          ))}
          <span style={{ fontSize: 12, color: 'var(--gray-mid, #6b7280)' }}>ou:</span>
          <input type="date" value={inicio} onChange={(e) => { setInicio(e.target.value); setDias(null) }}
            style={{ fontSize: 12, padding: '5px 8px', border: '1px solid #ddd', borderRadius: 6 }} />
          <span style={{ fontSize: 12, color: 'var(--gray-mid, #6b7280)' }}>até</span>
          <input type="date" value={fim} onChange={(e) => { setFim(e.target.value); setDias(null) }}
            style={{ fontSize: 12, padding: '5px 8px', border: '1px solid #ddd', borderRadius: 6 }} />
          <button onClick={() => setAberto(false)} style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: 'var(--gray-mid, #6b7280)', background: 'none', border: '1px solid #ddd', borderRadius: 6, padding: '5px 10px', cursor: 'pointer', fontFamily: 'inherit' }}>
            Recolher
          </button>
        </div>
      )}
    </div>
  )

  // Só filtra de fato quando o usuário abriu o painel ou escolheu um período;
  // assim a lista não esconde itens antes de o filtro ser engajado.
  const aplicar = aberto || ativo

  return { node, dentro, ativo, aplicar, range }
}
