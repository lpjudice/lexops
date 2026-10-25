import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import { Id } from './EstrategiaAdvogados'
import styles from './Estrategia.module.css'

const COLUNAS_PRINCIPAIS = ['ativo_total', 'caixa_ou_saldo', 'passivo_total', 'endividamento_bruto', 'divida_liquida', 'patrimonio_liquido']

export default function EstrategiaMapa({ casoId }: { casoId: string }) {
  const q = useQuery({ queryKey: ['autos-ia', 'mapa-ent', casoId], queryFn: () => autosIa.mapaEntidades(casoId), staleTime: 30_000 })
  const [aberta, setAberta] = useState<string | null>(null)       // "entidade|medida"
  const [soComSaldo, setSoComSaldo] = useState(false)
  const r = q.data
  if (q.isLoading) return <p className={styles.vazio}>Carregando…</p>
  if (!r || r.entidades.length === 0) return <p className={styles.vazio}>Extraia os valores na aba "Números" para montar o mapa de ativo × passivo.</p>
  const medidas = r.medidas.filter((m) => COLUNAS_PRINCIPAIS.includes(m.chave) || r.entidades.some((e) => e.celulas[m.chave]))
  const entidades = r.entidades.filter((e) => !soComSaldo || e.saldo)
  const rotulo = (k: string) => r.medidas.find((m) => m.chave === k)?.rotulo ?? k

  return (
    <div className={styles.wrap}>
      <p className={styles.explica}>
        Para cada entidade, o valor <strong>mais sustentado pelas peças</strong> (citado em mais peças diferentes; empate → o mais recente) em cada medida. Clique num valor para ver as alternativas e as peças de origem.
        O <strong>saldo</strong> (ativo − passivo) é indicativo: junta números que podem vir de fontes e datas diferentes e não substitui um balanço.
      </p>
      <div className={styles.barra}>
        <span className={styles.dica}>{r.resumo.entidades} entidade(s) · {r.resumo.com_ativo_e_passivo} com ativo e passivo · {r.resumo.saldo_negativo} com passivo acima do ativo</span>
        <label className={styles.campo}><input type="checkbox" checked={soComSaldo} onChange={(e) => setSoComSaldo(e.target.checked)} /> só com ativo e passivo</label>
      </div>
      <div className={styles.tabelaWrap}>
        <table className={styles.tabela}>
          <thead><tr><th>Entidade</th>{medidas.map((m) => <th key={m.chave}>{m.rotulo}</th>)}<th>Ativo − passivo</th></tr></thead>
          <tbody>
            {entidades.map((e) => (
              <Fragment key={e.chave}>
                <tr>
                  <th scope="row"><span className={styles.nome}>{e.nome}</span>{e.grupo && <span className={styles.chip}>grupo</span>}{e.variantes.length > 0 && <div className={styles.dica} title={e.variantes.join(' · ')}>+{e.variantes.length} grafia(s)</div>}</th>
                  {medidas.map((m) => {
                    const c = e.celulas[m.chave]; const k = `${e.chave}|${m.chave}`
                    return (
                      <td key={m.chave}>
                        {c ? <button className={`${styles.celulaValor} ${aberta === k ? styles.pSel : ''}`} aria-expanded={aberta === k} onClick={() => setAberta(aberta === k ? null : k)}
                              title={`${c.principal.n_pecas} peça(s)${c.n_valores > 1 ? ` · ${c.n_valores} valores diferentes` : ''}`}>
                            {c.principal.valor}{c.n_valores > 1 && <span className={styles.dica}> +{c.n_valores - 1}</span>}
                          </button> : <span className={styles.dica}>—</span>}
                      </td>
                    )
                  })}
                  <td>
                    {e.saldo ? <span className={`${styles.pBadge} ${e.saldo.negativo ? styles.pCon : styles.pFav}`} title={e.saldo.mesma_fonte ? 'Há um afirmante em comum nos dois números' : 'Os dois números vêm de afirmantes diferentes'}>
                      {e.saldo.negativo ? '− ' : '+ '}{e.saldo.valor}{e.saldo.cobertura != null ? ` · cobre ${Math.round(e.saldo.cobertura * 100)}%` : ''}{e.saldo.mesma_fonte ? '' : ' *'}
                    </span> : <span className={styles.dica}>—</span>}
                  </td>
                </tr>
                {aberta?.startsWith(`${e.chave}|`) && (() => {
                  const medida = aberta.split('|')[1]; const c = e.celulas[medida]
                  if (!c) return null
                  return (
                    <tr><td colSpan={medidas.length + 2} className={styles.detalheCel}>
                      <div className={styles.dica}><strong>{e.nome}</strong> — {rotulo(medida)}</div>
                      {[c.principal, ...c.alternativas].map((v, i) => (
                        <div key={v.valor_centavos} className={styles.linha}>
                          <div className={styles.linhaTopo}>
                            <span className={styles.valor}>{v.valor}</span>
                            {i === 0 && <span className={styles.chip}>mais sustentado</span>}
                            <span className={styles.dica}>{v.n_pecas} peça(s) · {v.afirmantes.join(' · ')}</span>
                          </div>
                          <div className={styles.chips}>{v.fatos.map((f) => <span key={f.id} title={f.trecho ?? undefined}><Id p={f.peticao} /></span>)}</div>
                        </div>
                      ))}
                    </td></tr>
                  )
                })()}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.dica}>* saldo com ativo e passivo de afirmantes diferentes — confira as peças antes de usar.</p>
    </div>
  )
}
