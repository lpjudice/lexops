import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Settings, AlertTriangle, Search, Star, Sparkles, Monitor, CheckCircle2, Clock } from 'lucide-react'
import { informativoStfApi } from '../api/informativoStf'
import { ramoCor } from '../utils/ramoColor'
import styles from './InformativoStfPage.module.css'

export default function InformativoStfPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [busca, setBusca] = useState('')

  const { data: edicoes = [], isLoading } = useQuery({
    queryKey: ['informativo-stf', 'edicoes'],
    queryFn: () => informativoStfApi.listarEdicoes(20),
  })

  const { data: resultadosBusca = [], isFetching: buscando } = useQuery({
    queryKey: ['informativo-stf', 'busca', busca],
    queryFn: () => informativoStfApi.buscar(busca),
    enabled: busca.trim().length >= 2,
  })

  const { data: config } = useQuery({
    queryKey: ['informativo-stf', 'config'],
    queryFn: () => informativoStfApi.getConfig(),
  })

  const solicitarSyncLocal = useMutation({
    mutationFn: () => informativoStfApi.solicitarSyncLocal(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stf', 'config'] }),
  })

  const reprocessarTudo = useMutation({
    mutationFn: () => informativoStfApi.reprocessarTudo(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stf'] }),
  })

  const mostrandoBusca = busca.trim().length >= 2

  return (
    <div>
      <div className={styles.header}>
        <span className={styles.headerTitle}>Informativo do STF</span>
        <div className={styles.headerActions}>
          <button className={styles.btn} onClick={() => navigate('/informativo-stf/favoritos')}>
            <Star size={14} /> Favoritos
          </button>
          <button className={styles.btn} onClick={() => navigate('/informativo-stf/config')}>
            <Settings size={14} /> Áreas de destaque
          </button>
          <button
            className={styles.btn}
            onClick={() => reprocessarTudo.mutate()}
            disabled={reprocessarTudo.isPending}
            title="Regera o resumo de IA de todos os julgados destacados já baixados, sem buscar edições novas"
          >
            <Sparkles size={14} />
            {reprocessarTudo.isPending ? 'Reprocessando…' : 'Reprocessar tudo'}
          </button>
          <button
            className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={() => solicitarSyncLocal.mutate()}
            disabled={solicitarSyncLocal.isPending}
            title="O site do STF bloqueia o servidor — a sincronização real roda num script no seu computador, que verifica este pedido em até 30 min"
          >
            <Monitor size={14} />
            {solicitarSyncLocal.isPending ? 'Enviando pedido…' : 'Rodar sincronização agora'}
          </button>
        </div>
      </div>

      {solicitarSyncLocal.isSuccess && (
        <div className={styles.syncAviso}>
          <Clock size={13} /> Pedido enviado — seu computador vai buscar em até 30 min (se estiver ligado e com o script rodando).
        </div>
      )}

      {config && (config.sync_local_ultimo_em || config.sync_local_solicitado_em) && (
        <div className={config.sync_local_ultimo_status === 'erro' ? styles.syncErro : styles.syncStatus}>
          {config.sync_local_ultimo_status === 'erro' ? (
            <>
              <AlertTriangle size={13} /> Última sincronização local falhou ({new Date(config.sync_local_ultimo_em!).toLocaleString('pt-BR')}):{' '}
              {config.sync_local_ultima_mensagem}
            </>
          ) : config.sync_local_ultimo_em ? (
            <>
              <CheckCircle2 size={13} /> Última sincronização local: {new Date(config.sync_local_ultimo_em).toLocaleString('pt-BR')}
              {config.sync_local_ultima_mensagem ? ` — ${config.sync_local_ultima_mensagem}` : ''}
            </>
          ) : (
            <>
              <Clock size={13} /> Pedido pendente desde {new Date(config.sync_local_solicitado_em!).toLocaleString('pt-BR')} — aguardando seu computador.
            </>
          )}
        </div>
      )}

      <div className={styles.searchBar}>
        <div className={styles.searchInputWrap}>
          <Search size={15} className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            placeholder="Buscar em todos os informativos…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        {mostrandoBusca && (
          <div className={styles.searchResults}>
            {buscando && <div className={styles.searchResultItem}>Buscando…</div>}
            {!buscando && resultadosBusca.length === 0 && (
              <div className={styles.searchResultItem}>Nenhum resultado para "{busca}".</div>
            )}
            {!buscando &&
              resultadosBusca.map((item) => (
                <div
                  key={item.id}
                  className={styles.searchResultItem}
                  onClick={() => navigate(`/informativo-stf/${item.edicao_id}?item=${item.id}`)}
                >
                  <div className={styles.searchResultTitulo}>{item.titulo}</div>
                  <div className={styles.searchResultTrecho}>
                    [{item.ramo_direito}] {(item.resumo_tema_central || item.destaque_oficial || '').slice(0, 140)}
                  </div>
                </div>
              ))}
          </div>
        )}
        {!mostrandoBusca && <div className={styles.searchHint}>Mostrando os 20 informativos mais recentes abaixo.</div>}
      </div>

      {isLoading && <p className={styles.empty}>Carregando edições…</p>}

      {!isLoading && edicoes.length === 0 && (
        <p className={styles.empty}>
          Nenhuma edição sincronizada ainda. Clique em "Sincronizar agora" para buscar as edições mais recentes.
        </p>
      )}

      <div className={styles.grid}>
        {edicoes.map((e) => (
          <div key={e.id} className={styles.card} onClick={() => navigate(`/informativo-stf/${e.id}`)}>
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

            {e.destaques.length > 0 && (
              <div className={styles.cardDestaquesLista}>
                {e.destaques.map((d) => {
                  const cor = ramoCor(d.ramo_direito)
                  return (
                    <div key={d.id} className={styles.cardDestaqueLinha}>
                      {d.favorito && <Star size={10} className={styles.cardDestaqueFavIcon} fill="currentColor" />}
                      <span className={styles.cardDestaqueRamo} style={{ color: cor.fg }}>●</span>
                      <span className={styles.cardDestaqueTexto}>{d.resumo_tema_central || d.titulo}</span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
