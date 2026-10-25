import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import type { FatoValor, FiltrosValores, PeticaoRef } from '../../api/autosIa'
import styles from './Numeros.module.css'

type Visao = 'divergencias' | 'corroboracoes' | 'todos'

const NATUREZA: Record<string, string> = {
  afirmacao_propria: 'afirma', citacao_de_terceiro: 'cita terceiro', determinacao_ou_decisao: 'determina',
  estimativa_ou_calculo: 'estimativa', pedido: 'pede',
}
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
const dataRef = (d: string | null) => {
  if (!d) return null
  const [a, m, dia] = d.split('-')
  return m ? `${dia ? dia + '/' : ''}${MESES[Number(m) - 1] ?? m}/${a}` : a
}
const dataBr = (d: string | null) => (d ? d.split('-').reverse().join('/') : '')

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

/** Trecho com o valor exato destacado (o servidor marca com ⟦…⟧). */
function Trecho({ texto }: { texto: string }) {
  const m = texto.match(/^([\s\S]*?)⟦([\s\S]*?)⟧([\s\S]*)$/)
  if (!m) return <>{texto}</>
  return <>…{m[1]}<mark className={styles.marca}>{m[2]}</mark>{m[3]}…</>
}

function FatoLinha({
  f, temas, ocupado, onAtualizar, casoId, mostrarValor = true,
}: {
  f: FatoValor; temas: { chave: string; rotulo: string }[]; ocupado: boolean; casoId: string; mostrarValor?: boolean
  onAtualizar: (id: string, body: { tema?: string; sujeito_canonico?: string; status?: string; nota?: string | null }) => void
}) {
  const [trecho, setTrecho] = useState(false)
  const [editando, setEditando] = useState(false)
  const [onde, setOnde] = useState(false)
  const [tema, setTema] = useState(f.tema ?? 'outro')
  const [sujeito, setSujeito] = useState(f.sujeito_canonico ?? '')
  const [nota, setNota] = useState(f.nota ?? '')
  const outros = useQuery({
    queryKey: ['autos-ia', 'fatos-valores', 'onde', casoId, f.id],
    queryFn: () => autosIa.ondeMaisApareceValor(casoId, f.id),
    enabled: onde,
    staleTime: 5 * 60_000,
  })
  const validado = f.status === 'validado'

  return (
    <div className={`${styles.fato} ${validado ? styles.fatoOk : ''}`}>
      <div className={styles.fatoTopo}>
        {mostrarValor && <span className={styles.valor} title={f.rotulo_original ? `Escrito: ${f.rotulo_original}` : undefined}>{f.valor}</span>}
        <span className={styles.chipTema}>{f.tema_rotulo}</span>
        {f.natureza && <span className={styles.chipNat}>{NATUREZA[f.natureza] ?? f.natureza}</span>}
        <span className={styles.sujeito}>{f.sujeito_canonico ?? <em>sem sujeito</em>}</span>
        <span className={styles.afirmante} title="Quem afirma">{f.afirmante}</span>
        {f.data_ref && <span className={styles.dataRef} title="Data a que o valor se refere">ref. {dataRef(f.data_ref)}</span>}
        <Id p={f.peticao} />
        <span className={styles.acoes}>
          <button className={`${styles.ico} ${validado ? styles.icoOn : ''}`} disabled={ocupado} aria-pressed={validado}
            title={validado ? 'Validado — clique para desfazer' : 'Marcar como conferido'} aria-label="Validar"
            onClick={() => onAtualizar(f.id, { status: validado ? 'extraido' : 'validado' })}>✓</button>
          <button className={styles.ico} disabled={ocupado} title="Editar tema, sujeito e nota" aria-label="Editar" onClick={() => setEditando((v) => !v)}>✎</button>
          <button className={styles.ico} disabled={ocupado} title="Rejeitar (não é um valor do caso)" aria-label="Rejeitar" onClick={() => onAtualizar(f.id, { status: 'rejeitado' })}>✕</button>
        </span>
      </div>
      {f.fonte_citada && <div className={styles.fonte}>fonte citada: {f.fonte_citada}</div>}
      {f.nota && !editando && <div className={styles.nota}>📝 {f.nota}</div>}
      <div className={styles.links}>
        <button className={styles.link} onClick={() => setTrecho((v) => !v)}>{trecho ? 'ocultar trecho' : 'ver trecho'}</button>
        <button className={styles.link} onClick={() => setOnde((v) => !v)} title="Outras peças do caso em que este mesmo número aparece">{onde ? 'ocultar' : 'onde mais aparece'}</button>
        {f.ocorrencias > 1 && <span className={styles.dica}>citado {f.ocorrencias}× nesta peça</span>}
      </div>
      {trecho && f.trecho && <blockquote className={styles.trecho}><Trecho texto={f.trecho} /></blockquote>}
      {onde && (
        <div className={styles.onde}>
          {outros.isLoading && <span className={styles.dica}>procurando…</span>}
          {outros.data && outros.data.length === 0 && <span className={styles.dica}>Não aparece escrito igual em outra peça (pode estar em outro formato).</span>}
          {outros.data?.map((o) => (
            <div key={o.peca_id} className={styles.ondeLinha}>
              <Id p={{ peca_id: o.peca_id, id_processual: o.id_processual, data: o.data, titulo: o.titulo ?? '', link_pdf: o.link_pdf, link_md: o.link_md }} />
              <span className={styles.dica}>{o.tipo_pje ?? '—'} · {o.ocorrencias}×</span>
              <span className={styles.ondeTrecho}>{o.trecho.slice(0, 200)}</span>
            </div>
          ))}
        </div>
      )}
      {editando && (
        <div className={styles.editor}>
          <label>Tema
            <select value={tema} onChange={(e) => setTema(e.target.value)}>
              {temas.map((t) => <option key={t.chave} value={t.chave}>{t.rotulo}</option>)}
            </select>
          </label>
          <label>Sujeito
            <input value={sujeito} onChange={(e) => setSujeito(e.target.value)} placeholder="Quem/qual veículo este valor descreve" />
          </label>
          <label className={styles.nota2}>Nota
            <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Ex.: conferido com o balanço do AJ" />
          </label>
          <button className={styles.mini} disabled={ocupado}
            onClick={() => { onAtualizar(f.id, { tema, sujeito_canonico: sujeito, nota: nota.trim() || null }); setEditando(false) }}>salvar</button>
          <button className={styles.miniLink} onClick={() => setEditando(false)}>cancelar</button>
        </div>
      )}
    </div>
  )
}

export default function Numeros({ casoId }: { casoId: string }) {
  const qc = useQueryClient()
  const [visao, setVisao] = useState<Visao>('divergencias')
  const [filtros, setFiltros] = useState<FiltrosValores>({})
  const [abertos, setAbertos] = useState<Set<string>>(new Set())

  const { data: temas = [] } = useQuery({ queryKey: ['autos-ia', 'fatos-temas'], queryFn: autosIa.temasFatos, staleTime: Infinity })
  const status = useQuery({
    queryKey: ['autos-ia', 'fatos-valores', 'status', casoId],
    queryFn: () => autosIa.statusFatosValores(casoId),
    refetchInterval: (q) => (q.state.data?.estado === 'rodando' ? 3000 : false),
  })
  const recon = useQuery({
    queryKey: ['autos-ia', 'fatos-valores', 'recon', casoId, status.data?.total_fatos ?? 0],
    queryFn: () => autosIa.reconciliacaoValores(casoId),
    staleTime: 30_000,
  })
  const lista = useQuery({
    queryKey: ['autos-ia', 'fatos-valores', 'lista', casoId, filtros, status.data?.total_fatos ?? 0],
    queryFn: () => autosIa.listarFatosValores(casoId, filtros),
    enabled: visao === 'todos',
  })
  const recarregar = () => qc.invalidateQueries({ queryKey: ['autos-ia', 'fatos-valores'] })
  const extrair = useMutation({
    mutationFn: (opts: { forcar?: boolean; limitePecas?: number }) => autosIa.extrairFatosValores(casoId, opts),
    onSuccess: (r) => { qc.setQueryData(['autos-ia', 'fatos-valores', 'status', casoId], r) },
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível iniciar.'),
  })
  const atualizar = useMutation({
    mutationFn: (v: { id: string; body: { tema?: string; sujeito_canonico?: string; status?: string; nota?: string | null } }) =>
      autosIa.atualizarFatoValor(casoId, v.id, v.body),
    onSuccess: recarregar,
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível salvar.'),
  })
  const onAtualizar = (id: string, body: any) => atualizar.mutate({ id, body })

  const st = status.data
  const rodando = st?.estado === 'rodando' || extrair.isPending
  const r = recon.data
  const alternar = (k: string) => setAbertos((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n })
  const estimativa = ((st?.pecas_pendentes ?? 0) * 0.02).toFixed(2)

  const iniciar = (forcar = false) => {
    const msg = forcar
      ? 'Reextrair os valores de TODAS as peças narrativas (os que você validou ou editou são mantidos)?'
      : `Ler os valores em R$ de ${st?.pecas_pendentes ?? 0} peça(s) (petições, decisões, pareceres) com IA — custo estimado ≈ US$ ${estimativa}. Os anexos não entram: servem de conferência. Continuar?`
    if (window.confirm(msg)) extrair.mutate({ forcar })
  }

  const afirmantes = Array.from(new Set((r?.corroboracoes ?? []).flatMap((c) => c.afirmantes).concat((r?.divergencias ?? []).flatMap((d) => d.afirmantes)))).sort()

  return (
    <div className={styles.wrap}>
      <div className={styles.topo}>
        <div className={styles.cobertura}>
          {st && st.total_fatos > 0
            ? <><strong>{st.total_fatos}</strong> valor(es) em <strong>{st.pecas_com_fatos}</strong> peça(s) · <strong>{st.validados}</strong> conferido(s) por você.</>
            : <>Nenhum valor extraído ainda.</>}
          {' '}Fonte: só peças narrativas (petições, decisões, pareceres); os anexos servem de conferência — "onde mais aparece".
          {st && st.pecas_pendentes > 0 && !rodando && <span className={styles.aviso}> {st.pecas_pendentes} peça(s) ainda não lidas.</span>}
        </div>
        <div className={styles.botoes}>
          <button className={styles.btn} disabled={rodando || (st?.pecas_pendentes ?? 0) === 0} onClick={() => iniciar(false)}
            title="Lê os valores das peças que ainda não foram lidas">
            {rodando ? 'Extraindo…' : `Extrair valores${st?.pecas_pendentes ? ` (${st.pecas_pendentes} peças · ≈ US$ ${estimativa})` : ''}`}
          </button>
          {!rodando && (st?.total_fatos ?? 0) > 0 && <button className={styles.miniLink} onClick={() => iniciar(true)}>reextrair tudo</button>}
          {rodando && st && <span className={styles.dica}>{st.feitos}/{st.total} peças · {st.fatos_novos} valores · US$ {st.custo_usd.toFixed(2)}</span>}
          {!rodando && st?.mensagem && <span className={st.estado === 'erro' ? styles.erro : styles.dica}>{st.mensagem}</span>}
        </div>
      </div>

      <div className={styles.barra}>
        <div className={styles.seg} role="tablist" aria-label="Visão">
          <button role="tab" aria-selected={visao === 'divergencias'} className={visao === 'divergencias' ? styles.segOn : ''} onClick={() => setVisao('divergencias')}>
            Divergências <span className={styles.n}>{r?.resumo.divergencias ?? 0}</span>
          </button>
          <button role="tab" aria-selected={visao === 'corroboracoes'} className={visao === 'corroboracoes' ? styles.segOn : ''} onClick={() => setVisao('corroboracoes')}>
            Mesmo número, várias fontes <span className={styles.n}>{r?.resumo.corroboracoes ?? 0}</span>
          </button>
          <button role="tab" aria-selected={visao === 'todos'} className={visao === 'todos' ? styles.segOn : ''} onClick={() => setVisao('todos')}>
            Todos os valores <span className={styles.n}>{r?.resumo.fatos ?? 0}</span>
          </button>
        </div>
      </div>

      {visao === 'divergencias' && (
        <>
          <p className={styles.explica}>Mesmo tema e mesmo sujeito, números diferentes — por afirmante. É a pauta de reconciliação: quem afirma o quê, e onde as versões não fecham.</p>
          {r?.divergencias.length === 0 && <p className={styles.vazio}>{(st?.total_fatos ?? 0) === 0 ? 'Extraia os valores para ver as divergências.' : 'Nenhuma divergência encontrada com os valores atuais.'}</p>}
          {r?.divergencias.map((d, i) => {
            const k = `d${i}`
            return (
              <div key={k} className={styles.card}>
                <button className={styles.cardHead} onClick={() => alternar(k)} aria-expanded={abertos.has(k)}>
                  <span className={styles.chevron}>{abertos.has(k) ? '▾' : '▸'}</span>
                  <span className={styles.chipTema}>{d.tema_rotulo}</span>
                  <span className={styles.titulo}>{d.sujeito}</span>
                  <span className={styles.conta}>{d.valores.length} números · {d.afirmantes.length} afirmante(s){d.razao ? ` · ×${String(d.razao).replace('.', ',')}` : ''}</span>
                </button>
                {abertos.has(k) && (
                  <div className={styles.corpo}>
                    {d.valores.map((v) => (
                      <div key={v.valor_centavos} className={styles.grupoValor}>
                        <div className={styles.grupoTopo}><span className={styles.valorG}>{v.valor}</span><span className={styles.afirmantes}>{v.afirmantes.join(' · ')}</span></div>
                        {v.fatos.map((f) => <FatoLinha key={f.id} f={f} temas={temas} ocupado={atualizar.isPending} casoId={casoId} onAtualizar={onAtualizar} mostrarValor={false} />)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </>
      )}

      {visao === 'corroboracoes' && (
        <>
          <p className={styles.explica}>Um mesmo número citado em peças diferentes — pontos de apoio (várias fontes concordam) e de origem (quem citou quem).</p>
          {r?.corroboracoes.length === 0 && <p className={styles.vazio}>Nenhum número repetido entre peças.</p>}
          {r?.corroboracoes.map((c, i) => {
            const k = `c${i}`
            return (
              <div key={k} className={styles.card}>
                <button className={styles.cardHead} onClick={() => alternar(k)} aria-expanded={abertos.has(k)}>
                  <span className={styles.chevron}>{abertos.has(k) ? '▾' : '▸'}</span>
                  <span className={styles.valorG}>{c.valor}</span>
                  <span className={styles.titulo}>{c.sujeitos.slice(0, 2).join(' · ') || c.temas.join(' · ')}</span>
                  <span className={styles.conta}>{c.n_pecas} peças · {c.afirmantes.length} afirmante(s)</span>
                </button>
                {abertos.has(k) && <div className={styles.corpo}>{c.fatos.map((f) => <FatoLinha key={f.id} f={f} temas={temas} ocupado={atualizar.isPending} casoId={casoId} onAtualizar={onAtualizar} mostrarValor={false} />)}</div>}
              </div>
            )
          })}
        </>
      )}

      {visao === 'todos' && (
        <>
          <div className={styles.filtros}>
            <select aria-label="Tema" value={filtros.tema ?? ''} onChange={(e) => setFiltros({ ...filtros, tema: e.target.value || undefined })}>
              <option value="">Todos os temas</option>
              {temas.map((t) => <option key={t.chave} value={t.chave}>{t.rotulo}</option>)}
            </select>
            <select aria-label="Afirmante" value={filtros.afirmante ?? ''} onChange={(e) => setFiltros({ ...filtros, afirmante: e.target.value || undefined })}>
              <option value="">Qualquer afirmante</option>
              <option value="juizo">Juízo</option><option value="mp">Ministério Público</option><option value="aj">Administrador Judicial</option>
              {afirmantes.filter((a) => !['Juízo', 'Ministério Público', 'Administrador Judicial'].includes(a)).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <select aria-label="Natureza" value={filtros.natureza ?? ''} onChange={(e) => setFiltros({ ...filtros, natureza: e.target.value || undefined })}>
              <option value="">Toda natureza</option>
              {Object.entries(NATUREZA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select aria-label="Status" value={filtros.status ?? ''} onChange={(e) => setFiltros({ ...filtros, status: e.target.value || undefined })}>
              <option value="">Sem os rejeitados</option><option value="validado">Só conferidos</option><option value="extraido">Só não conferidos</option><option value="rejeitado">Só rejeitados</option>
            </select>
            <input aria-label="Buscar" placeholder="Buscar sujeito, trecho, nota…" value={filtros.q ?? ''} onChange={(e) => setFiltros({ ...filtros, q: e.target.value || undefined })} />
          </div>
          {lista.data && <p className={styles.explica}>{lista.data.total} valor(es){lista.data.total > lista.data.itens.length ? ` (mostrando ${lista.data.itens.length})` : ''}, do maior para o menor.</p>}
          {lista.data?.itens.map((f) => <FatoLinha key={f.id} f={f} temas={temas} ocupado={atualizar.isPending} casoId={casoId} onAtualizar={onAtualizar} />)}
          {lista.data?.itens.length === 0 && <p className={styles.vazio}>Nada com esses filtros.</p>}
        </>
      )}
    </div>
  )
}
