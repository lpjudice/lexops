import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import type { Cenario, LinhaCenario } from '../../api/autosIa'
import { Id } from './EstrategiaAdvogados'
import styles from './Estrategia.module.css'

const brl = (centavos: number) => (centavos / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
/** "1.234.567,89" / "1234567,89" / "1234567.89" → centavos */
export const parseBrl = (t: string): number | null => {
  const s = t.replace(/[^\d.,]/g, '')
  if (!s) return null
  const norm = s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : /^\d{1,3}(\.\d{3})+$/.test(s) ? s.replace(/\./g, '') : s
  const n = Number(norm)
  return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) : null
}
const calcular = (linhas: LinhaCenario[]) => {
  const aj = (l: LinhaCenario) => Math.round(l.valor_centavos * l.percentual / 100)
  const ativo = linhas.filter((l) => l.lado === 'ativo').reduce((s, l) => s + aj(l), 0)
  const passivo = linhas.filter((l) => l.lado === 'passivo').reduce((s, l) => s + aj(l), 0)
  const bruto = (lado: string) => linhas.filter((l) => l.lado === lado).reduce((s, l) => s + l.valor_centavos, 0)
  return { ativo, passivo, saldo: ativo - passivo, cobertura: passivo ? ativo / passivo : null, brutoAtivo: bruto('ativo'), brutoPassivo: bruto('passivo') }
}

function Valor({ centavos, onChange }: { centavos: number; onChange: (c: number) => void }) {
  const [t, setT] = useState(() => (centavos / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
  useEffect(() => { setT((centavos / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })) }, [centavos])
  return <input aria-label="Valor (R$)" className={styles.inputValor} inputMode="decimal" value={t} onChange={(e) => setT(e.target.value)}
    onBlur={() => { const c = parseBrl(t); if (c != null) onChange(c); else setT((centavos / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2 })) }} />
}

function Editor({ casoId, cenario, onSalvo }: { casoId: string; cenario: Cenario; onSalvo: () => void }) {
  const [nome, setNome] = useState(cenario.nome)
  const [notas, setNotas] = useState(cenario.notas ?? '')
  const [linhas, setLinhas] = useState<LinhaCenario[]>(cenario.linhas)
  const [busca, setBusca] = useState('')
  const [mostrarBusca, setMostrarBusca] = useState(false)
  const sujo = nome !== cenario.nome || (notas || null) !== (cenario.notas ?? null) || JSON.stringify(linhas.map(({ fonte, ...l }) => l)) !== JSON.stringify(cenario.linhas.map(({ fonte, ...l }) => l))
  const sug = useQuery({ queryKey: ['autos-ia', 'cen-sug', casoId, busca], queryFn: () => autosIa.sugestoesCenario(casoId, busca || undefined), enabled: mostrarBusca, staleTime: 60_000 })
  const salvar = useMutation({
    mutationFn: () => autosIa.salvarCenario(casoId, cenario.id, { nome, notas: notas.trim() || null, linhas: linhas.map(({ fonte, ...l }) => l) }),
    onSuccess: onSalvo,
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível salvar.'),
  })
  const r = useMemo(() => calcular(linhas), [linhas])
  const set = (i: number, p: Partial<LinhaCenario>) => setLinhas((ls) => ls.map((l, k) => (k === i ? { ...l, ...p } : l)))
  const nova = (lado: 'ativo' | 'passivo') => setLinhas((ls) => [...ls, { id: crypto.randomUUID(), lado, rotulo: lado === 'ativo' ? 'Novo ativo' : 'Novo passivo', valor_centavos: 0, percentual: 100 }])

  const bloco = (lado: 'ativo' | 'passivo') => (
    <div className={styles.cenBloco}>
      <h4>{lado === 'ativo' ? 'Ativos (% = quanto se espera realizar)' : 'Passivos (% = quanto do crédito se reconhece)'}</h4>
      {linhas.map((l, i) => l.lado !== lado ? null : (
        <div key={l.id ?? i} className={styles.cenLinha}>
          <input aria-label="Rótulo" className={styles.inputRotulo} value={l.rotulo} onChange={(e) => set(i, { rotulo: e.target.value })} />
          <Valor centavos={l.valor_centavos} onChange={(c) => set(i, { valor_centavos: c })} />
          <label className={styles.pct}><input aria-label="Percentual" type="number" min={0} max={100} step={1} value={l.percentual} onChange={(e) => set(i, { percentual: Math.max(0, Math.min(100, Number(e.target.value))) })} />%</label>
          <span className={styles.ajustado} title="Valor × percentual">{brl(Math.round(l.valor_centavos * l.percentual / 100))}</span>
          {l.fonte && <Id p={{ peca_id: l.fonte.peca_id, id_processual: l.fonte.id_processual, data: l.fonte.data, titulo: l.fonte.titulo ?? '', link_pdf: l.fonte.link_pdf, link_md: l.fonte.link_md }} />}
          <button className={styles.ico} aria-label="Remover linha" title="Remover" onClick={() => setLinhas((ls) => ls.filter((_, k) => k !== i))}>✕</button>
        </div>
      ))}
      <button className={styles.link} onClick={() => nova(lado)}>+ linha de {lado} (manual)</button>
    </div>
  )

  return (
    <div className={styles.cenEditor}>
      <div className={styles.barra}>
        <input aria-label="Nome do cenário" className={styles.inputRotulo} value={nome} onChange={(e) => setNome(e.target.value)} />
        <button className={styles.btn} disabled={!sujo || salvar.isPending} onClick={() => salvar.mutate()}>{salvar.isPending ? 'Salvando…' : sujo ? 'Salvar alterações' : 'Salvo'}</button>
      </div>
      <div className={styles.cenGrade}>{bloco('ativo')}{bloco('passivo')}</div>
      <div className={styles.cenResultado} aria-label="Resultado">
        <div><span className={styles.dica}>Ativo realizável</span><strong>{brl(r.ativo)}</strong><span className={styles.dica}>de {brl(r.brutoAtivo)}</span></div>
        <div><span className={styles.dica}>Passivo reconhecido</span><strong>{brl(r.passivo)}</strong><span className={styles.dica}>de {brl(r.brutoPassivo)}</span></div>
        <div><span className={styles.dica}>Saldo</span><strong className={r.saldo < 0 ? styles.neg : styles.pos}>{r.saldo < 0 ? '− ' : ''}{brl(Math.abs(r.saldo))}</strong></div>
        <div><span className={styles.dica}>Cobertura / recuperação por R$ 1</span><strong>{r.cobertura == null ? '—' : `${(r.cobertura * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}% · R$ ${Math.min(1, r.cobertura).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</strong></div>
      </div>
      <label className={styles.notaCampo}><span className={styles.dica}>Premissas / notas do cenário</span>
        <textarea aria-label="Notas" rows={3} value={notas} onChange={(e) => setNotas(e.target.value)} placeholder="Ex.: ativo imobiliário a 60% (venda forçada); créditos tributários não reconhecidos." /></label>
      <div>
        <button className={styles.link} onClick={() => setMostrarBusca((v) => !v)}>{mostrarBusca ? 'fechar valores dos autos' : '+ adicionar a partir dos valores dos autos'}</button>
        {mostrarBusca && (
          <div className={styles.sugestoes}>
            <input aria-label="Buscar valor" placeholder="Buscar entidade ou medida…" value={busca} onChange={(e) => setBusca(e.target.value)} />
            {sug.data?.length === 0 && <p className={styles.dica}>Nenhum valor de ativo/passivo encontrado.</p>}
            {sug.data?.map((s) => (
              <div key={s.fato_id} className={styles.sugLinha}>
                <span className={`${styles.pBadge} ${s.lado === 'ativo' ? styles.pFav : styles.pCon}`}>{s.lado}</span>
                <span className={styles.nome}>{s.rotulo}</span><span className={styles.valor}>{s.valor}</span>
                <span className={styles.dica}>{s.afirmante}</span><Id p={s.peticao} />
                <button className={styles.mini} onClick={() => setLinhas((ls) => [...ls, { id: crypto.randomUUID(), lado: s.lado, rotulo: s.rotulo, valor_centavos: s.valor_centavos, percentual: 100, fato_id: s.fato_id }])}>adicionar</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function EstrategiaCenarios({ casoId }: { casoId: string }) {
  const qc = useQueryClient()
  const lista = useQuery({ queryKey: ['autos-ia', 'cenarios', casoId], queryFn: () => autosIa.listarCenarios(casoId) })
  const [sel, setSel] = useState<string | null>(null)
  const cenarios = lista.data ?? []
  const atual = cenarios.find((c) => c.id === sel) ?? cenarios[0]
  const recarregar = () => qc.invalidateQueries({ queryKey: ['autos-ia', 'cenarios', casoId] })
  const criar = useMutation({
    mutationFn: () => autosIa.criarCenario(casoId, { nome: `Cenário ${cenarios.length + 1}` }),
    onSuccess: (c) => { setSel(c.id); recarregar() },
  })
  const duplicar = useMutation({ mutationFn: (id: string) => autosIa.duplicarCenario(casoId, id), onSuccess: (c) => { setSel(c.id); recarregar() } })
  const excluir = useMutation({ mutationFn: (id: string) => autosIa.excluirCenario(casoId, id), onSuccess: () => { setSel(null); recarregar() } })

  return (
    <div className={styles.wrap}>
      <p className={styles.explica}>
        Planilha para simular a recuperação: ativos com o % que se espera <strong>realizar</strong> e passivos com o % que se <strong>reconhece</strong>. As linhas podem vir dos valores extraídos dos autos (com a peça de origem) ou ser digitadas — as premissas são suas.
        Duplique um cenário para comparar hipóteses.
      </p>
      <div className={styles.barra}>
        <div className={styles.seg} role="tablist" aria-label="Cenários">
          {cenarios.map((c) => <button key={c.id} role="tab" aria-selected={atual?.id === c.id} className={atual?.id === c.id ? styles.segOn : ''} onClick={() => setSel(c.id)}>{c.nome}</button>)}
        </div>
        <button className={styles.btn} disabled={criar.isPending} onClick={() => criar.mutate()}>+ Novo cenário</button>
        {atual && <button className={styles.miniLink} onClick={() => duplicar.mutate(atual.id)}>duplicar</button>}
        {atual && <button className={styles.miniLink} onClick={() => { if (window.confirm(`Excluir o cenário "${atual.nome}"?`)) excluir.mutate(atual.id) }}>excluir</button>}
      </div>
      {cenarios.length === 0 && !lista.isLoading && <p className={styles.vazio}>Nenhum cenário ainda. Crie o primeiro para começar.</p>}
      {atual && <Editor key={`${atual.id}-${atual.atualizado_em}`} casoId={casoId} cenario={atual} onSalvo={recarregar} />}
    </div>
  )
}
