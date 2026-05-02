import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { DollarSign, Briefcase, AlertCircle, Users, Plus } from 'lucide-react'
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

function diasRestantes(dataLimite: string): number {
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const limite = new Date(dataLimite + 'T00:00:00')
  return Math.round((limite.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24))
}

function DiasBadge({ dias }: { dias: number }) {
  let cls = styles.diasOk
  let label = `${dias}d`
  if (dias < 0) {
    cls = styles.diasVencido
    label = `${Math.abs(dias)}d atraso`
  } else if (dias <= 3) {
    cls = styles.diasCritico
    label = `${dias}d`
  } else if (dias <= 7) {
    cls = styles.diasAlerta
    label = `${dias}d`
  }
  return <span className={`${styles.diasBadge} ${cls}`}>{label}</span>
}

function parseAnalise(json: string | undefined): AnaliseIA | null {
  if (!json) return null
  try { return JSON.parse(json) as AnaliseIA } catch { return null }
}

export default function DashboardPage() {
  const navigate = useNavigate()

  const { data: resumo } = useQuery({
    queryKey: ['financeiro-resumo'],
    queryFn: () => financeiroApi.resumo(),
  })

  const { data: prazos = [] } = useQuery({
    queryKey: ['prazos'],
    queryFn: () => prazosApi.listar(),
  })

  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const { data: contratos = [] } = useQuery({
    queryKey: ['contratos'],
    queryFn: () => contratosApi.listar(),
  })

  const { data: tarefas = [] } = useQuery({
    queryKey: ['tarefas-dashboard'],
    queryFn: () => tarefasApi.listar({ status: 'pendente' }),
  })

  const { data: publicacoes = [] } = useQuery({
    queryKey: ['publicacoes-dashboard'],
    queryFn: () => diarioApi.listar({ lida: false }),
  })

  // ── KPI calculations ──────────────────────────────────────────────────
  const totalPendente = resumo?.total_pendente ?? 0
  const totalContratado = resumo?.total_contratado ?? 0

  const processosAtivos = processos.filter(
    (p) => p.status !== 'encerrado' && p.status !== 'arquivado'
  ).length

  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const em7dias = new Date(hoje)
  em7dias.setDate(hoje.getDate() + 7)

  const prazosUrgentes = prazos.filter((p) => {
    if (p.status !== 'pendente' || !p.data_limite) return false
    const limite = new Date(p.data_limite + 'T00:00:00')
    return limite >= hoje && limite <= em7dias
  }).length

  const prazosVencidos = prazos.filter((p) => {
    if (p.status !== 'pendente' || !p.data_limite) return false
    const limite = new Date(p.data_limite + 'T00:00:00')
    return limite < hoje
  }).length

  const totalClientes = clientes.length

  // ── Prazos pendentes (top 6 closest) ─────────────────────────────────
  const recentPrazos = useMemo(() =>
    [...prazos]
      .filter((p) => p.status === 'pendente' && p.data_limite)
      .sort((a, b) => new Date(a.data_limite!).getTime() - new Date(b.data_limite!).getTime())
      .slice(0, 6),
    [prazos]
  )

  // ── Lookup helpers ────────────────────────────────────────────────────
  const processoNro = (pid: string | undefined | null) => {
    if (!pid) return '—'
    const p = processos.find((x) => x.id === pid)
    if (!p?.numero_cnj) return pid.slice(0, 8) + '…'
    const n = p.numero_cnj
    return n.length > 22 ? n.slice(0, 21) + '…' : n
  }

  const clienteNome = (id: string | null | undefined) =>
    id ? (clientes.find((c) => c.id === id)?.nome ?? '—') : '—'

  // ── Próximas 3 tarefas ────────────────────────────────────────────────
  const proximasTarefas = useMemo(() =>
    [...tarefas]
      .filter((t) => t.data_limite && !t.acesso_restrito && t.status !== 'concluido' && t.status !== 'cancelado')
      .sort((a, b) => new Date(a.data_limite!).getTime() - new Date(b.data_limite!).getTime())
      .slice(0, 3),
    [tarefas]
  )

  // ── Processos com andamentos novos ────────────────────────────────────
  const processosComAndamento = useMemo(() =>
    [...processos]
      .filter((p) => p.andamentos_nao_lidos && p.andamentos_nao_lidos > 0)
      .sort((a, b) => {
        const da = a.ultimo_andamento_data ? new Date(a.ultimo_andamento_data).getTime() : 0
        const db2 = b.ultimo_andamento_data ? new Date(b.ultimo_andamento_data).getTime() : 0
        return db2 - da
      })
      .slice(0, 5),
    [processos]
  )

  // ── Publicações do dia ────────────────────────────────────────────────
  const hojeStr = new Date().toISOString().slice(0, 10)
  const publicacoesHoje = useMemo(() =>
    [...publicacoes]
      .filter((p) =>
        (p.data_publicacao && p.data_publicacao.slice(0, 10) === hojeStr) ||
        p.created_at.slice(0, 10) === hojeStr
      )
      .slice(0, 5),
    [publicacoes, hojeStr]
  )

  // ── Contratos by status ───────────────────────────────────────────────
  const contratosByStatus = contratos.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1
    return acc
  }, {})

  const STATUS_LABELS: Record<string, string> = {
    rascunho: 'Rascunho',
    aguardando_assinatura: 'Aguard. assinatura',
    parcialmente_assinado: 'Parcialmente assinado',
    assinado: 'Assinado',
    cancelado: 'Cancelado',
  }

  const STATUS_COLORS: Record<string, string> = {
    rascunho: '#9ca3af',
    aguardando_assinatura: '#f59e0b',
    parcialmente_assinado: '#3b82f6',
    assinado: '#22c55e',
    cancelado: '#ef4444',
  }

  return (
    <div className={styles.page}>
      {/* ── KPI Cards ──────────────────────────────────────────────────── */}
      <div className={styles.kpiRow}>
        <div className={styles.kpiCard}>
          <div className={styles.kpiIcon} style={{ background: 'rgba(0,176,144,0.1)', color: 'var(--teal)' }}>
            <DollarSign size={20} />
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiLabel}>Honorários a Receber</span>
            <span className={styles.kpiValue}>{formatCurrency(totalPendente)}</span>
            <span className={styles.kpiSub}>Total contratado: {formatCurrency(totalContratado)}</span>
          </div>
          <div className={styles.kpiAccent} style={{ background: 'var(--teal)' }} />
        </div>

        <div className={styles.kpiCard}>
          <div className={styles.kpiIcon} style={{ background: 'rgba(59,130,246,0.1)', color: '#3b82f6' }}>
            <Briefcase size={20} />
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiLabel}>Processos Ativos</span>
            <span className={styles.kpiValue}>{processosAtivos}</span>
            <span className={styles.kpiSub}>{processos.length} total cadastrados</span>
          </div>
          <div className={styles.kpiAccent} style={{ background: '#3b82f6' }} />
        </div>

        <div className={styles.kpiCard}>
          <div
            className={styles.kpiIcon}
            style={{
              background: prazosUrgentes + prazosVencidos > 0 ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
              color: prazosUrgentes + prazosVencidos > 0 ? '#ef4444' : '#22c55e',
            }}
          >
            <AlertCircle size={20} />
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiLabel}>Prazos Urgentes</span>
            <span
              className={styles.kpiValue}
              style={{ color: prazosUrgentes + prazosVencidos > 0 ? '#ef4444' : 'inherit' }}
            >
              {prazosUrgentes}
            </span>
            <span className={styles.kpiSub}>
              {prazosVencidos > 0 ? `${prazosVencidos} vencido(s)` : 'próximos 7 dias'}
            </span>
          </div>
          <div
            className={styles.kpiAccent}
            style={{ background: prazosUrgentes + prazosVencidos > 0 ? '#ef4444' : '#22c55e' }}
          />
        </div>

        <div className={styles.kpiCard}>
          <div className={styles.kpiIcon} style={{ background: 'rgba(168,85,247,0.1)', color: '#a855f7' }}>
            <Users size={20} />
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiLabel}>Clientes</span>
            <span className={styles.kpiValue}>{totalClientes}</span>
            <span className={styles.kpiSub}>cadastrados no sistema</span>
          </div>
          <div className={styles.kpiAccent} style={{ background: '#a855f7' }} />
        </div>
      </div>

      {/* ── Row 1: Prazos + Tarefas + Andamentos ───────────────────────── */}
      <div className={styles.gridThree}>

        {/* Prazos Pendentes */}
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Prazos Pendentes</span>
            <button className={styles.panelLink} onClick={() => navigate('/prazos')}>Ver todos</button>
          </div>
          {recentPrazos.length === 0 ? (
            <div className={styles.panelEmpty}>Nenhum prazo pendente</div>
          ) : (
            <table className={styles.prazoTable}>
              <thead>
                <tr>
                  <th>Processo</th>
                  <th>Tipo</th>
                  <th>Data Limite</th>
                  <th>Restante</th>
                </tr>
              </thead>
              <tbody>
                {recentPrazos.map((prazo) => {
                  const dias = diasRestantes(prazo.data_limite!)
                  return (
                    <tr key={prazo.id}>
                      <td className={styles.tdProcesso}>{processoNro(prazo.processo_id)}</td>
                      <td><span className={styles.tipoBadge}>{prazo.tipo}</span></td>
                      <td className={styles.tdData}>
                        {new Date(prazo.data_limite! + 'T00:00:00').toLocaleDateString('pt-BR')}
                      </td>
                      <td><DiasBadge dias={dias} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
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
              {proximasTarefas.map((t) => {
                const dias = diasRestantes(t.data_limite!)
                return (
                  <div key={t.id} className={styles.tarefaItem}>
                    <div className={styles.tarefaInfo}>
                      <div className={styles.tarefaTitulo}>{t.titulo}</div>
                      <div className={styles.tarefaMeta}>
                        {clienteNome(t.cliente_id) !== '—' && (
                          <span className={styles.tarefaCliente}>{clienteNome(t.cliente_id)}</span>
                        )}
                        {t.responsavel && (
                          <span className={styles.tarefaResp}>→ {t.responsavel}</span>
                        )}
                      </div>
                    </div>
                    <DiasBadge dias={dias} />
                  </div>
                )
              })}
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
                <div
                  key={p.id}
                  className={styles.andamentoItem}
                  onClick={() => navigate(`/processos/${p.id}`)}
                >
                  <div className={styles.andamentoTop}>
                    <span className={styles.andamentoCNJ}>{p.numero_cnj}</span>
                    <span className={styles.andamentoBadge}>{p.andamentos_nao_lidos} novo{(p.andamentos_nao_lidos ?? 0) > 1 ? 's' : ''}</span>
                  </div>
                  {p.ultimo_andamento_desc && (
                    <div className={styles.andamentoDesc}>{p.ultimo_andamento_desc}</div>
                  )}
                  {p.ultimo_andamento_data && (
                    <div className={styles.andamentoData}>
                      {new Date(p.ultimo_andamento_data + 'T12:00:00').toLocaleDateString('pt-BR')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Row 2: Publicações do dia + Contratos + Ações rápidas ──────── */}
      <div className={styles.gridTwo}>

        {/* Publicações do Dia */}
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Publicações de Hoje</span>
            <button className={styles.panelLink} onClick={() => navigate('/diario')}>Ver diário</button>
          </div>
          {publicacoesHoje.length === 0 ? (
            <div className={styles.panelEmpty}>Nenhuma publicação hoje</div>
          ) : (
            <div className={styles.pubList}>
              {publicacoesHoje.map((pub) => {
                const ia = parseAnalise(pub.analise_ia)
                return (
                  <div key={pub.id} className={styles.pubItem}>
                    <div className={styles.pubTop}>
                      <div className={styles.pubMeta}>
                        {pub.numero_cnj && (
                          <span className={styles.pubCNJ}>{pub.numero_cnj}</span>
                        )}
                        {pub.cliente_nome_pub && (
                          <span className={styles.pubCliente}>{pub.cliente_nome_pub}</span>
                        )}
                        {pub.tipo_ato && (
                          <span className={styles.tipoBadge}>{pub.tipo_ato}</span>
                        )}
                        {pub.tribunal && (
                          <span className={styles.pubTribunal}>{pub.tribunal}</span>
                        )}
                      </div>
                    </div>
                    {ia && (
                      <div className={styles.pubIA}>
                        {ia.requer_resposta && ia.peca_necessaria && (
                          <span className={styles.pubPeca}>📋 {ia.peca_necessaria}
                            {ia.dias_prazo ? ` — ${ia.dias_prazo}d` : ''}
                          </span>
                        )}
                        {ia.resumo && (
                          <p className={styles.pubResumo}>{ia.resumo}</p>
                        )}
                      </div>
                    )}
                    {!ia && pub.texto_resumo && (
                      <p className={styles.pubResumo}>{pub.texto_resumo.slice(0, 120)}…</p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Right side: Contratos + Quick Actions */}
        <div className={styles.rightCol}>
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
                      <div
                        className={styles.contratoBarFill}
                        style={{
                          width: `${Math.round((count / contratos.length) * 100)}%`,
                          background: STATUS_COLORS[s] ?? '#9ca3af',
                        }}
                      />
                    </div>
                    <span className={styles.contratoLabel}>{STATUS_LABELS[s] ?? s}</span>
                    <span className={styles.contratoCount}>{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span className={styles.panelTitle}>Ações Rápidas</span>
            </div>
            <div className={styles.quickActions}>
              <button className={styles.quickBtn} onClick={() => navigate('/clientes')}>
                <Plus size={14} />Novo Cliente
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/prazos')}>
                <Plus size={14} />Novo Prazo
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/contratos')}>
                <Plus size={14} />Novo Contrato
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/processos')}>
                <Plus size={14} />Novo Processo
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
