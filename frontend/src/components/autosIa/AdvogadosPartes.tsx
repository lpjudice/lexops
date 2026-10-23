import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import type { AdvPessoa, PeticaoRef } from '../../api/autosIa'
import styles from './AdvogadosPartes.module.css'

type Modo = 'advogado' | 'parte'

const semAcento = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
const nomeAdv = (a: AdvPessoa) => a.nome || `Advogado sem nome identificado`
const dataBr = (d: string | null) => (d ? d.split('-').reverse().join('/') : '')

/** ID processual da petição: clique abre o PDF (ou, sem PDF, o .md); "md" abre o resumo + inteiro teor. */
function IdPeticao({ p }: { p: PeticaoRef }) {
  const rotulo = p.id_processual || 's/ ID'
  const principal = p.link_pdf || p.link_md
  const dica = `${p.titulo}${p.data ? ` · ${dataBr(p.data)}` : ''}`
  return (
    <span className={styles.idWrap}>
      {principal ? (
        <a className={styles.id} href={principal} target="_blank" rel="noreferrer" title={`${p.link_pdf ? 'Abrir PDF' : 'Abrir .md'} — ${dica}`}>
          {rotulo}
        </a>
      ) : (
        <span className={styles.idSemLink} title={`${dica} — sem arquivo no Drive`}>{rotulo}</span>
      )}
      {p.link_pdf && p.link_md && (
        <a className={styles.idMd} href={p.link_md} target="_blank" rel="noreferrer" title={`Abrir resumo + inteiro teor (.md) — ${dica}`}>md</a>
      )}
    </span>
  )
}

function Ids({ lista }: { lista: PeticaoRef[] }) {
  return (
    <div className={styles.ids}>
      {lista.map((p) => <IdPeticao key={p.peca_id} p={p} />)}
    </div>
  )
}

export default function AdvogadosPartes({ casoId }: { casoId: string }) {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['autos-ia', 'advogados-partes', casoId],
    queryFn: () => autosIa.advogadosPartes(casoId),
    staleTime: 60_000,
  })
  const [modo, setModo] = useState<Modo>('advogado')
  const [busca, setBusca] = useState('')
  const [abertos, setAbertos] = useState<Set<string>>(new Set())
  const [mostrarSem, setMostrarSem] = useState(false)

  const termo = semAcento(busca.trim())

  const advogados = useMemo(() => {
    if (!data) return []
    if (!termo) return data.advogados
    const digitos = termo.replace(/\D/g, '')
    return data.advogados.filter((a) => {
      const alvo = semAcento(`${a.nome ?? ''} ${a.oabs.join(' ')}`)
      return alvo.includes(termo) || (digitos.length >= 3 && a.oabs.some((o) => o.replace(/\D/g, '').includes(digitos)))
    })
  }, [data, termo])

  const partes = useMemo(() => {
    if (!data) return []
    if (!termo) return data.partes
    return data.partes.filter((p) => semAcento(`${p.nome} ${p.variantes.join(' ')}`).includes(termo))
  }, [data, termo])

  const lista = modo === 'advogado' ? advogados : partes
  const alternar = (id: string) =>
    setAbertos((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const estaAberto = (id: string) => abertos.has(id) || (!!termo && lista.length <= 2)

  // Clicar numa parte (dentro de um advogado) ou num advogado (dentro de uma parte) troca a visão já filtrada.
  const irParaParte = (nome: string) => { setModo('parte'); setBusca(nome); setAbertos(new Set()) }
  const irParaAdvogado = (a: AdvPessoa) => { setModo('advogado'); setBusca(a.oabs[0] ?? a.nome ?? ''); setAbertos(new Set()) }

  if (isLoading) return <p className={styles.vazio}>Montando a relação a partir das petições…</p>
  if (isError || !data) {
    return <p className={styles.vazio}>Não foi possível carregar a relação. <button className={styles.link} onClick={() => refetch()}>Tentar de novo</button></p>
  }

  const r = data.resumo
  const semLinhas = data.sem_advogado

  return (
    <div className={styles.wrap}>
      <div className={styles.cobertura}>
        <strong>{r.peticoes_total}</strong> petição(ões) analisada(s) — fonte: só petições e recursos, não os documentos.
        {' '}<strong>{r.peticoes_com_advogado}</strong> com advogado identificado na assinatura/qualificação
        {' → '}<strong>{r.advogados}</strong> advogado(s) · <strong>{r.partes}</strong> parte(s).
        {r.peticoes_sem_texto > 0 && (
          <span className={styles.aviso}>
            {' '}{r.peticoes_sem_texto} petição(ões) sem texto lido (arquivo não extraído) — use <em>Reler pendentes</em> para completar.
          </span>
        )}
      </div>

      <div className={styles.barra}>
        <div className={styles.seg} role="tablist" aria-label="Visão">
          <button role="tab" aria-selected={modo === 'advogado'} className={modo === 'advogado' ? styles.segOn : ''} onClick={() => { setModo('advogado'); setBusca('') }}>
            Por advogado <span className={styles.n}>{data.advogados.length}</span>
          </button>
          <button role="tab" aria-selected={modo === 'parte'} className={modo === 'parte' ? styles.segOn : ''} onClick={() => { setModo('parte'); setBusca('') }}>
            Por parte <span className={styles.n}>{data.partes.length}</span>
          </button>
        </div>
        <input
          className={styles.busca}
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder={modo === 'advogado' ? 'Filtrar advogado (nome ou OAB)…' : 'Filtrar parte…'}
          aria-label="Filtrar"
        />
        {busca && <button className={styles.link} onClick={() => setBusca('')}>limpar</button>}
        <button className={styles.link} onClick={() => refetch()} disabled={isFetching} title="Recalcula com o que já foi lido">
          {isFetching ? 'atualizando…' : 'atualizar'}
        </button>
      </div>

      {lista.length === 0 && <p className={styles.vazio}>Nada encontrado{busca ? ` para “${busca}”` : ''}.</p>}

      <div className={styles.lista}>
        {modo === 'advogado' && advogados.map((a) => (
          <div key={a.id} className={styles.card}>
            <button className={styles.cardHead} onClick={() => alternar(a.id)} aria-expanded={estaAberto(a.id)}>
              <span className={styles.chevron}>{estaAberto(a.id) ? '▾' : '▸'}</span>
              <span className={styles.nome}>{nomeAdv(a)}</span>
              {a.oabs.map((o) => <span key={o} className={styles.oab}>{o}</span>)}
              <span className={styles.conta}>{a.partes.length} parte(s) · {a.total_peticoes} petição(ões)</span>
            </button>
            {estaAberto(a.id) && (
              <div className={styles.corpo}>
                {a.partes.map((p) => (
                  <div key={p.chave} className={styles.linha}>
                    <button className={styles.alvo} onClick={() => irParaParte(p.nome)} title={p.variantes.length > 1 ? `Variações: ${p.variantes.join(' | ')}` : 'Ver todos os advogados desta parte'}>
                      {p.nome}
                    </button>
                    <Ids lista={p.peticoes} />
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {modo === 'parte' && partes.map((p) => (
          <div key={p.chave} className={styles.card}>
            <button className={styles.cardHead} onClick={() => alternar(p.chave)} aria-expanded={estaAberto(p.chave)}>
              <span className={styles.chevron}>{estaAberto(p.chave) ? '▾' : '▸'}</span>
              <span className={styles.nome} title={p.variantes.length > 1 ? `Variações: ${p.variantes.join(' | ')}` : undefined}>{p.nome}</span>
              <span className={styles.conta}>{p.advogados.length} advogado(s) · {p.total_peticoes} petição(ões)</span>
            </button>
            {estaAberto(p.chave) && (
              <div className={styles.corpo}>
                {p.advogados.map((a) => (
                  <div key={a.id} className={styles.linha}>
                    <button className={styles.alvo} onClick={() => irParaAdvogado(a)} title="Ver todas as partes deste advogado">
                      {nomeAdv(a)}
                    </button>
                    {a.oabs.map((o) => <span key={o} className={styles.oab}>{o}</span>)}
                    <Ids lista={a.peticoes} />
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {semLinhas.length > 0 && (
        <div className={styles.sem}>
          <button className={styles.cardHead} onClick={() => setMostrarSem((v) => !v)} aria-expanded={mostrarSem}>
            <span className={styles.chevron}>{mostrarSem ? '▾' : '▸'}</span>
            <span className={styles.nome}>Petições sem advogado identificado</span>
            <span className={styles.conta}>{semLinhas.length}</span>
          </button>
          {mostrarSem && (
            <div className={styles.corpo}>
              {semLinhas.map((s) => (
                <div key={s.peticao.peca_id} className={styles.linha}>
                  <IdPeticao p={s.peticao} />
                  <span className={styles.motivo}>{s.motivo === 'sem_texto' ? 'arquivo sem texto lido' : 'sem OAB na assinatura/qualificação'}</span>
                  {s.parte && <span className={styles.parteSem}>{s.parte}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
