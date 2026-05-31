import { useMemo, useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { DollarSign, Briefcase, AlertCircle, Users, Plus, Eye, EyeOff } from 'lucide-react'
import { financeiroApi } from '../api/financeiro'
import { prazosApi } from '../api/prazos'
import { processosApi } from '../api/processos'
import { clientesApi } from '../api/clientes'
import { contratosApi } from '../api/contratos'
import { tarefasApi } from '../api/tarefas'
import { diarioApi } from '../api/diario'
import type { AnaliseIA } from '../api/diario'
import styles from './DashboardPage.module.css'

function formatCurrency(value: number) {
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function formatDate(d: string) {
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

function diasRestantes(dataLimite: string): number {
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const limite = new Date(dataLimite + 'T00:00:00')
  return Math.round((limite.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24))
}

function DiasBadge({ dias }: { dias: number }) {
  let cls = styles.diasOk
  let label = `${dias}d`
  if (dias < 0) { cls = styles.diasVencido; label = `${Math.abs(dias)}d atraso` }
  else if (dias <= 3) { cls = styles.diasCritico; label = `${dias}d` }
  else if (dias <= 7) { cls = styles.diasAlerta; label = `${dias}d` }
  return <span className={`${styles.diasBadge} ${cls}`}>{label}</span>
}

function parseAnalise(json: string | undefined): AnaliseIA | null {
  if (!json) return null
  try { return JSON.parse(json) as AnaliseIA } catch { return null }
}

const PREF_KEY = 'dash_kpi_prefs'
type KpiPrefs = { honorarios: boolean; processos: boolean; clientes: boolean }
function loadPrefs(): KpiPrefs {
  try { return JSON.parse(localStorage.getItem(PREF_KEY) ?? '{}') } catch { return {} as KpiPrefs }
}
function savePrefs(p: KpiPrefs) { localStorage.setItem(PREF_KEY, JSON.stringify(p)) }

export default function DashboardPage() {
  const navigate = useNavigate()

  // KPI visibility prefs (default hidden)
  const [kpiVis, setKpiVis] = useState<KpiPrefs>({ honorarios: false, processos: false, clientes: false })
  useEffect(() => {
    const { honorarios = false, processos = false, clientes = false } = loadPrefs()
    setKpiVis({ honorarios, processos, clientes })
  }, [])
  function toggleKpi(key: keyof KpiPrefs) {
    setKpiVis((prev) => { const next = { ...prev, [key]: !prev[key] }; savePrefs(next); return next })
  }

  const { data: resumo } = useQuery({ queryKey: ['financeiro-resumo'], queryFn: () => financeiroApi.resumo() })
  const { data: prazos = [] } = useQuery({ queryKey: ['prazos'], queryFn: () => prazosApi.listar() })
  const { data: processos = [] } = useQuery({ queryKey: ['processos'], queryFn: () => processosApi.listar() })
  const { data: clientes = [] } = useQuery({ queryKey: ['clientes'], queryFn: () => clientesApi.listar() })
  const { data: contratos = [] } = useQuery({ queryKey: ['contratos'], queryFn: () => contratosApi.listar() })
  const { data: tarefas = [] } = useQuery({ queryKey: ['tarefas-dashboard'], queryFn: () => tarefasApi.listar({ status: 'pendente' }) })
  const { data: publicacoes = [] } = useQuery({ queryKey: ['publicacoes-dashboard'], queryFn: () => diarioApi.listar({ lida: false }) })

  // ── KPI ──────────────────────────────────────────────────────────────
  const totalPendente = resumo?.total_pendente ?? 0
  const totalContratado = resumo?.total_contratado ?? 0
  const processosAtivos = processos.filter(p => p.status !== 'encerrado' && p.status !== 'arquivado').length
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0)
  const em7dias = new Date(hoje); em7dias.setDate(hoje.getDate() + 7)
  const prazosUrgentes = prazos.filter(p => {
    if (p.status !== 'pendente' || !p.data_limite) return false
    const l = new Date(p.data_limite + 'T00:00:00')
    return l >= hoje && l <= em7dias
  }).length
  const prazosVencidos = prazos.filter(p => {
    if (p.status !== 'pendente' || !p.data_limite) return false
    return new Date(p.data_limite + 'T00:00:00') < hoje
  }).length
  const totalClientes = clientes.length

  // ── Prazos pendentes (top 6 closest) ─────────────────────────────────
  const recentPrazos = useMemo(() =>
    [...prazos].filter(p => p.status === 'pendente' && p.data_limite)
      .sort((a, b) => new Date(a.data_limite!).getTime() - new Date(b.data_limite!).getTime())
      .slice(0, 6),
    [prazos])

  // ── Helpers ───────────────────────────────────────────────────────────
  const processoNro = (pid: string | undefined | null) => {
    if (!pid) return '—'
    const p = processos.find(x => x.id === pid)
    const n = p?.numero_cnj; if (!n) return pid.slice(0, 8) + '…'
    return n.length > 22 ? n.slice(0, 21) + '…' : n
  }
  const clienteNome = (id: string | null | undefined) => id ? (clientes.find(c => c.id === id)?.nome ?? '—') : '—'
  const prazoCliente = (pid: string) => {
    const proc = processos.find(x => x.id === pid)
    if (!proc?.cliente_id) return null
    return clientes.find(c => c.id === proc.cliente_id)?.nome ?? null
  }

  // ── Próximas 3 tarefas ────────────────────────────────────────────────
  const proximasTarefas = useMemo(() =>
    [...tarefas].filter(t => t.data_limite && !t.acesso_restrito && t.status !== 'concluido' && t.status !== 'cancelado')
      .sort((a, b) => new Date(a.data_limite!).getTime() - new Date(b.data_limite!).getTime())
      .slice(0, 3),
    [tarefas])

  // ── Processos com andamentos novos ────────────────────────────────────
  const processosComAndamento = useMemo(() =>
    [...processos].filter(p => p.andamentos_nao_lidos && p.andamentos_nao_lidos > 0)
      .sort((a, b) => {
        const da = a.ultimo_andamento_data ? new Date(a.ultimo_andamento_data).getTime() : 0
        const db2 = b.ultimo_andamento_data ? new Date(b.ultimo_andamento_data).getTime() : 0
        return db2 - da
      }).slice(0, 5),
    [processos])

  // ── Últimas 3 publicações ─────────────────────────────────────────────
  const ultimasPublicacoes = useMemo(() =>
    [...publicacoes]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 3),
    [publicacoes])

  // ── Contratos ─────────────────────────────────────────────────────────
  const contratosByStatus = contratos.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1; return acc
  }, {})
  const STATUS_LABELS: Record<string, string> = { rascunho: 'Rascunho', aguardando_assinatura: 'Aguard. assinatura', parcialmente_assinado: 'Parcialmente assinado', assinado: 'Assinado', cancelado: 'Cancelado' }
  const STATUS_COLORS: Record<string, string> = { rascunho: '#9ca3af', aguardando_assinatura: '#f59e0b', parcialmente_assinado: '#3b82f6', assinado: '#22c55e', cancelado: '#ef4444' }

  return (
    <div className={styles.page}>

      {/* ── Ações Rápidas — barra fina full-width ──────────────────────── */}
      <div className={styles.acoesBar}>
        <span className={styles.acoesBarLabel}>Ações Rápidas</span>
        <button className={styles.quickBtn} onClick={() => navigate('/clientes')}><Plus size={14} />Novo Cliente</button>
        <button className={styles.quickBtn} onClick={() => navigate('/prazos')}><Plus size={14} />Novo Prazo</button>
        <button className={styles.quickBtn} onClick={() => navigate('/contratos')}><Plus size={14} />Novo Contrato</button>
        <button className={styles.quickBtn} onClick={() => navigate('/processos')}><Plus size={14} />Novo Processo</button>
      </div>

      {/* ── Masonry: painéis se encaixam, sem espaço branco irregular ──── */}
      <div className={styles.masonry}>

        {/* Prazos Pendentes — card list */}
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Prazos Pendentes</span>
            <button className={styles.panelLink} onClick={() => navigate('/prazos')}>Ver todos</button>
          </div>
          {recentPrazos.length === 0 ? (
            <div className={styles.panelEmpty}>Nenhum prazo pendente</div>
          ) : (
            <div className={styles.prazoCardList}>
              {recentPrazos.map((prazo) => {
                const dias = diasRestantes(prazo.data_limite!)
                const cliente = prazoCliente(prazo.processo_id)
                return (
                  <div key={prazo.id} className={styles.prazoCardItem}>
                    <div className={styles.prazoCardInfo}>
                      <div className={styles.prazoCardTop}>
                        {cliente && <span className={styles.prazoCardCliente}>{cliente}</span>}
                        <code className={styles.prazoCardCNJ}>{processoNro(prazo.processo_id)}</code>
                      </div>
                      <div className={styles.prazoCardMid}>
                        <span className={styles.tipoBadge}>{prazo.tipo}</span>
                        <span className={styles.prazoCardData}>{formatDate(prazo.data_limite!)}</span>
                      </div>
                      {prazo.descricao && (
                        <div className={styles.prazoCardDesc}>{prazo.descricao}</div>
                      )}
                    </div>
                    <DiasBadge dias={dias} />
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Próximas Tarefas */}
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Próximas Tarefas</span>
            <button className={styles.panelLink} onClick={() => navigate('/tarefas')}>Ver todas</button>
          </div>
          {proximasTarefas.length === 0 ? (
            <div className={styles.panelEmpty}>Nenhuma tarefa com prazo</div>
          ) : (
            <div className={styles.tarefasList}>
              {proximasTarefas.map((t) => (
                <div key={t.id} className={styles.tarefaItem}>
                  <div className={styles.tarefaInfo}>
                    <div className={styles.tarefaTitulo}>{t.titulo}</div>
                    <div className={styles.tarefaMeta}>
                      {clienteNome(t.cliente_id) !== '—' && <span className={styles.tarefaCliente}>{clienteNome(t.cliente_id)}</span>}
                      {t.responsavel && <span className={styles.tarefaResp}>→ {t.responsavel}</span>}
                    </div>
                  </div>
                  <DiasBadge dias={diasRestantes(t.data_limite!)} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Andamentos Recentes */}
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Andamentos Recentes</span>
            <button className={styles.panelLink} onClick={() => navigate('/processos')}>Ver processos</button>
          </div>
          {processosComAndamento.length === 0 ? (
            <div className={styles.panelEmpty}>Nenhum andamento novo</div>
          ) : (
            <div className={styles.andamentosList}>
              {processosComAndamento.map((p) => (
                <div key={p.id} className={styles.andamentoItem} onClick={() => navigate(`/processos/${p.id}`)}>
                  <div className={styles.andamentoTop}>
                    <span className={styles.andamentoCNJ}>{p.numero_cnj}</span>
                    <span className={styles.andamentoBadge}>{p.andamentos_nao_lidos} novo{(p.andamentos_nao_lidos ?? 0) > 1 ? 's' : ''}</span>
                  </div>
                  {p.ultimo_andamento_desc && <div className={styles.andamentoDesc}>{p.ultimo_andamento_desc}</div>}
                  {p.ultimo_andamento_data && <div className={styles.andamentoData}>{formatDate(p.ultimo_andamento_data)}</div>}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Últimas Publicações */}
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Últimas Publicações</span>
            <button className={styles.panelLink} onClick={() => navigate('/diario')}>Ver diário</button>
          </div>
          {ultimasPublicacoes.length === 0 ? (
            <div className={styles.panelEmpty}>Nenhuma publicação recente</div>
          ) : (
            <div className={styles.pubList}>
              {ultimasPublicacoes.map((pub) => {
                const ia = parseAnalise(pub.analise_ia)
                return (
                  <div key={pub.id} className={styles.pubItem}>
                    <div className={styles.pubData}>
                      {pub.data_publicacao ? formatDate(pub.data_publicacao) : new Date(pub.created_at).toLocaleDateString('pt-BR')}
                    </div>
                    <div className={styles.pubMeta}>
                      {pub.numero_cnj && <span className={styles.pubCNJ}>{pub.numero_cnj}</span>}
                      {pub.cliente_nome_pub && <span className={styles.pubCliente}>{pub.cliente_nome_pub}</span>}
                      {pub.tipo_ato && <span className={styles.tipoBadge}>{pub.tipo_ato}</span>}
                      {pub.tribunal && <span className={styles.pubTribunal}>{pub.tribunal}</span>}
                    </div>
                    {ia && (
                      <div className={styles.pubIA}>
                        {ia.requer_resposta && ia.peca_necessaria && (
                          <span className={styles.pubPeca}>📋 {ia.peca_necessaria}{ia.dias_prazo ? ` — ${ia.dias_prazo}d` : ''}</span>
                        )}
                        {ia.resumo && <p className={styles.pubResumo}>{ia.resumo}</p>}
                      </div>
                    )}
                    {!ia && pub.texto_resumo && <p className={styles.pubResumo}>{pub.texto_resumo.slice(0, 120)}…</p>}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Contratos */}
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Contratos</span>
              <button className={styles.panelLink} onClick={() => navigate('/contratos')}>Ver todos</button>
            </div>
            {contratos.length === 0 ? (
              <div className={styles.panelEmpty}>Nenhum contrato</div>
            ) : (
              <div className={styles.contratosList}>
                {Object.entries(contratosByStatus).map(([s, count]) => (
                  <div key={s} className={styles.contratoItem}>
                    <div className={styles.contratoBar}>
                      <div className={styles.contratoBarFill} style={{ width: `${Math.round((count / contratos.length) * 100)}%`, background: STATUS_COLORS[s] ?? '#9ca3af' }} />
                    </div>
                    <span className={styles.contratoLabel}>{STATUS_LABELS[s] ?? s}</span>
                    <span className={styles.contratoCount}>{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

      {/* ── KPI Cards (bottom, with privacy toggles) ─────────────────────── */}
      <div className={styles.kpiRow}>

        {/* Honorários — toggleable */}
        <div className={styles.kpiCard}>
          <button className={styles.kpiEye} onClick={() => toggleKpi('honorarios')} title={kpiVis.honorarios ? 'Ocultar' : 'Mostrar'}>
            {kpiVis.honorarios ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>
          <div className={styles.kpiIcon} style={{ background: 'rgba(0,176,144,0.1)', color: 'var(--teal)' }}>
            <DollarSign size={20} />
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiLabel}>Honorários a Receber</span>
            <span className={styles.kpiValue}>{kpiVis.honorarios ? formatCurrency(totalPendente) : '••••'}</span>
            <span className={styles.kpiSub}>{kpiVis.honorarios ? `Total contratado: ${formatCurrency(totalContratado)}` : 'Clique para revelar'}</span>
          </div>
          <div className={styles.kpiAccent} style={{ background: 'var(--teal)' }} />
        </div>

        {/* Processos Ativos — toggleable */}
        <div className={styles.kpiCard}>
          <button className={styles.kpiEye} onClick={() => toggleKpi('processos')} title={kpiVis.processos ? 'Ocultar' : 'Mostrar'}>
            {kpiVis.processos ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>
          <div className={styles.kpiIcon} style={{ background: 'rgba(59,130,246,0.1)', color: '#3b82f6' }}>
            <Briefcase size={20} />
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiLabel}>Processos Ativos</span>
            <span className={styles.kpiValue}>{kpiVis.processos ? processosAtivos : '••'}</span>
            <span className={styles.kpiSub}>{kpiVis.processos ? `${processos.length} total cadastrados` : 'Clique para revelar'}</span>
          </div>
          <div className={styles.kpiAccent} style={{ background: '#3b82f6' }} />
        </div>

        {/* Prazos Urgentes — always visible */}
        <div className={styles.kpiCard}>
          <div className={styles.kpiIcon} style={{ background: prazosUrgentes + prazosVencidos > 0 ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)', color: prazosUrgentes + prazosVencidos > 0 ? '#ef4444' : '#22c55e' }}>
            <AlertCircle size={20} />
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiLabel}>Prazos Urgentes</span>
            <span className={styles.kpiValue} style={{ color: prazosUrgentes + prazosVencidos > 0 ? '#ef4444' : 'inherit' }}>{prazosUrgentes}</span>
            <span className={styles.kpiSub}>{prazosVencidos > 0 ? `${prazosVencidos} vencido(s)` : 'próximos 7 dias'}</span>
          </div>
          <div className={styles.kpiAccent} style={{ background: prazosUrgentes + prazosVencidos > 0 ? '#ef4444' : '#22c55e' }} />
        </div>

        {/* Clientes — toggleable */}
        <div className={styles.kpiCard}>
          <button className={styles.kpiEye} onClick={() => toggleKpi('clientes')} title={kpiVis.clientes ? 'Ocultar' : 'Mostrar'}>
            {kpiVis.clientes ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>
          <div className={styles.kpiIcon} style={{ background: 'rgba(168,85,247,0.1)', color: '#a855f7' }}>
            <Users size={20} />
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiLabel}>Clientes</span>
            <span className={styles.kpiValue}>{kpiVis.clientes ? totalClientes : '••'}</span>
            <span className={styles.kpiSub}>{kpiVis.clientes ? 'cadastrados no sistema' : 'Clique para revelar'}</span>
          </div>
          <div className={styles.kpiAccent} style={{ background: '#a855f7' }} />
        </div>
      </div>
    </div>
  )
}
