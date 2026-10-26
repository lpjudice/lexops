import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { estrutura } from '../../../api/estrutura'
import type { Dimensao, FiltrosCreditos } from '../../../api/estrutura'
import { baixarCsv, brlCurto } from './util'
import styles from './Estrutura.module.css'

const DIMS: { k: Dimensao; r: string }[] = [
  { k: 'devedora', r: 'Empresa devedora' }, { k: 'credor', r: 'Credor' }, { k: 'categoria', r: 'Categoria de dívida' }, { k: 'subcategoria', r: 'Subcategoria' },
  { k: 'classe', r: 'Classe' }, { k: 'origem', r: 'Origem (intragrupo/externo)' }, { k: 'nivel_devedora', r: 'Nível da devedora' }, { k: 'vencimento_mes', r: 'Mês de vencimento' },
]

/** Traduz (dimensão, valor) em filtro para detalhar uma célula na tabela. */
export function filtroDeDimensao(f: FiltrosCreditos, dim: Dimensao | '', chave: string): FiltrosCreditos {
  const n: FiltrosCreditos = { ...f }
  const mais = (k: 'categoria' | 'subcategoria' | 'classe' | 'devedor' | 'nivel_devedor' | 'credor') => { n[k] = [chave] }
  if (dim === 'devedora') mais('devedor'); else if (dim === 'credor') mais('credor'); else if (dim === 'categoria') mais('categoria')
  else if (dim === 'subcategoria' && chave !== '—') mais('subcategoria'); else if (dim === 'classe') mais('classe'); else if (dim === 'nivel_devedora') { if (chave.startsWith('(')) n.no_organograma = false; else mais('nivel_devedor') }
  else if (dim === 'origem') n.intragrupo = chave === 'Intragrupo'
  else if (dim === 'vencimento_mes' && /^\d{4}-\d{2}$/.test(chave)) {
    const [a, m] = chave.split('-').map(Number)
    n.venc_de = `${chave}-01`
    n.venc_ate = `${chave}-${String(new Date(a, m, 0).getDate()).padStart(2, '0')}`
  }
  return n
}

export default function PivotCreditos({ casoId, f, onDetalhar }: { casoId: string; f: FiltrosCreditos; onDetalhar: (f: FiltrosCreditos) => void }) {
  const [linhas, setLinhas] = useState<Dimensao>('devedora')
  const [colunas, setColunas] = useState<Dimensao | ''>('categoria')
  const q = useQuery({ queryKey: ['estrutura', 'pivot', casoId, f, linhas, colunas], queryFn: () => estrutura.agrupar(casoId, linhas, colunas, f), placeholderData: (p) => p })
  const p = q.data
  const maxCel = Math.max(1, ...(p?.linhas.flatMap((l) => Object.values(l.celulas).map((c) => c.valor_centavos)) ?? [1]))
  const exportar = () => {
    if (!p) return
    baixarCsv('tabela-dinamica.csv', [
      [DIMS.find((d) => d.k === linhas)?.r, ...p.colunas.map((c) => c.rotulo), 'Total'],
      ...p.linhas.map((l) => [l.rotulo, ...p.colunas.map((c) => (l.celulas[c.chave]?.valor_centavos ?? 0) / 100), l.valor_centavos / 100]),
    ])
  }
  return (
    <div className={styles.wrap}>
      <div className={styles.barra}>
        <label className={styles.campo}>Linhas
          <select aria-label="Linhas" value={linhas} onChange={(e) => setLinhas(e.target.value as Dimensao)}>{DIMS.map((d) => <option key={d.k} value={d.k}>{d.r}</option>)}</select></label>
        <label className={styles.campo}>Colunas
          <select aria-label="Colunas" value={colunas} onChange={(e) => setColunas(e.target.value as Dimensao | '')}><option value="">(só total)</option>{DIMS.filter((d) => d.k !== linhas).map((d) => <option key={d.k} value={d.k}>{d.r}</option>)}</select></label>
        <button className={styles.btnSec} onClick={exportar} disabled={!p}>Exportar CSV</button>
        <span className={styles.dica}>Clique numa célula, linha ou total para ver as linhas da planilha.</span>
      </div>
      {!p ? <p className={styles.vazio}>{q.isLoading ? 'Carregando…' : 'Sem dados.'}</p> : (
        <div className={styles.tabelaWrap}>
          <table className={styles.tabela}>
            <thead><tr><th>{DIMS.find((d) => d.k === linhas)?.r}</th>{p.colunas.map((c) => <th key={c.chave} className={styles.num} title={c.valor}>{c.rotulo}</th>)}<th className={styles.num}>Total</th></tr></thead>
            <tbody>
              {p.linhas.map((l) => (
                <tr key={l.chave}>
                  <th scope="row" style={{ fontWeight: 600, cursor: 'pointer' }} onClick={() => onDetalhar(filtroDeDimensao(f, linhas, l.chave))}>{l.rotulo}</th>
                  {p.colunas.map((c) => {
                    const cel = l.celulas[c.chave]
                    return <td key={c.chave} className={styles.celulaPivot} title={cel ? `${cel.valor} · ${cel.n} linha(s)` : undefined}
                      style={cel ? { background: `rgba(0,168,140,${0.08 + 0.5 * (cel.valor_centavos / maxCel)})` } : undefined}
                      onClick={() => cel && onDetalhar(colunas ? filtroDeDimensao(filtroDeDimensao(f, linhas, l.chave), colunas, c.chave) : filtroDeDimensao(f, linhas, l.chave))}>{cel ? brlCurto(cel.valor_centavos) : ''}</td>
                  })}
                  <td className={styles.celulaPivot} style={{ fontWeight: 800 }} onClick={() => onDetalhar(filtroDeDimensao(f, linhas, l.chave))} title={`${l.valor} · ${l.n} linha(s)`}>{brlCurto(l.valor_centavos)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr><td>Total{p.outras_linhas ? ` (+${p.outras_linhas} linhas menores não exibidas)` : ''}</td>{p.colunas.map((c) => <td key={c.chave} className={styles.num}>{brlCurto(c.valor_centavos)}</td>)}<td className={styles.num}>{brlCurto(p.total_centavos)}</td></tr></tfoot>
          </table>
        </div>
      )}
      {p && p.outras_colunas > 0 && <span className={styles.dica}>{p.outras_colunas} coluna(s) menor(es) não exibida(s) — filtre para detalhar.</span>}
    </div>
  )
}
