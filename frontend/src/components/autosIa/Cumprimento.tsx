import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import type { Determinacao, FiltrosDeterminacoes, PeticaoRef } from '../../api/autosIa'
import styles from './Cumprimento.module.css'

const dataBr = (d: string | null) => (d ? d.split('-').reverse().join('/') : '')
const TOM: Record<string, string> = {
  vencida_sem_cumprimento: 'bad', nao_localizada: 'warn', parcial: 'warn', em_prazo: 'info',
  cumprida: 'ok', prejudicada: 'mute', nao_aplicavel: 'mute', nao_avaliada: 'mute',
}
const ORDEM_STATUS = ['vencida_sem_cumprimento', 'nao_localizada', 'parcial', 'em_prazo', 'cumprida', 'prejudicada', 'nao_aplicavel', 'nao_avaliada']

function Id({ p }: { p: PeticaoRef }) {
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

function prazoTexto(d: Determinacao) {
  if (d.vencimento) {
    const dias = d.dias_para_vencer
    const encerrada = ['cumprida', 'prejudicada', 'nao_aplicavel'].includes(d.status)
    const rel = encerrada || dias == null ? '' : dias < 0 ? ` (venceu há ${-dias} d)` : dias === 0 ? ' (vence hoje)' : ` (em ${dias} d)`
    return `${dataBr(d.vencimento)}${d.vencimento_estimado ? ' est.' : ''}${rel}`
  }
  return d.prazo_condicao ? 'prazo condicionado' : 'sem prazo'
}

function Ordem({
  d, opcoes, ocupado, onAtualizar,
}: {
  d: Determinacao; opcoes: { chave: string; rotulo: string }[]; ocupado: boolean
  onAtualizar: (id: string, body: { status_manual?: string | null; nota?: string | null; rejeitar?: boolean; validar?: boolean }) => void
}) {
  const [aberto, setAberto] = useState(false)
  const [editando, setEditando] = useState(false)
  const [nota, setNota] = useState(d.nota ?? '')
  const tom = TOM[d.status] ?? 'mute'
  const rotuloStatus = opcoes.find((o) => o.chave === d.status)?.rotulo ?? d.status

  return (
    <div className={`${styles.ordem} ${d.validado ? styles.ordemOk : ''}`}>
      <div className={styles.topo}>
        <span className={styles.num} title={d.capitulo ?? undefined}>{d.ordem ? `item ${d.ordem}` : '—'}</span>
        <span className={styles.dest}>{d.destinatario ?? d.destinatario_rotulo}</span>
        <span className={`${styles.badge} ${styles[tom]}`} title={d.status_manual ? 'Definido por você' : 'Avaliação da IA'}>
          {rotuloStatus}{d.status_manual ? ' ✎' : ''}
        </span>
        {d.ligada_a_mediacao && <span className={styles.badgeMed} title="Ordem ligada à mediação">mediação</span>}
        <span className={styles.prazo} title={d.vencimento_motivo ?? undefined}>{prazoTexto(d)}</span>
        <span className={styles.acoes}>
          <button className={`${styles.ico} ${d.validado ? styles.icoOn : ''}`} disabled={ocupado} aria-pressed={d.validado} aria-label="Validar"
            title={d.validado ? 'Conferido — clique para desfazer' : 'Marcar como conferido'}
            onClick={() => onAtualizar(d.id, { validar: !d.validado })}>✓</button>
          <button className={styles.ico} disabled={ocupado} aria-label="Editar" title="Corrigir a situação e anotar" onClick={() => setEditando((v) => !v)}>✎</button>
          <button className={styles.ico} disabled={ocupado} aria-label="Rejeitar" title="Rejeitar (não é uma ordem)" onClick={() => onAtualizar(d.id, { rejeitar: true })}>✕</button>
        </span>
      </div>
      <div className={styles.acao}>{d.acao}</div>
      {d.sancao && <div className={styles.sancao}>Sanção: {d.sancao}</div>}
      {d.nota && !editando && <div className={styles.nota}>📝 {d.nota}</div>}
      <div className={styles.links}>
        <button className={styles.link} onClick={() => setAberto((v) => !v)}>{aberto ? 'ocultar detalhes' : 'trecho e cumprimento'}</button>
        {d.evidencias.length > 0 && <span className={styles.ev}>cumprimento em: {d.evidencias.map((e) => <Id key={e.peca_id} p={e} />)}</span>}
      </div>
      {aberto && (
        <div className={styles.detalhe}>
          {d.trecho && <blockquote className={styles.trecho}>{d.trecho}</blockquote>}
          {d.justificativa && <p className={styles.just}><strong>Leitura da IA{d.confianca != null ? ` (confiança ${Math.round(d.confianca * 100)}%)` : ''}:</strong> {d.justificativa}</p>}
          {d.vencimento_motivo && <p className={styles.just}><strong>Prazo:</strong> {d.vencimento_motivo}</p>}
        </div>
      )}
      {editando && (
        <div className={styles.editor}>
          <label>Situação
            <select aria-label="Situação desta ordem" value={d.status_manual ?? 'automatico'} onChange={(e) => onAtualizar(d.id, { status_manual: e.target.value })}>
              <option value="automatico">Automática (IA)</option>
              {opcoes.filter((o) => o.chave !== 'vencida_sem_cumprimento' && o.chave !== 'nao_avaliada').map((o) => <option key={o.chave} value={o.chave}>{o.rotulo}</option>)}
            </select>
          </label>
          <label className={styles.notaCampo}>Nota
            <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Ex.: juntado por fora dos autos em 24/10" />
          </label>
          <button className={styles.mini} disabled={ocupado} onClick={() => { onAtualizar(d.id, { nota: nota.trim() || null }); setEditando(false) }}>salvar nota</button>
          <button className={styles.miniLink} onClick={() => setEditando(false)}>fechar</button>
        </div>
      )}
    </div>
  )
}

function Intimacao({ casoId, d, onSalvo }: { casoId: string; d: Determinacao; onSalvo: () => void }) {
  const [v, setV] = useState(d.intimacao_data ?? '')
  const salvar = useMutation({
    mutationFn: (data: string | null) => autosIa.intimacaoDaDecisao(casoId, d.decisao.peca_id, data),
    onSuccess: onSalvo,
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível salvar a data.'),
  })
  return (
    <span className={styles.intim}>
      <label>Intimação <input type="date" value={v} onChange={(e) => setV(e.target.value)} /></label>
      <button className={styles.mini} disabled={salvar.isPending || v === (d.intimacao_data ?? '')} onClick={() => salvar.mutate(v || null)}>recalcular prazos</button>
    </span>
  )
}

export default function Cumprimento({ casoId }: { casoId: string }) {
  const qc = useQueryClient()
  const [filtros, setFiltros] = useState<FiltrosDeterminacoes>({})
  const [minuta, setMinuta] = useState<string | null>(null)
  const [copiado, setCopiado] = useState(false)

  const { data: opcoes } = useQuery({ queryKey: ['autos-ia', 'det-opcoes'], queryFn: autosIa.opcoesDeterminacoes, staleTime: Infinity })
  const status = useQuery({
    queryKey: ['autos-ia', 'det', 'status', casoId],
    queryFn: () => autosIa.statusDeterminacoes(casoId),
    refetchInterval: (q) => (q.state.data?.estado === 'rodando' ? 3000 : false),
  })
  const lista = useQuery({
    queryKey: ['autos-ia', 'det', 'lista', casoId, filtros, status.data?.total_determinacoes ?? 0, status.data?.estado],
    queryFn: () => autosIa.listarDeterminacoes(casoId, filtros),
  })
  const recarregar = () => qc.invalidateQueries({ queryKey: ['autos-ia', 'det'] })
  const extrair = useMutation({
    mutationFn: (forcar: boolean) => autosIa.extrairDeterminacoes(casoId, forcar),
    onSuccess: (r) => { qc.setQueryData(['autos-ia', 'det', 'status', casoId], r) },
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível iniciar.'),
  })
  const atualizar = useMutation({
    mutationFn: (v: { id: string; body: { status_manual?: string | null; nota?: string | null; rejeitar?: boolean; validar?: boolean } }) =>
      autosIa.atualizarDeterminacao(casoId, v.id, v.body),
    onSuccess: recarregar,
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível salvar.'),
  })
  const gerarMinuta = useMutation({
    mutationFn: () => autosIa.minutaDeterminacoes(casoId, filtros.destinatario_tipo),
    onSuccess: (r) => { setMinuta(r.markdown); setCopiado(false) },
  })

  const st = status.data
  const rodando = st?.estado === 'rodando' || extrair.isPending
  const itens = lista.data?.itens ?? []
  const resumo = lista.data?.resumo ?? {}
  const rotuloStatus = (k: string) => opcoes?.status.find((o) => o.chave === k)?.rotulo ?? k

  const porDecisao = useMemo(() => {
    const m = new Map<string, Determinacao[]>()
    for (const d of itens) m.set(d.decisao.peca_id, [...(m.get(d.decisao.peca_id) ?? []), d])
    return Array.from(m.values())
  }, [itens])

  const iniciar = (forcar: boolean) => {
    const msg = forcar
      ? 'Reler TODAS as decisões do Juízo e reavaliar o cumprimento (as ordens que você validou ou rejeitou são mantidas)? Usa IA.'
      : `Ler ${st?.atos_pendentes ?? 0} ato(s) do Juízo ainda não lidos e (re)avaliar o cumprimento de todas as ordens contra as peças posteriores? Usa IA.`
    if (window.confirm(msg)) extrair.mutate(forcar)
  }

  const copiar = async () => {
    if (!minuta) return
    try { await navigator.clipboard.writeText(minuta); setCopiado(true) } catch { /* sem permissão: o texto segue selecionável */ }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.cobertura}>
        {st && st.total_determinacoes > 0
          ? <><strong>{st.total_determinacoes}</strong> ordem(ns) do Juízo mapeadas.</>
          : <>Nenhuma ordem mapeada ainda.</>}
        {' '}As decisões e despachos são lidos com IA; o cumprimento é conferido nas peças posteriores. Os prazos são <strong>estimativas</strong> em dias úteis (informe a data de intimação para corrigir).
        {st && st.atos_pendentes > 0 && !rodando && <span className={styles.aviso}> {st.atos_pendentes} ato(s) ainda não lidos.</span>}
      </div>
      <div className={styles.botoes}>
        <button className={styles.btn} disabled={rodando} onClick={() => iniciar(false)}>
          {rodando ? 'Lendo…' : (st?.atos_pendentes ?? 0) > 0 ? `Ler decisões e avaliar (${st?.atos_pendentes} atos)` : 'Reavaliar cumprimento'}
        </button>
        {!rodando && (st?.total_determinacoes ?? 0) > 0 && <button className={styles.miniLink} onClick={() => iniciar(true)}>reler tudo</button>}
        <button className={styles.btnSec} disabled={gerarMinuta.isPending || itens.length === 0} onClick={() => gerarMinuta.mutate()}
          title="Quadro das ordens vencidas ou sem cumprimento comprovado, para colar numa petição">Gerar minuta de descumprimento</button>
        {rodando && st && <span className={styles.dica}>{st.feitos}/{st.total} atos · {st.novas} ordens · US$ {st.custo_usd.toFixed(2)}</span>}
        {!rodando && st?.mensagem && <span className={st.estado === 'erro' ? styles.erro : styles.dica}>{st.mensagem}</span>}
      </div>

      {minuta !== null && (
        <div className={styles.minuta}>
          <div className={styles.minutaTopo}>
            <strong>Minuta (Markdown)</strong>
            <span className={styles.dica}>Estimativas de prazo e leitura da IA: confira cada item antes de usar.</span>
            <button className={styles.mini} onClick={copiar}>{copiado ? 'copiado ✓' : 'copiar'}</button>
            <button className={styles.miniLink} onClick={() => setMinuta(null)}>fechar</button>
          </div>
          <textarea readOnly value={minuta} rows={12} aria-label="Minuta" onFocus={(e) => e.currentTarget.select()} />
        </div>
      )}

      <div className={styles.chips} role="group" aria-label="Filtrar por situação">
        {ORDEM_STATUS.filter((k) => resumo[k]).map((k) => (
          <button key={k} className={`${styles.chip} ${styles[TOM[k]]} ${filtros.status === k ? styles.chipOn : ''}`} aria-pressed={filtros.status === k}
            onClick={() => setFiltros({ ...filtros, status: filtros.status === k ? undefined : k })}>
            {rotuloStatus(k)} <span className={styles.n}>{resumo[k]}</span>
          </button>
        ))}
      </div>

      <div className={styles.filtros}>
        <select aria-label="Destinatário" value={filtros.destinatario_tipo ?? ''} onChange={(e) => setFiltros({ ...filtros, destinatario_tipo: e.target.value || undefined })}>
          <option value="">Todos os destinatários</option>
          {opcoes?.destinatarios.map((o) => <option key={o.chave} value={o.chave}>{o.rotulo}</option>)}
        </select>
        <select aria-label="Tema" value={filtros.tema ?? ''} onChange={(e) => setFiltros({ ...filtros, tema: e.target.value || undefined })}>
          <option value="">Todos os temas</option>
          {opcoes?.temas.map((o) => <option key={o.chave} value={o.chave}>{o.rotulo}</option>)}
        </select>
        <label className={styles.check}>
          <input type="checkbox" checked={!!filtros.mediacao} onChange={(e) => setFiltros({ ...filtros, mediacao: e.target.checked || undefined })} /> só ligadas à mediação
        </label>
        <input aria-label="Buscar" placeholder="Buscar ação, destinatário, trecho…" value={filtros.q ?? ''} onChange={(e) => setFiltros({ ...filtros, q: e.target.value || undefined })} />
      </div>

      {lista.data && itens.length === 0 && <p className={styles.vazio}>{(st?.total_determinacoes ?? 0) === 0 ? 'Leia as decisões para ver o quadro de ordens.' : 'Nada com esses filtros.'}</p>}
      {porDecisao.map((ordens) => {
        const d0 = ordens[0]
        return (
          <section key={d0.decisao.peca_id} className={styles.decisao}>
            <header className={styles.decisaoTopo}>
              <Id p={d0.decisao} />
              <span className={styles.decisaoTit}>{d0.decisao.titulo}</span>
              <span className={styles.dica}>{dataBr(d0.decisao_data)} · {ordens.length} ordem(ns)</span>
              <Intimacao key={`${d0.decisao.peca_id}-${d0.intimacao_data ?? ''}`} casoId={casoId} d={d0} onSalvo={recarregar} />
            </header>
            {ordens.map((d) => (
              <Ordem key={d.id} d={d} opcoes={opcoes?.status ?? []} ocupado={atualizar.isPending}
                onAtualizar={(id, body) => atualizar.mutate({ id, body })} />
            ))}
          </section>
        )
      })}
    </div>
  )
}
