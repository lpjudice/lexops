import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { diario2Api } from '../api/diario2'
import type { Diario2Publicacao, Diario2Dia, Diario2PrazoCreate, StatusPrazoDiario2 } from '../api/diario2'
import { processosApi } from '../api/processos'
import type { EstadoProcesso } from '../api/processos'
import { clientesApi } from '../api/clientes'
import { usuariosApi } from '../api/usuarios'
import DespachoStatusResumo from '../components/DespachoStatusResumo'
import ProcessoCombobox from '../components/ProcessoCombobox'
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

function prazoLabel(pub: Diario2Publicacao) {
  if (!pub.tem_publicacao) return 'Sem publicação'
  if (!pub.prazo) return 'Sem prazo'
  const status = pub.prazo.status === 'cumprido' ? 'cumprido' : pub.prazo.status
  return `${formatDate(pub.prazo.data_limite)} · ${status}`
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
  const [msg, setMsg] = useState('')

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

  const criarProcesso = async (data: { numero_cnj: string; cliente_id: string; estado: EstadoProcesso }): Promise<string> => {
    const p = await processosApi.criar(data)
    qc.invalidateQueries({ queryKey: ['processos'] })
    return p.id
  }

  const abrirPrazo = (pub: Diario2Publicacao) => {
    setPrazoPub(pub.id)
    setPrazoForm(defaultPrazo(pub))
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
                        <span className={pub.prazo ? diario2Styles.prazoOk : diario2Styles.prazoMiss}>{prazoLabel(pub)}</span>
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
                            <select className={styles.input} style={{ width: 150 }} value={pub.prazo.status} onChange={(e) => statusPrazo.mutate({ id: pub.id, status: e.target.value as StatusPrazoDiario2 })}>
                              <option value="pendente">pendente</option>
                              <option value="cumprido">cumprido</option>
                              <option value="perdido">perdido</option>
                            </select>
                          </div>
                        )}
                        <DespachoStatusResumo status={pub.despacho_status} />

                        {prazoPub === pub.id && prazoForm && (
                          <form
                            className={diario2Styles.prazoForm}
                            onSubmit={(e) => {
                              e.preventDefault()
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
                              onChange={(peca) => setPrazoForm({ ...prazoForm, peca_necessaria: peca })}
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
