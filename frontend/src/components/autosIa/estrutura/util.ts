import type { FiltrosCreditos } from '../../../api/estrutura'

export const brl = (centavos: number) => (centavos / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
/** R$ compacto para caixas pequenas: 1,2 mi · 985,6 mi · 3,4 bi · 12,3 mil */
export const brlCurto = (centavos: number) => {
  const v = Math.abs(centavos) / 100
  const s = v >= 1e9 ? `${(v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} bi` : v >= 1e6 ? `${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`
    : v >= 1e3 ? `${(v / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mil` : v.toLocaleString('pt-BR', { maximumFractionDigits: 0 })
  return `${centavos < 0 ? '−' : ''}R$ ${s}`
}
export const dataBr = (d: string | null) => (d ? d.split('-').reverse().join('/') : '—')
export const pctTxt = (p: number | null) => (p == null ? '—' : `${p.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`)

export const COR_NIVEL: Record<string, { bg: string; fg: string; borda: string }> = {
  'Holding': { bg: '#0b1f4d', fg: '#ffffff', borda: '#0b1f4d' },
  'Unidade de Negócio': { bg: '#dbeafe', fg: '#1e3a8a', borda: '#60a5fa' },
  'Investimentos': { bg: '#ccfbf1', fg: '#115e59', borda: '#2dd4bf' },
  'Veículo de Investimento': { bg: '#f1f5f9', fg: '#334155', borda: '#94a3b8' },
  'Projeto / SPE': { bg: '#fef3c7', fg: '#92400e', borda: '#fbbf24' },
  'Operacional': { bg: '#dcfce7', fg: '#166534', borda: '#4ade80' },
}
export const corNivel = (n: string | null) => COR_NIVEL[n ?? ''] ?? { bg: '#ffffff', fg: '#334155', borda: '#cbd5e1' }

/** Rótulo legível de cada filtro ativo (para as "etiquetas" removíveis). */
export function etiquetasFiltros(f: FiltrosCreditos, nomeDevedora: (c: string) => string, nomeCredor: (c: string) => string): { chave: keyof FiltrosCreditos; valor?: string; rotulo: string }[] {
  const out: { chave: keyof FiltrosCreditos; valor?: string; rotulo: string }[] = []
  ;(f.categoria ?? []).forEach((v) => out.push({ chave: 'categoria', valor: v, rotulo: `Categoria: ${v}` }))
  ;(f.subcategoria ?? []).forEach((v) => out.push({ chave: 'subcategoria', valor: v, rotulo: `Subcategoria: ${v}` }))
  ;(f.classe ?? []).forEach((v) => out.push({ chave: 'classe', valor: v, rotulo: `Classe: ${v}` }))
  ;(f.devedor ?? []).forEach((v) => out.push({ chave: 'devedor', valor: v, rotulo: `Devedora: ${nomeDevedora(v)}` }))
  ;(f.nivel_devedor ?? []).forEach((v) => out.push({ chave: 'nivel_devedor', valor: v, rotulo: `Nível da devedora: ${v}` }))
  ;(f.credor ?? []).forEach((v) => out.push({ chave: 'credor', valor: v, rotulo: `Credor: ${nomeCredor(v)}` }))
  if (f.credor_q) out.push({ chave: 'credor_q', rotulo: `Credor contém “${f.credor_q}”` })
  if (f.natureza_q) out.push({ chave: 'natureza_q', rotulo: `Natureza contém “${f.natureza_q}”` })
  if (f.q) out.push({ chave: 'q', rotulo: `Busca “${f.q}”` })
  if (f.intragrupo !== undefined) out.push({ chave: 'intragrupo', rotulo: f.intragrupo ? 'Só intragrupo' : 'Só credores externos' })
  if (f.vencidos !== undefined) out.push({ chave: 'vencidos', rotulo: f.vencidos ? 'Só vencidos' : 'Só a vencer' })
  if (f.com_coobrigado !== undefined) out.push({ chave: 'com_coobrigado', rotulo: f.com_coobrigado ? 'Com coobrigado/fiador' : 'Sem coobrigado' })
  if (f.no_organograma !== undefined) out.push({ chave: 'no_organograma', rotulo: f.no_organograma ? 'Devedora no organograma' : 'Devedora fora do organograma' })
  if (f.valor_min !== undefined) out.push({ chave: 'valor_min', rotulo: `Valor ≥ R$ ${f.valor_min.toLocaleString('pt-BR')}` })
  if (f.valor_max !== undefined) out.push({ chave: 'valor_max', rotulo: `Valor ≤ R$ ${f.valor_max.toLocaleString('pt-BR')}` })
  if (f.venc_de) out.push({ chave: 'venc_de', rotulo: `Vence a partir de ${dataBr(f.venc_de)}` })
  if (f.venc_ate) out.push({ chave: 'venc_ate', rotulo: `Vence até ${dataBr(f.venc_ate)}` })
  return out
}

export function removerFiltro(f: FiltrosCreditos, chave: keyof FiltrosCreditos, valor?: string): FiltrosCreditos {
  const n: any = { ...f }
  if (valor !== undefined && Array.isArray(n[chave])) { n[chave] = n[chave].filter((x: string) => x !== valor); if (!n[chave].length) delete n[chave] } else delete n[chave]
  return n
}

export function baixarCsv(nome: string, linhas: (string | number | null | undefined)[][]) {
  const esc = (v: string | number | null | undefined) => { const s = v == null ? '' : String(v); return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
  const blob = new Blob(['﻿' + linhas.map((l) => l.map(esc).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = nome; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
