import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { estrutura } from '../../../api/estrutura'
import type { EmpresaGrupo, Participacao } from '../../../api/estrutura'
import { brl, brlCurto, COR_NIVEL, corNivel, pctTxt } from './util'
import styles from './Estrutura.module.css'

const LARG = 262, ALT = 44, COL = 300, MARGEM = 24

interface No { e: EmpresaGrupo; filhos: string[]; paiPrimario: Participacao | null; outrosPais: Participacao[] }

export default function Organograma({ casoId, onVerDividas }: { casoId: string; onVerDividas: (cnpj: string) => void }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['estrutura', 'organograma', casoId], queryFn: () => estrutura.organograma(casoId) })
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set())
  const [inicial, setInicial] = useState(false)
  const [sel, setSel] = useState<string | null>(null)
  const [busca, setBusca] = useState('')
  const [cor, setCor] = useState<'nivel' | 'divida'>('nivel')
  const [vista, setVista] = useState<'diagrama' | 'fluxos'>('diagrama')
  const d = q.data

  const grafo = useMemo(() => {
    if (!d) return null
    const nos = new Map<string, No>()
    d.empresas.forEach((e) => nos.set(e.cnpj, { e, filhos: [], paiPrimario: null, outrosPais: [] }))
    const porFilho = new Map<string, Participacao[]>()
    d.participacoes.forEach((p) => porFilho.set(p.filho, [...(porFilho.get(p.filho) ?? []), p]))
    porFilho.forEach((ps, filho) => {
      const ord = [...ps].sort((a, b) => Number(a.tracejado) - Number(b.tracejado) || (b.pct ?? -1) - (a.pct ?? -1))
      const n = nos.get(filho)!
      n.paiPrimario = ord[0]; n.outrosPais = ord.slice(1)
      nos.get(ord[0].pai)?.filhos.push(filho)
    })
    nos.forEach((n) => n.filhos.sort((a, b) => nos.get(b)!.filhos.length - nos.get(a)!.filhos.length || nos.get(b)!.e.deve_centavos - nos.get(a)!.e.deve_centavos || nos.get(a)!.e.nome.localeCompare(nos.get(b)!.e.nome)))
    const raizes = [...nos.values()].filter((n) => !n.paiPrimario).map((n) => n.e.cnpj)
    return { nos, raizes }
  }, [d])

  useEffect(() => {
    if (!grafo || inicial) return
    // abre as raízes e os dois primeiros níveis (cadeia das holdings até a Apex Partners)
    const s = new Set<string>()
    const abre = (c: string, prof: number) => { if (prof >= 4) return; s.add(c); grafo.nos.get(c)!.filhos.forEach((f) => abre(f, prof + 1)) }
    grafo.raizes.forEach((r) => { if (grafo.nos.get(r)!.filhos.length) abre(r, 0) })
    setExpandidos(s); setInicial(true)
  }, [grafo, inicial])

  const termo = busca.trim().toLowerCase()
  const acertos = useMemo(() => {
    if (!grafo || termo.length < 2) return new Set<string>()
    return new Set([...grafo.nos.values()].filter((n) => n.e.nome.toLowerCase().includes(termo) || n.e.cnpj.includes(termo.replace(/\D/g, '') || '§')).map((n) => n.e.cnpj))
  }, [grafo, termo])

  const ancestrais = (c: string) => { const out: string[] = []; let n = grafo?.nos.get(c); while (n?.paiPrimario) { out.push(n.paiPrimario.pai); n = grafo!.nos.get(n.paiPrimario.pai) } return out }
  useEffect(() => { if (acertos.size) setExpandidos((s) => { const n = new Set(s); acertos.forEach((c) => ancestrais(c).forEach((a) => n.add(a))); return n }) }, [acertos]) // eslint-disable-line react-hooks/exhaustive-deps
  const mostra = (c: string) => { setExpandidos((s) => { const n = new Set(s); ancestrais(c).forEach((a) => n.add(a)); return n }); setSel(c); setVista('diagrama') }

  const layout = useMemo(() => {
    if (!grafo) return { itens: [] as { c: string; x: number; y: number; prof: number }[], pos: new Map<string, { x: number; y: number }>(), larg: 0, alt: 0 }
    const itens: { c: string; x: number; y: number; prof: number }[] = []
    const pos = new Map<string, { x: number; y: number }>()
    let linha = 0
    const visita = (c: string, prof: number) => {
      const p = { x: MARGEM + prof * COL, y: MARGEM + linha * (ALT + 8) }
      linha++; itens.push({ c, ...p, prof }); pos.set(c, p)
      if (expandidos.has(c)) grafo.nos.get(c)!.filhos.forEach((f) => visita(f, prof + 1))
    }
    grafo.raizes.forEach((r) => visita(r, 0))
    const maxX = Math.max(0, ...itens.map((i) => i.x))
    return { itens, pos, larg: maxX + LARG + 80, alt: MARGEM * 2 + linha * (ALT + 8) }
  }, [grafo, expandidos])

  const maxDeve = Math.max(1, ...(d?.empresas.map((e) => e.deve_centavos) ?? [1]))
  const alternar = (c: string) => setExpandidos((s) => { const n = new Set(s); n.has(c) ? n.delete(c) : n.add(c); return n })
  const expandirTudo = () => grafo && setExpandidos(new Set([...grafo.nos.values()].filter((n) => n.filhos.length).map((n) => n.e.cnpj)))
  const recolher = () => grafo && setExpandidos(new Set(grafo.raizes))

  const fluxosSel = useMemo(() => (d && sel ? d.dividas_intragrupo.filter((f) => f.devedora === sel || f.credora === sel) : []), [d, sel])
  const atualizar = useMutation({
    mutationFn: async (v: { tipo: 'nivel'; cnpj: string; nivel: string | null } | { tipo: 'pct'; id: string; pct: number | null } | { tipo: 'status'; id: string; status: string }
      | { tipo: 'novo'; pai: string; filho: string; pct: number | null }): Promise<unknown> => {
      if (v.tipo === 'nivel') return estrutura.atualizarEmpresa(casoId, v.cnpj, { nivel: v.nivel })
      if (v.tipo === 'pct') return estrutura.atualizarParticipacao(casoId, v.id, { pct: v.pct })
      if (v.tipo === 'status') return estrutura.atualizarParticipacao(casoId, v.id, { status: v.status })
      return estrutura.criarParticipacao(casoId, { pai: v.pai, filho: v.filho, pct: v.pct })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['estrutura', 'organograma', casoId] }),
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível salvar.'),
  })

  if (!d || !grafo) return <p className={styles.vazio}>{q.isLoading ? 'Carregando…' : 'Sem dados.'}</p>
  if (d.empresas.length === 0) return <p className={styles.vazio}>O organograma ainda não foi lido. Use a aba "Importar" → "Ler organograma do processo".</p>
  const selNo = sel ? grafo.nos.get(sel) : null
  const nome = (c: string) => grafo.nos.get(c)?.e.nome ?? c

  return (
    <div className={styles.wrap}>
      <div className={styles.barra}>
        <div className={styles.seg} role="tablist" aria-label="Vista do organograma">
          <button role="tab" aria-selected={vista === 'diagrama'} className={vista === 'diagrama' ? styles.segOn : ''} onClick={() => setVista('diagrama')}>Diagrama</button>
          <button role="tab" aria-selected={vista === 'fluxos'} className={vista === 'fluxos' ? styles.segOn : ''} onClick={() => setVista('fluxos')}>Dívidas entre empresas do grupo</button>
        </div>
        <span className={styles.dica}>{d.resumo.empresas} empresas · {d.resumo.vinculos} vínculos societários · {d.resumo.com_divida} com dívida · intragrupo {brlCurto(d.resumo.intragrupo_total_centavos)}
          {d.resumo.devedoras_fora_do_organograma > 0 && ` · ${d.resumo.devedoras_fora_do_organograma} devedora(s) da planilha fora do organograma`}</span>
      </div>

      {vista === 'diagrama' && (
        <>
          <div className={styles.barra}>
            <input aria-label="Buscar empresa" type="search" placeholder="Buscar empresa ou CNPJ…" value={busca} onChange={(e) => setBusca(e.target.value)} style={{ padding: '6px 10px', border: '1px solid var(--gray-border)', borderRadius: 8, font: 'inherit', fontSize: 13, minWidth: 240 }} />
            {termo.length >= 2 && <span className={styles.dica}>{acertos.size} encontrada(s)</span>}
            <button className={styles.btnSec} onClick={expandirTudo}>Expandir tudo</button>
            <button className={styles.btnSec} onClick={recolher}>Recolher</button>
            <label className={styles.dica}>Cor: <select value={cor} onChange={(e) => setCor(e.target.value as any)} aria-label="Colorir por">
              <option value="nivel">nível na estrutura</option><option value="divida">tamanho da dívida</option></select></label>
            <span className={styles.legenda}>{d.niveis.map((n) => <span key={n} className={styles.legItem}><span className={styles.legCor} style={{ background: COR_NIVEL[n]?.bg, borderColor: COR_NIVEL[n]?.borda }} />{n}</span>)}</span>
          </div>
          <div className={styles.orgLayout}>
            <div className={styles.orgCanvas} data-testid="canvas">
              <svg width={layout.larg} height={layout.alt} role="img" aria-label="Organograma societário do grupo">
                <defs><marker id="seta" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#dc2626" /></marker>
                  <marker id="setaV" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#16a34a" /></marker></defs>
                {layout.itens.map(({ c }) => {
                  const n = grafo.nos.get(c)!
                  if (!expandidos.has(c)) return null
                  const p = layout.pos.get(c)!
                  return n.filhos.map((f) => {
                    const pf = layout.pos.get(f)!; const part = grafo.nos.get(f)!.paiPrimario!
                    const x1 = p.x + LARG, y1 = p.y + ALT / 2, x2 = pf.x, y2 = pf.y + ALT / 2, mx = x1 + (x2 - x1) / 2
                    return <g key={`${c}>${f}`}><path d={`M${x1},${y1} H${mx} V${y2} H${x2}`} fill="none" stroke={part.tracejado ? '#c084fc' : '#94a3b8'} strokeWidth={1.2} strokeDasharray={part.tracejado ? '4 3' : undefined} />
                      <text x={x2 - 6} y={y2 - 3} fontSize={10} textAnchor="end" fill="#475569">{pctTxt(part.pct)}</text></g>
                  })
                })}
                {sel && fluxosSel.map((f, i) => {
                  const a = layout.pos.get(f.devedora), b = layout.pos.get(f.credora)
                  if (!a || !b) return null
                  const x1 = a.x, y1 = a.y + ALT / 2, x2 = b.x, y2 = b.y + ALT / 2, bx = Math.min(x1, x2) - 40 - (i % 4) * 8
                  const sai = f.devedora === sel
                  return <g key={`${f.devedora}-${f.credora}`}><path d={`M${x1},${y1} C${bx},${y1} ${bx},${y2} ${x2},${y2}`} fill="none" stroke={sai ? '#dc2626' : '#16a34a'} strokeWidth={1.8} strokeDasharray="5 3" markerEnd={sai ? 'url(#seta)' : 'url(#setaV)'} />
                    <text x={bx - 2} y={(y1 + y2) / 2} fontSize={10} textAnchor="end" fill={sai ? '#b91c1c' : '#15803d'} fontWeight={700}>{brlCurto(f.valor_centavos)}</text></g>
                })}
                {layout.itens.map(({ c, x, y }) => {
                  const n = grafo.nos.get(c)!; const e = n.e; const k = corNivel(e.nivel)
                  const heat = cor === 'divida' ? Math.min(1, e.deve_centavos / maxDeve) : 0
                  const fundo = cor === 'divida' ? (e.deve_centavos ? `rgba(220,38,38,${0.12 + 0.75 * Math.sqrt(heat)})` : '#f8fafc') : k.bg
                  const texto = cor === 'divida' ? '#1e293b' : k.fg
                  const marcada = acertos.has(c)
                  return (
                    <g key={c} transform={`translate(${x},${y})`} style={{ cursor: 'pointer' }} onClick={() => setSel(c)} role="button" aria-label={`Empresa ${e.nome}`} aria-pressed={sel === c}>
                      <rect width={LARG} height={ALT} rx={8} fill={fundo} stroke={sel === c ? '#00a88c' : marcada ? '#f59e0b' : k.borda} strokeWidth={sel === c || marcada ? 2.5 : 1.2} />
                      <text x={8} y={16} fontSize={11} fontWeight={700} fill={texto}>{e.nome.length > 38 ? `${e.nome.slice(0, 37)}…` : e.nome}<title>{e.nome}</title></text>
                      <text x={8} y={31} fontSize={9.5} fill={texto} opacity={0.85}>{e.cnpj_fmt}</text>
                      {e.deve_centavos > 0 && <text x={LARG - (n.filhos.length > 0 ? 22 : 8)} y={31} fontSize={9.5} textAnchor="end" fontWeight={700} fill={cor === 'divida' || e.nivel === 'Holding' ? (cor === 'divida' ? '#991b1b' : '#fca5a5') : '#b91c1c'}>deve {brlCurto(e.deve_centavos)}</text>}
                      {n.filhos.length > 0 && (
                        <g transform={`translate(${LARG - 2},${ALT / 2})`} onClick={(ev) => { ev.stopPropagation(); alternar(c) }} aria-label={expandidos.has(c) ? 'Recolher filhos' : `Expandir ${n.filhos.length} filhos`} role="button">
                          <circle r={10} fill="#fff" stroke="#64748b" /><text textAnchor="middle" y={4} fontSize={10} fill="#334155" fontWeight={700}>{expandidos.has(c) ? '−' : n.filhos.length}</text>
                        </g>
                      )}
                    </g>
                  )
                })}
              </svg>
            </div>

            <aside className={styles.orgPainel} aria-label="Detalhes da empresa">
              {!selNo ? <span className={styles.dica}>Clique numa empresa para ver o nível, as participações, as dívidas e as relações de dívida com outras empresas do grupo. As setas vermelhas/verdes mostram, no diagrama, para quem ela deve / de quem tem a receber.</span> : (
                <>
                  <h3>{selNo.e.nome}</h3>
                  <span className={styles.dica}>{selNo.e.cnpj_fmt}{selNo.e.origem === 'manual' ? ' · editado' : ''}</span>
                  <label className={styles.campo}>Nível
                    <select value={selNo.e.nivel ?? ''} aria-label="Nível da empresa" onChange={(ev) => atualizar.mutate({ tipo: 'nivel', cnpj: selNo.e.cnpj, nivel: ev.target.value || null })}>
                      <option value="">(sem nível)</option>{d.niveis.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
                  {selNo.e.descricao && <details><summary className={styles.link}>atividade / objeto social</summary><p className={styles.explica}>{selNo.e.descricao}</p></details>}

                  <h4>Quem detém esta empresa</h4>
                  {!selNo.paiPrimario && <span className={styles.dica}>Topo da estrutura (nenhuma controladora no desenho).</span>}
                  {[selNo.paiPrimario, ...selNo.outrosPais].filter(Boolean).map((p) => (
                    <div key={p!.id} className={styles.rel}>
                      <button onClick={() => mostra(p!.pai)}>{nome(p!.pai)}</button>
                      <span>{pctTxt(p!.pct)}{p!.tracejado ? ' (tracejado)' : ''} <button className={styles.miniLink} onClick={() => {
                        const v = window.prompt('Percentual de participação (0 a 100):', p!.pct == null ? '' : String(p!.pct).replace('.', ','))
                        if (v === null) return
                        const n = v.trim() === '' ? null : Number(v.replace(',', '.'))
                        if (n !== null && !(n >= 0 && n <= 100)) { alert('Informe um número entre 0 e 100.'); return }
                        atualizar.mutate({ tipo: 'pct', id: p!.id, pct: n })
                      }}>editar</button> <button className={styles.miniLink} onClick={() => window.confirm('Remover este vínculo do organograma?') && atualizar.mutate({ tipo: 'status', id: p!.id, status: 'rejeitado' })}>remover</button></span>
                    </div>
                  ))}
                  <label className={styles.campo}>Adicionar controladora
                    <select aria-label="Adicionar controladora" value="" onChange={(ev) => {
                      if (!ev.target.value) return
                      const v = window.prompt('Percentual de participação (0 a 100; vazio = não informado):', '')
                      if (v === null) return
                      const n = v.trim() === '' ? null : Number(v.replace(',', '.'))
                      if (n !== null && !(n >= 0 && n <= 100)) { alert('Informe um número entre 0 e 100.'); return }
                      atualizar.mutate({ tipo: 'novo', pai: ev.target.value, filho: selNo.e.cnpj, pct: n })
                    }}><option value="">escolher empresa…</option>{d.empresas.filter((x) => x.cnpj !== selNo.e.cnpj).map((x) => <option key={x.cnpj} value={x.cnpj}>{x.nome}</option>)}</select></label>

                  <h4>Empresas que ela detém ({selNo.filhos.length})</h4>
                  {selNo.filhos.slice(0, 12).map((f) => <div key={f} className={styles.rel}><button onClick={() => mostra(f)}>{nome(f)}</button><span>{pctTxt(grafo.nos.get(f)!.paiPrimario!.pct)}</span></div>)}
                  {selNo.filhos.length > 12 && <span className={styles.dica}>+ {selNo.filhos.length - 12} — expanda no diagrama.</span>}

                  <h4>Dívidas</h4>
                  <div className={styles.rel}><span>Deve (lote ativo)</span><span className={styles.valorDeve}>{brl(selNo.e.deve_centavos)}</span></div>
                  <div className={styles.rel}><span>Tem a receber de empresas do grupo</span><span className={styles.valorRecebe}>{brl(selNo.e.a_receber_centavos)}</span></div>
                  <div className={styles.rel}><span>Do que deve, intragrupo</span><span>{brl(selNo.e.intragrupo_deve_centavos)}</span></div>
                  {selNo.e.n_creditos > 0 && <button className={styles.btnSec} onClick={() => onVerDividas(selNo.e.cnpj)}>Ver as {selNo.e.n_creditos} dívida(s) desta empresa</button>}

                  {fluxosSel.length > 0 && <h4>Relações de dívida com o grupo</h4>}
                  {fluxosSel.map((f) => {
                    const sai = f.devedora === sel
                    return <div key={`${f.devedora}-${f.credora}`} className={styles.rel}><button onClick={() => mostra(sai ? f.credora : f.devedora)}>{sai ? `deve a ${nome(f.credora)}` : `${nome(f.devedora)} deve a ela`}</button>
                      <span className={sai ? styles.valorDeve : styles.valorRecebe} title={f.categorias.map((c) => `${c.categoria}: ${c.valor}`).join('\n')}>{brlCurto(f.valor_centavos)}</span></div>
                  })}
                </>
              )}
            </aside>
          </div>
        </>
      )}

      {vista === 'fluxos' && (
        <div className={styles.tabelaWrap}>
          <table className={styles.tabela}>
            <thead><tr><th>Empresa devedora</th><th>Empresa credora</th><th>Categorias</th><th className={styles.num}>Linhas</th><th className={styles.num}>Valor</th></tr></thead>
            <tbody>
              {d.dividas_intragrupo.map((f) => (
                <tr key={`${f.devedora}-${f.credora}`}>
                  <td><button className={styles.link} onClick={() => mostra(f.devedora)}>{nome(f.devedora)}</button></td>
                  <td><button className={styles.link} onClick={() => mostra(f.credora)}>{nome(f.credora)}</button></td>
                  <td>{f.categorias.map((c) => `${c.categoria} (${brlCurto(c.valor_centavos)})`).join(' · ')}</td>
                  <td className={styles.num}>{f.n}</td><td className={styles.num}>{f.valor}</td>
                </tr>
              ))}
              {d.dividas_intragrupo.length === 0 && <tr><td colSpan={5} className={styles.vazio}>Nenhuma dívida entre empresas do grupo no lote ativo.</td></tr>}
            </tbody>
            <tfoot><tr><td colSpan={4}>Total entre empresas do grupo</td><td className={styles.num}>{brl(d.resumo.intragrupo_total_centavos)}</td></tr></tfoot>
          </table>
        </div>
      )}
    </div>
  )
}
