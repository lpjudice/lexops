import { Fragment, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import type { Posicao } from '../../api/autosIa'
import { Id } from './EstrategiaAdvogados'
import styles from './Estrategia.module.css'

type Visao = 'matriz' | 'contradicoes' | 'conflitos'
const dataBr = (d: string | null) => (d ? d.split('-').reverse().join('/') : '')
const TOM: Record<string, string> = { favoravel: 'pFav', contraria: 'pCon', condicionada: 'pCond', neutra: 'pNeu' }
const TIPO_ROTULO: Record<string, string> = { juizo: 'Juízo', mp: 'Ministério Público', aj: 'Administradora Judicial', parte: 'Parte' }

type Atualizar = (id: string, body: { posicao?: string; tema?: string; status?: string; nota?: string | null }) => void

function ItemPosicao({ p, opcoes, ocupado, onAtualizar }: {
  p: Posicao; opcoes: { temas: { chave: string; rotulo: string }[]; posicoes: { chave: string; rotulo: string }[] } | undefined; ocupado: boolean; onAtualizar: Atualizar
}) {
  const [trecho, setTrecho] = useState(false)
  const [editando, setEditando] = useState(false)
  const [posicao, setPosicao] = useState(p.posicao ?? 'neutra')
  const [tema, setTema] = useState(p.tema ?? 'outro')
  const [nota, setNota] = useState(p.nota ?? '')
  return (
    <div className={`${styles.pItem} ${p.validado ? styles.pOk : ''}`}>
      <div className={styles.linhaTopo}>
        <span className={styles.dica}>{dataBr(p.data)}</span>
        <Id p={p.peticao} />
        <span className={`${styles.pBadge} ${styles[TOM[p.posicao ?? 'neutra']]}`}>{p.posicao_rotulo}</span>
        <span className={styles.chip}>{p.tema_rotulo}</span>
        <span className={styles.pResumo}>{p.resumo}</span>
        <span className={styles.acoes}>
          <button className={`${styles.ico} ${p.validado ? styles.icoOn : ''}`} disabled={ocupado} aria-pressed={p.validado} aria-label="Validar"
            title={p.validado ? 'Conferida — clique para desfazer' : 'Marcar como conferida'} onClick={() => onAtualizar(p.id, { status: p.validado ? 'extraido' : 'validado' })}>✓</button>
          <button className={styles.ico} disabled={ocupado} aria-label="Editar" title="Corrigir posição/tema e anotar" onClick={() => setEditando((v) => !v)}>✎</button>
          <button className={styles.ico} disabled={ocupado} aria-label="Rejeitar" title="Rejeitar (não é uma posição da parte)" onClick={() => onAtualizar(p.id, { status: 'rejeitado' })}>✕</button>
        </span>
      </div>
      {p.pede && <div className={styles.dica}>Pede: {p.pede}</div>}
      {p.nota && !editando && <div className={styles.notaTxt}>📝 {p.nota}</div>}
      <button className={styles.link} onClick={() => setTrecho((v) => !v)}>{trecho ? 'ocultar trecho' : 'ver trecho'}</button>
      {trecho && p.trecho && <blockquote className={styles.trecho}>{p.trecho}</blockquote>}
      {editando && (
        <div className={styles.editor}>
          <label>Posição
            <select aria-label="Posição" value={posicao} onChange={(e) => setPosicao(e.target.value)}>{opcoes?.posicoes.map((o) => <option key={o.chave} value={o.chave}>{o.rotulo}</option>)}</select>
          </label>
          <label>Tema
            <select aria-label="Tema da posição" value={tema} onChange={(e) => setTema(e.target.value)}>{opcoes?.temas.map((o) => <option key={o.chave} value={o.chave}>{o.rotulo}</option>)}</select>
          </label>
          <label className={styles.notaCampo}>Nota
            <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Ex.: só aceita se houver prazo" />
          </label>
          <button className={styles.mini} disabled={ocupado} onClick={() => { onAtualizar(p.id, { posicao, tema, nota: nota.trim() || null }); setEditando(false) }}>salvar</button>
          <button className={styles.miniLink} onClick={() => setEditando(false)}>cancelar</button>
        </div>
      )}
    </div>
  )
}

export default function EstrategiaPosicoes({ casoId }: { casoId: string }) {
  const qc = useQueryClient()
  const [visao, setVisao] = useState<Visao>('matriz')
  const [aberta, setAberta] = useState<string | null>(null)        // "participante|tema"
  const [abertos, setAbertos] = useState<Set<string>>(new Set())
  const { data: opcoes } = useQuery({ queryKey: ['autos-ia', 'pos-opcoes'], queryFn: autosIa.opcoesPosicoes, staleTime: Infinity })
  const status = useQuery({
    queryKey: ['autos-ia', 'pos', 'status', casoId], queryFn: () => autosIa.statusPosicoes(casoId),
    refetchInterval: (q) => (q.state.data?.estado === 'rodando' ? 3000 : false),
  })
  const n = status.data?.total_posicoes ?? 0
  const matriz = useQuery({ queryKey: ['autos-ia', 'pos', 'matriz', casoId, n], queryFn: () => autosIa.matrizPosicoes(casoId), enabled: visao === 'matriz' })
  const contr = useQuery({ queryKey: ['autos-ia', 'pos', 'contr', casoId, n], queryFn: () => autosIa.contradicoesPosicoes(casoId), enabled: visao === 'contradicoes' })
  const confl = useQuery({ queryKey: ['autos-ia', 'pos', 'confl', casoId, n], queryFn: () => autosIa.conflitosAdvogados(casoId), enabled: visao === 'conflitos' })
  const recarregar = () => qc.invalidateQueries({ queryKey: ['autos-ia', 'pos'] })
  const extrair = useMutation({
    mutationFn: (forcar: boolean) => autosIa.extrairPosicoes(casoId, forcar),
    onSuccess: (r) => { qc.setQueryData(['autos-ia', 'pos', 'status', casoId], r) },
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível iniciar.'),
  })
  const atualizar = useMutation({
    mutationFn: (v: { id: string; body: Parameters<Atualizar>[1] }) => autosIa.atualizarPosicao(casoId, v.id, v.body),
    onSuccess: recarregar,
    onError: (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível salvar.'),
  })
  const onAtualizar: Atualizar = (id, body) => atualizar.mutate({ id, body })
  const st = status.data
  const rodando = st?.estado === 'rodando' || extrair.isPending
  const estimativa = ((st?.pecas_pendentes ?? 0) * 0.03).toFixed(2)
  const alternar = (k: string) => setAbertos((s) => { const x = new Set(s); x.has(k) ? x.delete(k) : x.add(k); return x })
  const iniciar = (forcar: boolean) => {
    const msg = forcar ? 'Reler as posições de TODAS as peças narrativas (as que você validou ou editou são mantidas)? Usa IA.'
      : `Ler as posições de ${st?.pecas_pendentes ?? 0} peça(s) com IA — custo estimado ≈ US$ ${estimativa}. Continuar?`
    if (window.confirm(msg)) extrair.mutate(forcar)
  }
  const Item = (p: Posicao) => <ItemPosicao key={p.id} p={p} opcoes={opcoes} ocupado={atualizar.isPending} onAtualizar={onAtualizar} />

  return (
    <div className={styles.wrap}>
      <p className={styles.explica}>
        Posição que cada participante <strong>assume expressamente</strong> nas peças (a IA só registra o que o autor da peça afirma, com o trecho como prova; nada é deduzido). Corrija o que estiver errado — o que você validar não é sobrescrito.
      </p>
      <div className={styles.barra}>
        <span className={styles.dica}>
          {st && st.total_posicoes > 0 ? <><strong>{st.total_posicoes}</strong> posição(ões) em {st.pecas_com_posicoes} peça(s) · {st.validadas} conferida(s).</> : 'Nenhuma posição lida ainda.'}
          {st && st.pecas_pendentes > 0 && !rodando && <span className={styles.aviso}> {st.pecas_pendentes} peça(s) ainda não lidas.</span>}
        </span>
        <button className={styles.btn} disabled={rodando || (st?.pecas_pendentes ?? 0) === 0} onClick={() => iniciar(false)}>
          {rodando ? 'Lendo…' : `Ler posições${st?.pecas_pendentes ? ` (${st.pecas_pendentes} peças · ≈ US$ ${estimativa})` : ''}`}
        </button>
        {!rodando && (st?.total_posicoes ?? 0) > 0 && <button className={styles.miniLink} onClick={() => iniciar(true)}>reler tudo</button>}
        {rodando && st && <span className={styles.dica}>{st.feitos}/{st.total} peças · {st.novas} posições · US$ {st.custo_usd.toFixed(2)}</span>}
        {!rodando && st?.mensagem && <span className={st.estado === 'erro' ? styles.erro : styles.dica}>{st.mensagem}</span>}
      </div>
      <div className={styles.seg} role="tablist" aria-label="Visão das posições">
        <button role="tab" aria-selected={visao === 'matriz'} className={visao === 'matriz' ? styles.segOn : ''} onClick={() => setVisao('matriz')}>Matriz de posições</button>
        <button role="tab" aria-selected={visao === 'contradicoes'} className={visao === 'contradicoes' ? styles.segOn : ''} onClick={() => setVisao('contradicoes')}>Contradições no tempo{contr.data ? <span className={styles.n}>{contr.data.total}</span> : null}</button>
        <button role="tab" aria-selected={visao === 'conflitos'} className={visao === 'conflitos' ? styles.segOn : ''} onClick={() => setVisao('conflitos')}>Advogados em conflito{confl.data ? <span className={styles.n}>{confl.data.total}</span> : null}</button>
      </div>

      {visao === 'matriz' && matriz.data && (
        matriz.data.linhas.length === 0 ? <p className={styles.vazio}>Leia as posições para montar a matriz.</p> : (
          <div className={styles.tabelaWrap}>
            <table className={styles.tabela}>
              <thead><tr><th>Participante</th>{matriz.data.temas.map((t) => <th key={t.chave}>{t.rotulo}</th>)}</tr></thead>
              <tbody>
                {matriz.data.linhas.map((l) => (
                  <Fragment key={l.chave}>
                    <tr>
                      <th scope="row"><span className={styles.nome}>{l.nome}</span> <span className={styles.dica}>{TIPO_ROTULO[l.tipo] ?? ''}{l.tipo === 'parte' ? ` · ${l.n_pecas} peça(s)` : ''}</span></th>
                      {matriz.data.temas.map((t) => {
                        const c = l.celulas[t.chave]; const k = `${l.chave}|${t.chave}`
                        return (
                          <td key={t.chave}>
                            {c ? <button className={`${styles.pBadge} ${styles[TOM[c.atual]]} ${aberta === k ? styles.pSel : ''}`} aria-expanded={aberta === k}
                                  title={c.inversao ? 'Já se posicionou nos dois sentidos' : c.mudou ? 'Mudou de posição' : undefined} onClick={() => setAberta(aberta === k ? null : k)}>
                                {c.atual_rotulo}{c.mudou ? ' ↯' : ''}{c.n > 1 ? ` ·${c.n}` : ''}
                              </button> : <span className={styles.dica}>—</span>}
                          </td>
                        )
                      })}
                    </tr>
                    {aberta?.startsWith(`${l.chave}|`) && (
                      <tr><td colSpan={matriz.data.temas.length + 1} className={styles.detalheCel}>
                        {l.celulas[aberta.split('|')[1]]?.itens.map(Item)}
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {visao === 'contradicoes' && contr.data && (
        <>
          <p className={styles.explica}>Mesmo participante, mesmo tema, posições diferentes em peças diferentes. “Inversão” = já foi a favor e contra. Útil para confrontar a parte com o que ela própria afirmou antes.</p>
          {contr.data.itens.length === 0 && <p className={styles.vazio}>Nenhuma mudança de posição encontrada com as posições atuais.</p>}
          {contr.data.itens.map((c) => {
            const k = `c${c.chave}|${c.tema}`
            return (
              <div key={k} className={styles.card}>
                <button className={styles.cardHead} aria-expanded={abertos.has(k)} onClick={() => alternar(k)}>
                  <span className={styles.chevron}>{abertos.has(k) ? '▾' : '▸'}</span>
                  <span className={styles.titulo}>{c.nome}</span>
                  <span className={styles.chip}>{c.tema_rotulo}</span>
                  {c.inversao && <span className={`${styles.pBadge} ${styles.pCon}`}>inversão</span>}
                  <span className={styles.conta}>{c.itens.map((i) => i.posicao_rotulo).join(' → ')}</span>
                </button>
                {abertos.has(k) && <div className={styles.corpo}>{c.itens.map(Item)}</div>}
              </div>
            )
          })}
        </>
      )}

      {visao === 'conflitos' && confl.data && (
        <>
          <p className={styles.explica}>Advogados que representam, ao mesmo tempo, partes <strong>a favor</strong> e partes <strong>contra</strong> no mesmo tema (usa a posição mais recente de cada parte). Em tese é um conflito de interesses a verificar — ou uma incoerência entre clientes.</p>
          {confl.data.itens.length === 0 && <p className={styles.vazio}>Nenhum conflito com as posições atuais.</p>}
          {confl.data.itens.map((c) => {
            const k = `x${c.advogado.id}|${c.tema}`
            return (
              <div key={k} className={styles.card}>
                <button className={styles.cardHead} aria-expanded={abertos.has(k)} onClick={() => alternar(k)}>
                  <span className={styles.chevron}>{abertos.has(k) ? '▾' : '▸'}</span>
                  <span className={styles.titulo}>{c.advogado.nome || c.advogado.id}</span>
                  <span className={styles.dica}>{c.advogado.oabs.join(' · ')}</span>
                  <span className={styles.chip}>{c.tema_rotulo}</span>
                  <span className={styles.conta}>{c.favoraveis.length} a favor × {c.contrarias.length} contra</span>
                </button>
                {abertos.has(k) && (
                  <div className={styles.corpo}>
                    <div className={styles.dica}>A favor:</div>
                    {c.favoraveis.map((p) => <div key={p.chave}><span className={styles.nome}>{p.principal && '★ '}{p.nome}</span>{Item(p.posicao_item)}</div>)}
                    <div className={styles.dica}>Contra:</div>
                    {c.contrarias.map((p) => <div key={p.chave}><span className={styles.nome}>{p.principal && '★ '}{p.nome}</span>{Item(p.posicao_item)}</div>)}
                  </div>
                )}
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}
