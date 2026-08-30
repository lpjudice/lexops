import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { diario2Api } from '../api/diario2'
import type { Diario2Publicacao, Diario2Dia, Diario2PrazoCreate, StatusPrazoDiario2 } from '../api/diario2'
import { processosApi } from '../api/processos'
import type { EstadoProcesso } from '../api/processos'
import { clientesApi } from '../api/clientes'
import { usuariosApi } from '../api/usuarios'
import DespachoStatusResumo from '../components/DespachoStatusResumo'
import PrazoEditorInline from '../components/PrazoEditorInline'
import ProcessoCombobox from '../components/ProcessoCombobox'
import LegendaPrazos from '../components/LegendaPrazos'
import {
  useCatalogoPrazos, sugestaoDaPeca, divergeDaLei, textoConfirmacaoDivergencia,
} from '../api/prazosLegais'
import PecaCombobox from '../components/PecaCombobox'
import styles from './Page.module.css'
import diario2Styles from './Diario2Page.module.css'

const TIPOS = ['contestacao', 'recurso', 'contrarrazoes', 'manifestacao', 'audiencia', 'pericia', 'outro']
const PECAS = [
  'Agravo de Instrumento', 'Agravo Interno', 'Agravo em Recurso Especial', 'Agravo em Recurso Extraordinário',
  'Alegações Finais', 'Audiência', 'Contestação', 'Contrarrazões', 'Contrarrazões de Agravo',
  'Contrarrazões de Apelação', 'Cumprimento de Sentença', 'Embargos de Declaração', 'Embargos de Divergência',
  'Embargos Infringentes', 'Exceção de Pré-Executividade', 'Impugnação', 'Impugnação ao Cumprimento de Sentença',
  'Manifestação', 'Memorial', 'Petição Intermediária', 'Quesitos', 'Recurso de Apelação', 'Recurso Especial',
  'Recurso Extraordinário', 'Recurso Ordinário', 'Réplica',
].sort((a, b) => a.localeCompare(b, 'pt-BR'))

function formatDate(date?: string | null) {
  if (!date) return '-'
  return new Date(date + 'T12:00:00').toLocaleDateString('pt-BR')
}

// Data de disponibilização representativa do dia (vem no texto de cada publicação).
function dispDoDia(dia: Diario2Dia): string | null {
  const pub = dia.publicacoes.find((p) => p.detalhes?.data_disponibilizacao)
  return pub?.detalhes?.data_disponibilizacao ?? null
}

function defaultPrazo(pub: Diario2Publicacao): Diario2PrazoCreate {
  return {
    processo_id: pub.processo_id ?? '',
    tipo: pub.analise_ia?.peca_necessaria ?? 'manifestacao',
    descricao: pub.analise_ia?.resumo ?? pub.texto_resumo ?? '',
    peca_necessaria: pub.analise_ia?.peca_necessaria ?? 'Manifestação',
    responsavel: '',
    dias_prazo: pub.analise_ia?.dias_prazo ?? 5,
    tipo_contagem: pub.analise_ia?.tipo_contagem ?? 'uteis',
  }
}

const STATUS_LABEL: Record<StatusPrazoDiario2, string> = {
  pendente: 'pendente',
  cumprido: 'cumprido',
  perdido: 'perdido',
  ignorado: 'ignorado',
  nada_a_fazer: 'nada a fazer',
}

function prazoLabel(pub: Diario2Publicacao) {
  if (!pub.tem_publicacao) return 'Sem publicação'
  if (!pub.prazo) return 'Sem prazo'
  return `${formatDate(pub.prazo.data_limite)} · ${STATUS_LABEL[pub.prazo.status] ?? pub.prazo.status}`
}

function ehNadaAFazer(pub: Diario2Publicacao) {
  return pub.despacho_status?.disposicao === 'nada_a_fazer' || pub.prazo?.status === 'nada_a_fazer'
}

function nomeCliente(pub: Diario2Publicacao) {
  return pub.cliente ?? pub.cliente_sugerido ?? 'Cliente não vinculado'
}

export default function Diario2Page() {
  const qc = useQueryClient()
  const [daysBack, setDaysBack] = useState(30)
  const [syncDays, setSyncDays] = useState(7)
  const [relembreDays, setRelembreDays] = useState(7)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [prazoPub, setPrazoPub] = useState<string | null>(null)
  const [prazoForm, setPrazoForm] = useState<Diario2PrazoCreate | null>(null)
  const [editPrazoPub, setEditPrazoPub] = useState<string | null>(null)
  const [msg, setMsg] = useState('')
  const { data: catalogoLegal } = useCatalogoPrazos()

  const { data, isLoading } = useQuery({
    queryKey: ['diario2', daysBack],
    queryFn: () => diario2Api.listar(daysBack),
  })
  const { data: gmailStatus } = useQuery({
    queryKey: ['diario2-gmail-status'],
    queryFn: diario2Api.gmailStatus,
  })
  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })
  const { data: usuarios = [] } = useQuery({
    queryKey: ['usuarios'],
    queryFn: usuariosApi.listar,
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const sync = useMutation({
    mutationFn: () => diario2Api.syncGmail(syncDays),
    onSuccess: (result) => {
      setMsg(result.mensagem)
      qc.invalidateQueries({ queryKey: ['diario2'] })
      qc.invalidateQueries({ queryKey: ['diario2-gmail-status'] })
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      setMsg(error.response?.data?.detail ?? 'Não foi possível importar o Gmail agora.')
    },
  })

  const analisar = useMutation({
    mutationFn: (id: string) => diario2Api.analisar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diario2'] }),
  })

  const criarPrazo = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Diario2PrazoCreate }) => diario2Api.criarPrazo(id, payload),
    onSuccess: () => {
      setPrazoPub(null)
      setPrazoForm(null)
      qc.invalidateQueries({ queryKey: ['diario2'] })
      qc.invalidateQueries({ queryKey: ['prazos'] })
    },
  })

  const statusPrazo = useMutation({
    mutationFn: ({ id, status }: { id: string; status: StatusPrazoDiario2 }) => diario2Api.atualizarPrazoStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['diario2'] })
      qc.invalidateQueries({ queryKey: ['prazos'] })
    },
  })

  const relembre = useMutation({
    mutationFn: () => diario2Api.relembre(relembreDays),
  })

  const nadaAFazer = useMutation({
    mutationFn: (id: string) => diario2Api.nadaAFazer(id),
    onSuccess: (r) => {
      const res = r.resultado_nada_a_fazer
      const canceladas = res.tarefas_canceladas
        ? ` ${res.tarefas_canceladas} tarefa(s) automática(s) cancelada(s).`
        : ''
      setMsg(res.aviso ?? `Marcado como "nada a fazer".${canceladas} Já espelhado na aba Nada a fazer em Prazos.`)
      qc.invalidateQueries({ queryKey: ['diario2'] })
      qc.invalidateQueries({ queryKey: ['diario'] })
      qc.invalidateQueries({ queryKey: ['prazos'] })
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      qc.invalidateQueries({ queryKey: ['despacho'] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setMsg(e.response?.data?.detail ?? 'Não foi possível marcar como "nada a fazer".'),
  })

  const desfazerNadaAFazer = useMutation({
    mutationFn: (id: string) => diario2Api.desfazerNadaAFazer(id),
    onSuccess: (r) => {
      const res = r.resultado_nada_a_fazer
      const partes = [
        res.prazo_removido
          ? 'o marcador de prazo foi removido'
          : res.prazo_id ? 'prazo de volta em pendente' : null,
        res.tarefas_reativadas ? `${res.tarefas_reativadas} tarefa(s) reativada(s)` : null,
      ].filter(Boolean).join(' · ')
      setMsg(res.aviso ?? `Tratamento desfeito${partes ? ` — ${partes}` : ''}.`)
      qc.invalidateQueries({ queryKey: ['diario2'] })
      qc.invalidateQueries({ queryKey: ['diario'] })
      qc.invalidateQueries({ queryKey: ['prazos'] })
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      qc.invalidateQueries({ queryKey: ['despacho'] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setMsg(e.response?.data?.detail ?? 'Não foi possível desfazer o tratamento.'),
  })


  const criarProcesso = async (data: { numero_cnj: string; cliente_id: string; estado: EstadoProcesso }): Promise<string> => {
    const p = await processosApi.criar(data)
    qc.invalidateQueries({ queryKey: ['processos'] })
    return p.id
  }

  const abrirPrazo = (pub: Diario2Publicacao) => {
    setPrazoPub(pub.id)
    // A sugestão da IA vem primeiro; se ela não trouxe dias, usa o prazo legal
    // da peça que ela indicou, em vez do chute fixo de 5 dias.
    const base = defaultPrazo(pub)
    const sug = sugestaoDaPeca(catalogoLegal, base.peca_necessaria)
    setPrazoForm(
      !pub.analise_ia?.dias_prazo && sug?.dias != null
        ? { ...base, dias_prazo: sug.dias, tipo_contagem: (sug.contagem ?? 'uteis') as 'uteis' | 'corridos' }
        : base,
    )
    setExpanded(pub.id)
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Recorte Digital OAB</h1>
          <p className={diario2Styles.muted}>Publicações importadas do Gmail do Recorte Digital/OABES.</p>
        </div>
        <div className={diario2Styles.toolbar}>
          <span
            className={`${diario2Styles.statusPill} ${gmailStatus?.ok ? '' : diario2Styles.statusWarn}`}
            title={gmailStatus?.email_esperado ? `Conta esperada: ${gmailStatus.email_esperado}` : undefined}
          >
            Gmail: {gmailStatus?.email ?? 'não conectado'}
          </span>
          <LegendaPrazos />
          <a className={styles.btnPrimary} href="/api/auth/google">Conectar Gmail master</a>
        </div>
      </div>

      <div className={diario2Styles.panel}>
        <div className={diario2Styles.controls}>
          <label className={styles.formRow}>
            <span className={styles.formLabel}>Ver últimos dias</span>
            <input className={`${styles.input} ${diario2Styles.smallField}`} type="number" min={1} max={180} value={daysBack} onChange={(e) => setDaysBack(Number(e.target.value))} />
          </label>
          <label className={styles.formRow}>
            <span className={styles.formLabel}>Importar dias</span>
            <input className={`${styles.input} ${diario2Styles.smallField}`} type="number" min={1} max={60} value={syncDays} onChange={(e) => setSyncDays(Number(e.target.value))} />
          </label>
          <button className={styles.btnPrimary} disabled={sync.isPending} onClick={() => sync.mutate()}>
            {sync.isPending ? 'Importando...' : 'Importar Gmail agora'}
          </button>
          <label className={styles.formRow}>
            <span className={styles.formLabel}>Relembre dias</span>
            <input className={`${styles.input} ${diario2Styles.smallField}`} type="number" min={1} max={60} value={relembreDays} onChange={(e) => setRelembreDays(Number(e.target.value))} />
          </label>
          <button className={diario2Styles.ghostBtn} disabled={relembre.isPending} onClick={() => relembre.mutate()}>
            {relembre.isPending ? 'Resumindo...' : 'Relembre'}
          </button>
        </div>
        {msg && <div className={diario2Styles.message}>{msg}</div>}
        {relembre.data && (
          <div className={diario2Styles.relembreBox}>
            <strong>Relembre dos últimos {relembre.data.days_back} dias: {relembre.data.total} publicação(ões)</strong>
            <div className={diario2Styles.relembreList}>
              {relembre.data.itens.map((item, idx) => (
                <div key={`${item.numero_cnj}-${idx}`} className={diario2Styles.relembreItem}>
                  <span>{formatDate(item.data_publicacao)}</span>
                  <code className={diario2Styles.cnj}>{item.numero_cnj ?? 'sem CNJ'}</code>
                  <span>{item.cliente ?? 'Cliente não vinculado'}</span>
                  <span>{item.resumo_curto}</span>
                  <span className={item.tem_prazo ? diario2Styles.prazoOk : diario2Styles.prazoMiss}>
                    {item.prazo ? `${formatDate(item.prazo.data_limite)} · ${item.prazo.status}` : 'Sem prazo'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {isLoading ? (
        <p className={styles.empty}>Carregando publicações...</p>
      ) : !data?.dias.length ? (
        <p className={styles.empty}>Nenhuma publicação importada ainda.</p>
      ) : (
        <div className={diario2Styles.days}>
          {data.dias.map((dia) => (
            <section key={dia.data} className={diario2Styles.dayBlock}>
              <div className={diario2Styles.dayHeader}>
                <span className={diario2Styles.dayTitle}>
                  {dispDoDia(dia) && (
                    <>
                      <span className={diario2Styles.dayDateLabel}>Disp.</span>{' '}
                      {dispDoDia(dia)}
                      <span className={diario2Styles.daySep}>·</span>
                    </>
                  )}
                  <span className={diario2Styles.dayDateLabel}>Pub.</span>{' '}
                  {formatDate(dia.data)}
                </span>
                <span className={diario2Styles.dayCount}>{dia.publicacoes.length} registro(s)</span>
              </div>
              <div className={diario2Styles.publicationList}>
                {dia.publicacoes.map((pub) => (
                  <article key={pub.id} className={`${diario2Styles.card} ${pub.tem_publicacao ? '' : diario2Styles.cardNoPub}`}>
                    {!pub.tem_publicacao ? (
                      <div className={diario2Styles.emptyRow}>Sem publicações neste diário.</div>
                    ) : (
                      <div className={diario2Styles.cardTop}>
                        <code className={diario2Styles.cnj}>{pub.numero_cnj ?? 'sem CNJ'}</code>
                        <span className={diario2Styles.mainText}>{nomeCliente(pub)}</span>
                        <span className={diario2Styles.tribunal}>{pub.tribunal ?? '-'}</span>
                        <span className={diario2Styles.summary}>{pub.resumo_curto}</span>
                        {/* Ocupa a MESMA célula do prazo (o grid tem 6 colunas
                            fixas — um item extra criava uma 7ª e quebrava a
                            linha). Quando é nada a fazer, o chip substitui o
                            rótulo do prazo, que já diria "· nada a fazer". */}
                        {ehNadaAFazer(pub) ? (
                          <span
                            className={diario2Styles.chipNadaAFazer}
                            title={`Tratada: revisada e sem providência a tomar${pub.prazo ? ` · prazo ${formatDate(pub.prazo.data_limite)}` : ''}`}
                          >
                            🚫 Nada a fazer
                          </span>
                        ) : (
                          <span className={pub.prazo ? diario2Styles.prazoOk : diario2Styles.prazoMiss}>{prazoLabel(pub)}</span>
                        )}
                        <div className={diario2Styles.actions}>
                          <button className={diario2Styles.ghostBtn} onClick={() => setExpanded(expanded === pub.id ? null : pub.id)}>
                            {expanded === pub.id ? 'Fechar' : 'Abrir'}
                          </button>
                          <button className={diario2Styles.ghostBtn} disabled={analisar.isPending} onClick={() => analisar.mutate(pub.id)}>
                            IA
                          </button>
                          {!pub.prazo && (
                            <button className={diario2Styles.ghostBtn} onClick={() => abrirPrazo(pub)}>
                              + Prazo
                            </button>
                          )}
                          {ehNadaAFazer(pub) ? (
                            <button
                              className={diario2Styles.ghostBtn}
                              disabled={desfazerNadaAFazer.isPending}
                              title="Reabre a publicação, devolve o prazo para pendente e reativa as tarefas canceladas por este tratamento."
                              onClick={() => {
                                if (confirm(
                                  'Desfazer o "Nada a fazer" desta publicação?\n\n' +
                                  'Ela volta a ficar em aberto, o prazo volta para pendente (em vermelho, se já estiver vencido) ' +
                                  'e as tarefas canceladas por este tratamento voltam para pendente.',
                                )) desfazerNadaAFazer.mutate(pub.id)
                              }}
                            >
                              ↺ Desfazer
                            </button>
                          ) : (
                            <button
                              className={diario2Styles.ghostBtn}
                              disabled={nadaAFazer.isPending}
                              title="Publicação revisada que não exige providência (ex.: sentença favorável sem embargo a opor). Encerra a publicação e cancela as tarefas automáticas dela."
                              onClick={() => {
                                if (confirm(
                                  'Marcar esta publicação como "Nada a fazer"?\n\n' +
                                  'Ela é encerrada aqui e no Diário Oficial, aparece na aba "Nada a fazer" da tela de Prazos, ' +
                                  'e as tarefas criadas automaticamente por causa dela são canceladas.',
                                )) nadaAFazer.mutate(pub.id)
                              }}
                            >
                              🚫 Nada a fazer
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {expanded === pub.id && (
                      <div className={diario2Styles.details}>
                        <div className={diario2Styles.detailGrid}>
                          {pub.detalhes?.data_publicacao && <span><b>Publicação</b>{pub.detalhes.data_publicacao}</span>}
                          {pub.detalhes?.classe && <span><b>Classe</b>{pub.detalhes.classe}</span>}
                          {pub.detalhes?.orgao && <span><b>Órgão</b>{pub.detalhes.orgao}</span>}
                          {pub.detalhes?.relator && <span><b>Relator</b>{pub.detalhes.relator}</span>}
                          {pub.detalhes?.local && <span><b>Local</b>{pub.detalhes.local}</span>}
                          <span><b>Em nome de</b>{pub.publicado_em_nome_de}</span>
                        </div>
                        {pub.detalhes?.partes && pub.detalhes.partes.length > 0 && (
                          <div className={diario2Styles.partes}>
                            {pub.detalhes.partes.map((parte) => <span key={parte}>{parte}</span>)}
                          </div>
                        )}
                        <div className={diario2Styles.muted}>
                          {pub.url_fonte && <> · <a href={pub.url_fonte} target="_blank" rel="noreferrer">fonte</a></>}
                        </div>
                        {pub.prazo && (
                          <div className={diario2Styles.controls} style={{ marginTop: 8 }}>
                            <span className={diario2Styles.prazoOk}>Prazo: {formatDate(pub.prazo.data_limite)}</span>
                            <select
                              className={styles.input}
                              style={{ width: 150 }}
                              value={pub.prazo.status}
                              onChange={(e) => {
                                const novo = e.target.value as StatusPrazoDiario2
                                if (novo === 'nada_a_fazer' && !confirm(
                                  'Marcar como "Nada a fazer"?\n\nA publicação é encerrada e as tarefas automáticas dela são canceladas.',
                                )) return
                                statusPrazo.mutate({ id: pub.id, status: novo })
                              }}
                            >
                              {(Object.keys(STATUS_LABEL) as StatusPrazoDiario2[]).map((s) => (
                                <option key={s} value={s}>{STATUS_LABEL[s]}</option>
                              ))}
                            </select>
                            <button
                              className={diario2Styles.ghostBtn}
                              onClick={() => setEditPrazoPub(editPrazoPub === pub.id ? null : pub.id)}
                            >
                              {editPrazoPub === pub.id ? 'Cancelar edição' : '✎ Alterar prazo'}
                            </button>
                            <a className={diario2Styles.ghostBtn} href={`/prazos?destaque=${pub.prazo.id}`} style={{ textDecoration: 'none' }}>
                              Ver em Prazos
                            </a>
                          </div>
                        )}

                        {editPrazoPub === pub.id && pub.prazo && (
                          <PrazoEditorInline
                            prazo={{
                              id: pub.prazo.id,
                              tipo: pub.prazo.tipo,
                              peca_necessaria: pub.prazo.peca_necessaria ?? null,
                              descricao: pub.prazo.descricao ?? null,
                              data_publicacao: pub.data_publicacao,
                              dias_prazo: pub.prazo.dias_prazo,
                              tipo_contagem: pub.prazo.tipo_contagem,
                              responsavel: pub.despacho_status?.prazo?.responsavel ?? null,
                              status: pub.prazo.status,
                            }}
                            dataPublicacaoFallback={pub.data_publicacao}
                            onCancel={() => setEditPrazoPub(null)}
                            onSaved={() => {
                              setEditPrazoPub(null)
                              setMsg('Prazo atualizado — a alteração já vale na tela de Prazos e no Diário Oficial.')
                            }}
                          />
                        )}

                        <DespachoStatusResumo status={pub.despacho_status} />

                        {prazoPub === pub.id && prazoForm && (
                          <form
                            className={diario2Styles.prazoForm}
                            onSubmit={(e) => {
                              e.preventDefault()
                              const sug = sugestaoDaPeca(catalogoLegal, prazoForm.peca_necessaria)
                              if (sug && divergeDaLei(sug, prazoForm.dias_prazo, prazoForm.tipo_contagem)
                                  && !confirm(textoConfirmacaoDivergencia(sug, prazoForm.dias_prazo, prazoForm.tipo_contagem))) return
                              criarPrazo.mutate({ id: pub.id, payload: prazoForm })
                            }}
                          >
                            <ProcessoCombobox
                              value={prazoForm.processo_id ?? ''}
                              onChange={(id) => setPrazoForm({ ...prazoForm, processo_id: id })}
                              processos={processos}
                              clientes={clientes}
                              onCreateProcesso={criarProcesso}
                            />
                            <select className={styles.input} value={prazoForm.tipo} onChange={(e) => setPrazoForm({ ...prazoForm, tipo: e.target.value })}>
                              {TIPOS.map((tipo) => <option key={tipo} value={tipo}>{tipo}</option>)}
                            </select>
                            <input className={styles.input} type="number" min={1} value={prazoForm.dias_prazo} onChange={(e) => setPrazoForm({ ...prazoForm, dias_prazo: Number(e.target.value) })} />
                            <select className={styles.input} value={prazoForm.tipo_contagem} onChange={(e) => setPrazoForm({ ...prazoForm, tipo_contagem: e.target.value as 'uteis' | 'corridos' })}>
                              <option value="uteis">úteis</option>
                              <option value="corridos">corridos</option>
                            </select>
                            <PecaCombobox
                              value={prazoForm.peca_necessaria ?? ''}
                              onChange={(peca) => {
                                const sug = sugestaoDaPeca(catalogoLegal, peca)
                                setPrazoForm({
                                  ...prazoForm,
                                  peca_necessaria: peca,
                                  ...(sug?.dias != null
                                    ? { dias_prazo: sug.dias, tipo_contagem: (sug.contagem ?? 'uteis') as 'uteis' | 'corridos' }
                                    : {}),
                                })
                              }}
                              baseOptions={PECAS}
                              onApplyDefault={(dias, tipoContagem) =>
                                setPrazoForm((prev) => prev ? { ...prev, dias_prazo: dias, tipo_contagem: tipoContagem } : prev)
                              }
                            />
                            <select className={styles.input} value={prazoForm.responsavel ?? ''} onChange={(e) => setPrazoForm({ ...prazoForm, responsavel: e.target.value })}>
                              <option value="">Resp.</option>
                              {usuarios.filter(u => u.ativo).map((u) => <option key={u.id} value={u.nome}>{u.nome}</option>)}
                              <option value="Terceiros">Terceiros</option>
                            </select>
                            <button className={styles.btnPrimary} disabled={criarPrazo.isPending}>
                              Criar
                            </button>
                            {(() => {
                              const sug = sugestaoDaPeca(catalogoLegal, prazoForm.peca_necessaria)
                              if (!sug) return null
                              const div = divergeDaLei(sug, prazoForm.dias_prazo, prazoForm.tipo_contagem)
                              return (
                                <div style={{
                                  flexBasis: '100%', fontSize: 11, lineHeight: 1.5, padding: '6px 9px',
                                  borderRadius: 6, borderLeft: `3px solid ${div ? '#f59e0b' : '#0d9488'}`,
                                  background: div ? '#fffbeb' : '#ecfdf5', color: div ? '#92400e' : '#065f46',
                                }}>
                                  <strong>
                                    {sug.dias == null
                                      ? `${sug.rotulo}: sem prazo em dias`
                                      : `${sug.rotulo}: ${sug.dias} dia(s) ${sug.contagem === 'corridos' ? 'corridos' : 'úteis'}`}
                                  </strong>{' '}· {sug.fundamento}
                                  {div && <> — <strong>fora do prazo legal</strong>; será pedida confirmação.</>}
                                </div>
                              )
                            })()}
                          </form>
                        )}
                        <div className={diario2Styles.detailsText}>{pub.texto_relevante || pub.texto_completo || pub.texto_resumo || 'Sem texto.'}</div>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
