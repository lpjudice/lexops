import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Settings, AlertTriangle } from 'lucide-react'
import { informativoStjApi } from '../api/informativoStj'
import styles from './InformativoStjPage.module.css'

export default function InformativoStjPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: edicoes = [], isLoading } = useQuery({
    queryKey: ['informativo-stj', 'edicoes'],
    queryFn: () => informativoStjApi.listarEdicoes(),
  })

  const sync = useMutation({
    mutationFn: () => informativoStjApi.sincronizarAgora(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stj'] }),
  })

  return (
    <div>
      <div className={styles.header}>
        <span className={styles.headerTitle}>Informativo de Jurisprudência — STJ</span>
        <div className={styles.headerActions}>
          <button className={styles.btn} onClick={() => navigate('/informativo-stj/config')}>
            <Settings size={14} /> Áreas de destaque
          </button>
          <button
            className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={() => sync.mutate()}
            disabled={sync.isPending}
          >
            <RefreshCw size={14} className={sync.isPending ? 'spin' : ''} />
            {sync.isPending ? 'Sincronizando…' : 'Sincronizar agora'}
          </button>
        </div>
      </div>

      {isLoading && <p className={styles.empty}>Carregando edições…</p>}

      {!isLoading && edicoes.length === 0 && (
        <p className={styles.empty}>
          Nenhuma edição sincronizada ainda. Clique em "Sincronizar agora" para buscar as edições mais recentes.
        </p>
      )}

      <div className={styles.grid}>
        {edicoes.map((e) => (
          <div key={e.id} className={styles.card} onClick={() => navigate(`/informativo-stj/${e.id}`)}>
            <div className={styles.cardTop}>
              <span className={styles.cardNumero}>
                Informativo nº {e.numero}
                {e.tipo === 'extraordinaria' && ' · Extraordinário'}
              </span>
              <span className={styles.cardData}>
                {e.data_publicacao ? new Date(e.data_publicacao + 'T00:00:00').toLocaleDateString('pt-BR') : '—'}
              </span>
            </div>
            <div className={styles.cardMeta}>
              {e.total_destacados > 0 && (
                <span className={`${styles.badge} ${styles.badgeDestacado}`}>
                  {e.total_destacados} destacado{e.total_destacados > 1 ? 's' : ''}
                </span>
              )}
              <span className={`${styles.badge} ${styles.badgeNeutro}`}>{e.total_itens} julgados</span>
              {e.status_scraping === 'erro_parsing' && (
                <span className={`${styles.badge} ${styles.badgeErro}`}>
                  <AlertTriangle size={11} /> Erro ao processar
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
