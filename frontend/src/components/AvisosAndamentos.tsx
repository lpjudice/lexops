import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { andamentosApi } from '../api/andamentos'
import styles from '../pages/DashboardPage.module.css'

function formatDate(d: string | null): string {
  if (!d) return '—'
  const parts = d.split('-')
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`
  try {
    return new Date(d).toLocaleDateString('pt-BR')
  } catch {
    return '—'
  }
}

export default function AvisosAndamentos() {
  const qc = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-avisos'],
    queryFn: () => andamentosApi.dashboardAvisos(),
    refetchInterval: 5 * 60 * 1000, // 5 min
  })

  const marcarUm = useMutation({
    mutationFn: (processoId: string) => andamentosApi.marcarLidos(processoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard-avisos'] }),
  })

  const marcarLote = useMutation({
    mutationFn: (payload: { processo_ids?: string[]; all?: boolean }) =>
      andamentosApi.marcarLidosLote(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard-avisos'] }),
  })

  if (isLoading) return null

  const total = data?.total_andamentos ?? 0
  const items = data?.items ?? []

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>
          📨 Andamentos novos {total > 0 && `(${total})`}
        </span>
        {items.length > 0 && (
          <button
            className={styles.panelLink}
            onClick={() => {
              if (confirm(`Marcar todos os ${total} andamentos como lidos?`)) {
                marcarLote.mutate({ all: true })
              }
            }}
            disabled={marcarLote.isPending}
          >
            Marcar todos como lidos
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <div className={styles.panelEmpty}>Nenhum andamento novo</div>
      ) : (
        <div className={styles.prazoCardList}>
          {items.map((item) => (
            <div key={item.processo_id} className={styles.prazoCardItem}>
              <div
                className={styles.prazoCardInfo}
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/processos?cnj=${encodeURIComponent(item.numero_cnj)}`)}
                title="Abrir processo"
              >
                <div className={styles.prazoCardTop}>
                  <span className={styles.prazoCardCliente}>{item.cliente_nome}</span>
                  <code className={styles.prazoCardCNJ}>{item.numero_cnj}</code>
                  <span
                    style={{
                      background: '#fef3c7',
                      color: '#92400e',
                      fontSize: 11,
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: 999,
                    }}
                  >
                    {item.qtd_nao_lidos} novo{item.qtd_nao_lidos > 1 ? 's' : ''}
                  </span>
                  {item.tribunal && (
                    <span style={{ fontSize: 11, color: '#666' }}>{item.tribunal}</span>
                  )}
                  {item.mais_recente && (
                    <span style={{ fontSize: 11, color: '#666' }}>
                      • {formatDate(item.mais_recente)}
                    </span>
                  )}
                </div>
                {item.ultimo_desc && (
                  <div
                    style={{
                      fontSize: 12,
                      color: '#525252',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={item.ultimo_desc}
                  >
                    {item.ultimo_desc}
                  </div>
                )}
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  marcarUm.mutate(item.processo_id)
                }}
                disabled={marcarUm.isPending}
                title="Marcar lido"
                style={{
                  background: 'transparent',
                  border: '1px solid #d4d4d8',
                  borderRadius: 6,
                  padding: '4px 10px',
                  cursor: 'pointer',
                  fontSize: 13,
                  color: '#16a34a',
                }}
              >
                ✓
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
