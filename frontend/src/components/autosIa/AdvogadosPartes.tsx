import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import type { AdvogadosPartes as Relacao, AdvPessoa, MotivoSemAdvogado, PeticaoRef } from '../../api/autosIa'
import styles from './AdvogadosPartes.module.css'

type Modo = 'advogado' | 'parte'

const semAcento = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
const nomeAdv = (a: AdvPessoa) => a.nome || 'Advogado sem nome identificado'
const dataBr = (d: string | null) => (d ? d.split('-').reverse().join('/') : '')

const MOTIVO: Record<MotivoSemAdvogado, string> = {
  sem_texto: 'arquivo sem texto lido — releia a peça',
  texto_incompleto: 'texto cortado, assinatura não lida — releia a peça',
  ministerio_publico: 'Ministério Público · assinada por promotor, não há OAB',
  administrador_judicial: 'Administrador Judicial · não é advogado, não há OAB',
  sem_oab: 'sem OAB identificada no texto',
}

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

/** Campo de texto inline: Enter salva, Esc cancela. */
function EditarNome({ inicial, ocupado, onSalvar, onCancelar }: { inicial: string; ocupado: boolean; onSalvar: (nome: string) => void; onCancelar: () => void }) {
  const [v, setV] = useState(inicial)
  return (
    <span className={styles.editar}>
      <input
        className={styles.campo}
        autoFocus
        value={v}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && v.trim()) onSalvar(v.trim())
          if (e.key === 'Escape') onCancelar()
        }}
        aria-label="Nome do advogado"
      />
      <button className={styles.mini} disabled={ocupado || !v.trim()} onClick={() => onSalvar(v.trim())}>salvar</button>
      <button className={styles.miniLink} onClick={onCancelar}>cancelar</button>
    </span>
  )
}

function AdicionarAdvogado({ ocupado, onAdicionar, onCancelar }: { ocupado: boolean; onAdicionar: (nome: string, oab: string) => void; onCancelar: () => void }) {
  const [nome, setNome] = useState('')
  const [oab, setOab] = useState('')
  const enviar = () => nome.trim() && onAdicionar(nome.trim(), oab.trim())
  return (
    <div className={styles.novo}>
      <input className={styles.campo} autoFocus placeholder="Nome do advogado" value={nome} onChange={(e) => setNome(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && enviar()} aria-label="Nome do novo advogado" />
      <input className={`${styles.campo} ${styles.campoOab}`} placeholder="OAB (opcional) ex.: ES 4939" value={oab} onChange={(e) => setOab(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && enviar()} aria-label="OAB do novo advogado" />
      <button className={styles.mini} disabled={ocupado || !nome.trim()} onClick={enviar}>adicionar</button>
      <button className={styles.miniLink} onClick={onCancelar}>cancelar</button>
    </div>
  )
}

export default function AdvogadosPartes({ casoId }: { casoId: string }) {
  const qc = useQueryClient()
  const chave = ['autos-ia', 'advogados-partes', casoId]
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: chave,
    queryFn: () => autosIa.advogadosPartes(casoId),
    staleTime: 60_000,
  })
  const [modo, setModo] = useState<Modo>('advogado')
  const [busca, setBusca] = useState('')
  const [abertos, setAbertos] = useState<Set<string>>(new Set())
  const [mostrarSem, setMostrarSem] = useState(false)
  const [editando, setEditando] = useState<string | null>(null)        // adv_id em edição de nome
  const [adicionandoEm, setAdicionandoEm] = useState<string | null>(null) // parte_chave com o formulário aberto
  const [removidosAbertos, setRemovidosAbertos] = useState<Set<string>>(new Set())

  const aoSalvar = (r: Relacao) => { qc.setQueryData(chave, r); setEditando(null); setAdicionandoEm(null) }
  const aoErro = (e: any) => alert(e?.response?.data?.detail || e?.message || 'Não foi possível salvar.')
  const renomear = useMutation({ mutationFn: (v: { advId: string; nome: string }) => autosIa.renomearAdvogado(casoId, v.advId, v.nome), onSuccess: aoSalvar, onError: aoErro })
  const adicionar = useMutation({ mutationFn: (v: { parte: string; nome: string; oab: string }) => autosIa.adicionarAdvogado(casoId, v.parte, v.nome, v.oab), onSuccess: aoSalvar, onError: aoErro })
  const principal = useMutation({ mutationFn: (v: { parte: string; advId: string | null }) => autosIa.definirAdvogadoPrincipal(casoId, v.parte, v.advId), onSuccess: aoSalvar, onError: aoErro })
  const remover = useMutation({ mutationFn: (v: { parte: string; advId: string }) => autosIa.removerAdvogadoDaParte(casoId, v.parte, v.advId), onSuccess: aoSalvar, onError: aoErro })
  const restaurar = useMutation({ mutationFn: (v: { parte: string; advId: string }) => autosIa.restaurarAdvogadoDaParte(casoId, v.parte, v.advId), onSuccess: aoSalvar, onError: aoErro })
  const ocupado = renomear.isPending || adicionar.isPending || principal.isPending || remover.isPending || restaurar.isPending

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
  const faltaTexto = semLinhas.filter((s) => s.motivo === 'sem_texto' || s.motivo === 'texto_incompleto').length

  const estrela = (parte: string, a: { id: string; principal: boolean; sugerido?: boolean }) => {
    const rotulo = a.principal
      ? 'Advogado principal desta parte — clique para desmarcar'
      : a.sugerido
        ? 'Sugerido (mais petições nesta parte) — clique para marcar como principal'
        : 'Marcar como advogado principal desta parte'
    return (
      <button
        className={`${styles.estrela} ${a.principal ? styles.estrelaOn : a.sugerido ? styles.estrelaSug : ''}`}
        disabled={ocupado}
        aria-pressed={a.principal}
        aria-label={rotulo}
        title={rotulo}
        onClick={() => principal.mutate({ parte, advId: a.principal ? null : a.id })}
      >
        {a.principal ? '★' : '☆'}
      </button>
    )
  }

  const nomeEditavel = (a: AdvPessoa, destaque?: boolean) =>
    editando === a.id ? (
      <EditarNome inicial={a.nome ?? ''} ocupado={renomear.isPending} onSalvar={(nome) => renomear.mutate({ advId: a.id, nome })} onCancelar={() => setEditando(null)} />
    ) : (
      <>
        {destaque
          ? <span className={styles.nome}>{nomeAdv(a)}</span>
          : <button className={styles.alvo} onClick={() => irParaAdvogado(a)} title="Ver todas as partes deste advogado">{nomeAdv(a)}</button>}
        <button className={styles.lapis} onClick={() => setEditando(a.id)} title={a.oabs.length ? 'Editar o nome (vale em todas as partes)' : 'Editar o nome'} aria-label={`Editar nome de ${nomeAdv(a)}`}>✎</button>
      </>
    )

  return (
    <div className={styles.wrap}>
      <div className={styles.cobertura}>
        <strong>{r.peticoes_total}</strong> petição(ões) analisada(s) — fonte: só petições (documento com tipo de petição no PJe), não os anexos
        {r.eventos_sem_arquivo > 0 && <> nem os {r.eventos_sem_arquivo} protocolos sem arquivo</>}.
        {' '}<strong>{r.peticoes_com_advogado}</strong> com advogado identificado → <strong>{r.advogados}</strong> advogado(s) · <strong>{r.partes}</strong> parte(s).
        {faltaTexto > 0 && (
          <span className={styles.aviso}> {faltaTexto} sem texto ou cortada(s) — use <em>Reler</em> na peça.</span>
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
                <div className={styles.linha}>
                  <span className={styles.rotulo}>Nome</span>
                  {nomeEditavel(a, true)}
                </div>
                {a.partes.map((p) => (
                  <div key={p.chave} className={styles.linha}>
                    {estrela(p.chave, { id: a.id, principal: p.principal })}
                    <button className={styles.alvo} onClick={() => irParaParte(p.nome)} title={p.variantes.length > 1 ? `Variações: ${p.variantes.join(' | ')}` : 'Ver todos os advogados desta parte'}>
                      {p.nome}
                    </button>
                    {p.principal && <span className={styles.tagPrincipal}>principal</span>}
                    {p.manual && <span className={styles.tagManual}>adicionado</span>}
                    <Ids lista={p.peticoes} />
                    <button className={styles.x} disabled={ocupado} onClick={() => remover.mutate({ parte: p.chave, advId: a.id })} title="Tirar este advogado desta parte" aria-label={`Remover ${nomeAdv(a)} de ${p.nome}`}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {modo === 'parte' && partes.map((p) => {
          const princ = p.advogados.find((a) => a.principal)
          return (
            <div key={p.chave} className={styles.card}>
              <button className={styles.cardHead} onClick={() => alternar(p.chave)} aria-expanded={estaAberto(p.chave)}>
                <span className={styles.chevron}>{estaAberto(p.chave) ? '▾' : '▸'}</span>
                <span className={styles.nome} title={p.variantes.length > 1 ? `Variações: ${p.variantes.join(' | ')}` : undefined}>{p.nome}</span>
                {princ && <span className={styles.tagPrincipal} title="Advogado principal">★ {nomeAdv(princ)}</span>}
                <span className={styles.conta}>{p.advogados.length} advogado(s) · {p.total_peticoes} petição(ões)</span>
              </button>
              {estaAberto(p.chave) && (
                <div className={styles.corpo}>
                  {p.advogados.length === 0 && <p className={styles.semAdv}>Nenhum advogado identificado nas petições desta parte — adicione abaixo.</p>}
                  {p.advogados.map((a) => (
                    <div key={a.id} className={styles.linha}>
                      {estrela(p.chave, a)}
                      {nomeEditavel(a)}
                      {a.oabs.map((o) => <span key={o} className={styles.oab}>{o}</span>)}
                      {a.principal && <span className={styles.tagPrincipal}>principal</span>}
                      {!a.principal && a.sugerido && <span className={styles.tagSug}>sugerido</span>}
                      {a.manual && <span className={styles.tagManual}>adicionado</span>}
                      <Ids lista={a.peticoes} />
                      <button className={styles.x} disabled={ocupado} onClick={() => remover.mutate({ parte: p.chave, advId: a.id })} title="Tirar este advogado desta parte" aria-label={`Remover ${nomeAdv(a)} de ${p.nome}`}>×</button>
                    </div>
                  ))}

                  {adicionandoEm === p.chave ? (
                    <AdicionarAdvogado ocupado={adicionar.isPending} onAdicionar={(nome, oab) => adicionar.mutate({ parte: p.chave, nome, oab })} onCancelar={() => setAdicionandoEm(null)} />
                  ) : (
                    <div className={styles.rodape}>
                      <button className={styles.link} onClick={() => setAdicionandoEm(p.chave)}>+ Adicionar advogado</button>
                      {p.removidos.length > 0 && (
                        <button className={styles.miniLink} onClick={() => setRemovidosAbertos((s) => { const n = new Set(s); n.has(p.chave) ? n.delete(p.chave) : n.add(p.chave); return n })}>
                          {removidosAbertos.has(p.chave) ? 'ocultar' : 'ver'} {p.removidos.length} removido(s)
                        </button>
                      )}
                    </div>
                  )}
                  {removidosAbertos.has(p.chave) && p.removidos.map((a) => (
                    <div key={a.id} className={`${styles.linha} ${styles.removido}`}>
                      <span>{nomeAdv(a)}</span>
                      {a.oabs.map((o) => <span key={o} className={styles.oab}>{o}</span>)}
                      <button className={styles.miniLink} disabled={ocupado} onClick={() => restaurar.mutate({ parte: p.chave, advId: a.id })}>restaurar</button>
                    </div>
                  ))}

                  <div className={`${styles.linha} ${styles.petsParte}`}>
                    <span className={styles.rotulo}>Petições desta parte</span>
                    <Ids lista={p.peticoes} />
                  </div>
                </div>
              )}
            </div>
          )
        })}
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
                  <span className={s.motivo === 'ministerio_publico' || s.motivo === 'administrador_judicial' ? styles.motivoNeutro : styles.motivo}>
                    {MOTIVO[s.motivo]}{s.assinante ? ` — ${s.assinante}` : ''}
                  </span>
                  {s.parte && <button className={styles.alvo} onClick={() => irParaParte(s.parte as string)} title="Abrir a parte para adicionar um advogado">{s.parte}</button>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
