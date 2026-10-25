import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import type { PeticaoRef } from '../../api/autosIa'
import styles from './Estrategia.module.css'

type Visao = 'valor' | 'bancas' | 'pares' | 'blocos'
const dataBr = (d: string | null) => (d ? d.split('-').reverse().join('/') : '')

export function Id({ p }: { p: PeticaoRef }) {
  const rotulo = p.id_processual || 's/ ID'
  const principal = p.link_pdf || p.link_md
  return (
    <span className={styles.idWrap}>
      {principal
        ? <a className={styles.id} href={principal} target="_blank" rel="noreferrer" title={`${p.link_pdf ? 'Abrir PDF' : 'Abrir .md'} — ${p.titulo}${p.data ? ` · ${dataBr(p.data)}` : ''}`}>{rotulo}</a>
        : <span className={styles.idSem}>{rotulo}</span>}
      {p.link_pdf && p.link_md && <a className={styles.idMd} href={p.link_md} target="_blank" rel="noreferrer" title="Abrir resumo + inteiro teor (.md)">md</a>}
    </span>
  )
}

const quem = (a: { nome: string | null; id: string }) => a.nome || a.id

export default function EstrategiaAdvogados({ casoId }: { casoId: string }) {
  const [visao, setVisao] = useState<Visao>('valor')
  const [minPartes, setMinPartes] = useState(2)
  const [abertos, setAbertos] = useState<Set<string>>(new Set())
  const [trechos, setTrechos] = useState<Set<string>>(new Set())
  const q = useQuery({ queryKey: ['autos-ia', 'adv-cruz', casoId, minPartes], queryFn: () => autosIa.cruzamentosAdvogados(casoId, minPartes) })
  const alternar = (s: Set<string>, k: string, set: (n: Set<string>) => void) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); set(n) }
  const r = q.data

  return (
    <div className={styles.wrap}>
      <p className={styles.explica}>
        Cruza quem representa quem com os números das peças. O <strong>valor indicativo</strong> soma, por parte, o valor que as peças atribuem a ela (seu aporte, crédito ou prejuízo) —
        é um ponto de partida para dimensionar a carteira de cada advogado, não um total apurado: partes sem valor localizado ficam de fora e valores podem se sobrepor entre advogados.
      </p>
      <div className={styles.barra}>
        <div className={styles.seg} role="tablist" aria-label="Cruzamento">
          <button role="tab" aria-selected={visao === 'valor'} className={visao === 'valor' ? styles.segOn : ''} onClick={() => setVisao('valor')}>Valor por advogado</button>
          <button role="tab" aria-selected={visao === 'bancas'} className={visao === 'bancas' ? styles.segOn : ''} onClick={() => setVisao('bancas')}>Bancas <span className={styles.n}>{r?.resumo.bancas ?? 0}</span></button>
          <button role="tab" aria-selected={visao === 'pares'} className={visao === 'pares' ? styles.segOn : ''} onClick={() => setVisao('pares')}>Advogados em comum <span className={styles.n}>{r?.resumo.pares ?? 0}</span></button>
          <button role="tab" aria-selected={visao === 'blocos'} className={visao === 'blocos' ? styles.segOn : ''} onClick={() => setVisao('blocos')}>Partes representadas em bloco <span className={styles.n}>{r?.resumo.blocos ?? 0}</span></button>
        </div>
        {visao !== 'valor' && (
          <label className={styles.campo}>mín. de partes em comum
            <select value={minPartes} onChange={(e) => setMinPartes(Number(e.target.value))} aria-label="Mínimo de partes em comum">
              {[1, 2, 3, 5, 10].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
        {r && <span className={styles.dica}>{r.resumo.partes_com_valor} de {r.resumo.partes} partes com valor localizado</span>}
      </div>
      {q.isLoading && <p className={styles.vazio}>Carregando…</p>}
      {r && r.resumo.advogados === 0 && <p className={styles.vazio}>Nenhum advogado mapeado ainda (aba "Advogados & Partes").</p>}

      {r && visao === 'valor' && r.advogados.map((a) => {
        const k = `a${a.id}`
        return (
          <div key={a.id} className={styles.card}>
            <button className={styles.cardHead} aria-expanded={abertos.has(k)} onClick={() => alternar(abertos, k, setAbertos)}>
              <span className={styles.chevron}>{abertos.has(k) ? '▾' : '▸'}</span>
              <span className={styles.titulo}>{quem(a)}</span>
              <span className={styles.dica}>{a.oabs.join(' · ')}</span>
              <span className={styles.valorG}>{a.valor_indicativo ?? '—'}</span>
              <span className={styles.conta}>{a.n_partes} parte(s) · {a.n_partes_com_valor} com valor</span>
            </button>
            {abertos.has(k) && (
              <div className={styles.corpo}>
                {a.partes.map((p) => {
                  const tk = `${a.id}|${p.chave}`
                  return (
                    <div key={p.chave} className={styles.linha}>
                      <div className={styles.linhaTopo}>
                        <span className={styles.nome}>{p.principal && <span title="Advogado principal desta parte">★ </span>}{p.nome}</span>
                        {p.valor_info
                          ? <><span className={styles.valor}>{p.valor}</span><span className={styles.chip}>{p.valor_info.tema_rotulo}</span><Id p={p.valor_info.peticao} />
                              <span className={styles.dica}>{p.valor_info.n_pecas} peça(s){p.valor_info.n_valores > 1 ? ` · ${p.valor_info.n_valores} valores diferentes` : ''}</span>
                              <button className={styles.link} onClick={() => alternar(trechos, tk, setTrechos)}>{trechos.has(tk) ? 'ocultar trecho' : 'ver trecho'}</button></>
                          : <span className={styles.dica}>valor não localizado nas peças</span>}
                      </div>
                      {trechos.has(tk) && p.valor_info?.trecho && <blockquote className={styles.trecho}>{p.valor_info.trecho.replace(/⟦|⟧/g, '')}</blockquote>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      {r && visao === 'bancas' && (
        <>
          <p className={styles.explica}>Grupos de advogados que dividem clientes: ligados quando têm ao menos {minPartes} parte(s) em comum e a metade ou mais da carteira do menor deles é compartilhada.</p>
          {r.bancas.length === 0 && <p className={styles.vazio}>Nenhuma banca com esse critério — reduza o mínimo de partes em comum.</p>}
          {r.bancas.map((b, i) => {
            const k = `b${i}`
            return (
              <div key={k} className={styles.card}>
                <button className={styles.cardHead} aria-expanded={abertos.has(k)} onClick={() => alternar(abertos, k, setAbertos)}>
                  <span className={styles.chevron}>{abertos.has(k) ? '▾' : '▸'}</span>
                  <span className={styles.titulo}>{b.advogados.map(quem).join(' · ')}</span>
                  <span className={styles.valorG}>{b.valor_indicativo ?? '—'}</span>
                  <span className={styles.conta}>{b.advogados.length} advogados · {b.n_partes} partes</span>
                </button>
                {abertos.has(k) && (
                  <div className={styles.corpo}>
                    <div className={styles.chips}>{b.advogados.map((a) => <span key={a.id} className={styles.chip}>{quem(a)} · {a.n_partes} partes</span>)}</div>
                    <div className={styles.partes}>{b.partes.join(' · ')}</div>
                  </div>
                )}
              </div>
            )
          })}
        </>
      )}

      {r && visao === 'pares' && (
        <>
          <p className={styles.explica}>Pares de advogados que representam as mesmas partes. “Cobertura” = parcela da carteira do menor dos dois que o outro também atende.</p>
          {r.pares.length === 0 && <p className={styles.vazio}>Nenhum par com esse critério.</p>}
          {r.pares.map((p, i) => {
            const k = `p${i}`
            return (
              <div key={k} className={styles.card}>
                <button className={styles.cardHead} aria-expanded={abertos.has(k)} onClick={() => alternar(abertos, k, setAbertos)}>
                  <span className={styles.chevron}>{abertos.has(k) ? '▾' : '▸'}</span>
                  <span className={styles.titulo}>{quem(p.a)} + {quem(p.b)}</span>
                  <span className={styles.conta}>{p.n_comuns} parte(s) em comum · cobertura {Math.round(p.cobertura * 100)}%</span>
                </button>
                {abertos.has(k) && <div className={styles.corpo}><div className={styles.partes}>{p.partes.join(' · ')}</div></div>}
              </div>
            )
          })}
        </>
      )}

      {r && visao === 'blocos' && (
        <>
          <p className={styles.explica}>Partes que têm exatamente o mesmo conjunto de advogados — tendem a agir como bloco na negociação.</p>
          {r.blocos.length === 0 && <p className={styles.vazio}>Nenhum bloco.</p>}
          {r.blocos.map((b, i) => {
            const k = `l${i}`
            return (
              <div key={k} className={styles.card}>
                <button className={styles.cardHead} aria-expanded={abertos.has(k)} onClick={() => alternar(abertos, k, setAbertos)}>
                  <span className={styles.chevron}>{abertos.has(k) ? '▾' : '▸'}</span>
                  <span className={styles.titulo}>{b.advogados.map(quem).join(' · ')}</span>
                  <span className={styles.conta}>{b.n_partes} partes</span>
                </button>
                {abertos.has(k) && <div className={styles.corpo}><div className={styles.partes}>{b.partes.join(' · ')}</div></div>}
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}
