import { useQuery } from '@tanstack/react-query'
import { estrutura } from '../../../api/estrutura'
import type { FiltrosCreditos, Quebra } from '../../../api/estrutura'
import { brl, brlCurto } from './util'
import styles from './Estrutura.module.css'

function Barras({ titulo, itens, onClique, nota }: { titulo: string; itens: Quebra[]; onClique?: (q: Quebra) => void; nota?: string }) {
  const max = Math.max(1, ...itens.map((i) => i.valor_centavos))
  return (
    <div className={styles.bloco}>
      <h4>{titulo}</h4>
      {itens.length === 0 && <span className={styles.dica}>Sem dados.</span>}
      {itens.map((i) => (
        <button key={i.chave} className={styles.barItem} onClick={() => onClique?.(i)} disabled={!onClique} title={`${i.rotulo} — ${i.valor} · ${i.n} linha(s) · ${i.pct.toLocaleString('pt-BR')}% do total`}>
          <span className={styles.barRotulo}>{i.rotulo}</span>
          <span className={styles.barTrilho}><span className={styles.barPreenche} style={{ width: `${Math.max(1, (100 * i.valor_centavos) / max)}%` }} /></span>
          <span className={styles.barValor}>{brlCurto(i.valor_centavos)} <span className={styles.dica}>· {i.pct.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%</span></span>
        </button>
      ))}
      {nota && <span className={styles.dica}>{nota}</span>}
    </div>
  )
}

export default function VisaoGeral({ casoId, f, setF }: { casoId: string; f: FiltrosCreditos; setF: (f: FiltrosCreditos) => void }) {
  const q = useQuery({ queryKey: ['estrutura', 'resumo', casoId, f], queryFn: () => estrutura.resumo(casoId, f), placeholderData: (p) => p })
  const r = q.data
  if (!r) return <p className={styles.vazio}>{q.isLoading ? 'Carregando…' : 'Sem dados.'}</p>
  const add = (k: keyof FiltrosCreditos, v: string) => setF({ ...f, [k]: [...(((f as any)[k] as string[]) ?? []).filter((x) => x !== v), v] })
  return (
    <div className={styles.wrap}>
      <div className={styles.kpis}>
        <div className={styles.kpi}><span className={styles.dica}>Total da relação</span><strong>{r.total}</strong><span className={styles.dica}>{r.n.toLocaleString('pt-BR')} linha(s) · {r.devedoras} devedora(s) · {r.credores} credor(es)</span></div>
        <div className={styles.kpi}><button onClick={() => setF({ ...f, intragrupo: true })} title="Filtrar: só intragrupo"><span className={styles.dica}>Intragrupo (credor é do grupo)</span><br /><strong>{r.intragrupo.valor}</strong><br /><span className={styles.dica}>{r.intragrupo.n} linha(s) · {r.intragrupo.pct.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}% do total</span></button></div>
        <div className={styles.kpi}><button onClick={() => setF({ ...f, vencidos: true })} title="Filtrar: só vencidos"><span className={styles.dica}>Vencidos até hoje (data de vencimento da planilha)</span><br /><strong>{brl(r.vencidos.valor_centavos)}</strong><br /><span className={styles.dica}>{r.vencidos.n} linha(s)</span></button></div>
        <div className={styles.kpi}><button onClick={() => setF({ ...f, com_coobrigado: true })} title="Filtrar: com coobrigado"><span className={styles.dica}>Com coobrigado / fiador</span><br /><strong>{brl(r.com_coobrigado.valor_centavos)}</strong><br /><span className={styles.dica}>{r.com_coobrigado.n} linha(s)</span></button></div>
        <div className={styles.kpi}><button onClick={() => setF({ ...f, no_organograma: false })} title="Filtrar: devedora fora do organograma"><span className={styles.dica}>Devedora fora do organograma</span><br /><strong>{brl(r.fora_do_organograma.valor_centavos)}</strong><br /><span className={styles.dica}>{r.fora_do_organograma.n} linha(s)</span></button></div>
      </div>
      <p className={styles.explica}>Clique numa barra para filtrar por ela (os filtros valem também para as outras visões).</p>
      <div className={styles.blocos}>
        <Barras titulo="Por categoria de dívida" itens={r.por_categoria} onClique={(q) => add('categoria', q.chave)} />
        <Barras titulo="Por classe" itens={r.por_classe} onClique={(q) => add('classe', q.chave)} />
        <Barras titulo="Por origem do credor" itens={r.por_origem} onClique={(q) => setF({ ...f, intragrupo: q.chave === 'Intragrupo' })} />
        <Barras titulo="Por nível da devedora no organograma" itens={r.por_nivel_devedora} onClique={(q) => q.chave.startsWith('(') ? setF({ ...f, no_organograma: false }) : add('nivel_devedor', q.chave)} />
        <Barras titulo="Maiores devedoras" itens={r.por_devedora} onClique={(q) => q.chave && add('devedor', q.chave)} nota="Top 25." />
        <Barras titulo="Maiores credores" itens={r.por_credor} onClique={(q) => add('credor', q.chave)} nota="Top 25." />
      </div>
    </div>
  )
}
