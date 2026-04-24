import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { DollarSign, Briefcase, AlertCircle, Users, Plus } from 'lucide-react'
import { financeiroApi } from '../api/financeiro'
import { prazosApi } from '../api/prazos'
import { processosApi } from '../api/processos'
import { clientesApi } from '../api/clientes'
import { contratosApi } from '../api/contratos'
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

  // KPI calculations
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

  // Recent prazos: pending, ordered by data_limite asc, first 6
  const recentPrazos = [...prazos]
    .filter((p) => p.status === 'pendente' && p.data_limite)
    .sort((a, b) => new Date(a.data_limite!).getTime() - new Date(b.data_limite!).getTime())
    .slice(0, 6)

  // Contratos by status
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
      {/* KPI Cards */}
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

      {/* Bottom grid */}
      <div className={styles.grid}>
        {/* Recent Prazos */}
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Prazos Pendentes</span>
            <button className={styles.panelLink} onClick={() => navigate('/prazos')}>
              Ver todos
            </button>
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
                      <td className={styles.tdProcesso}>{prazo.processo_id.slice(0, 8)}…</td>
                      <td>
                        <span className={styles.tipoBadge}>{prazo.tipo}</span>
                      </td>
                      <td className={styles.tdData}>
                        {new Date(prazo.data_limite! + 'T00:00:00').toLocaleDateString('pt-BR')}
                      </td>
                      <td>
                        <DiasBadge dias={dias} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Right column */}
        <div className={styles.rightCol}>
          {/* Contratos status */}
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span className={styles.panelTitle}>Contratos</span>
              <button className={styles.panelLink} onClick={() => navigate('/contratos')}>
                Ver todos
              </button>
            </div>
            {contratos.length === 0 ? (
              <div className={styles.panelEmpty}>Nenhum contrato</div>
            ) : (
              <div className={styles.contratosList}>
                {Object.entries(contratosByStatus).map(([status, count]) => (
                  <div key={status} className={styles.contratoItem}>
                    <div className={styles.contratoBar}>
                      <div
                        className={styles.contratoBarFill}
                        style={{
                          width: `${Math.round((count / contratos.length) * 100)}%`,
                          background: STATUS_COLORS[status] ?? '#9ca3af',
                        }}
                      />
                    </div>
                    <span className={styles.contratoLabel}>{STATUS_LABELS[status] ?? status}</span>
                    <span className={styles.contratoCount}>{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick actions */}
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span className={styles.panelTitle}>Ações Rápidas</span>
            </div>
            <div className={styles.quickActions}>
              <button className={styles.quickBtn} onClick={() => navigate('/clientes')}>
                <Plus size={14} />
                Novo Cliente
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/prazos')}>
                <Plus size={14} />
                Novo Prazo
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/contratos')}>
                <Plus size={14} />
                Novo Contrato
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/processos')}>
                <Plus size={14} />
                Novo Processo
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
