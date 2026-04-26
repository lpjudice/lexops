import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { andamentosApi } from '../api/andamentos'
import type { Andamento, SincronizacaoResult } from '../api/andamentos'
import InstrucoesJusBRModal from './InstrucoesJusBRModal'
import styles from './AndamentosSection.module.css'
import {
  clearStoredJusbrToken,
  formatTokenExpiry,
  loadStoredJusbrToken,
  saveStoredJusbrToken,
} from '../utils/jusbrToken'

interface Props {
  processoId: string
  tribunal?: string | null
  ultimoAndamentoData?: string | null
  ultimoCheck?: string | null
}

type Fonte = 'datajud' | 'jusbr'

function formatDate(d: string | null | undefined): string {
  if (!d) return '—'
  const [y, m, day] = d.split('-')
  return `${day}/${m}/${y}`
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function SyncBanner({ result, ultimoAndamentoPre }: {
  result: SincronizacaoResult
  ultimoAndamentoPre: string | null | undefined
}) {
  const { status, novos_andamentos, mensagem, ultimo_andamento_data } = result
  const dataRef = formatDate(ultimo_andamento_data ?? ultimoAndamentoPre ?? null)
  const temDataRef = !!(ultimo_andamento_data || ultimoAndamentoPre)

  if (status === 'erro') return (
    <div className={`${styles.banner} ${styles.bannerErro}`}>
      <span className={styles.bannerIcon}>⚠</span>
      <span>{mensagem ?? 'Erro desconhecido.'}</span>
    </div>
  )
  if (status === 'nenhum') return (
    <div className={`${styles.banner} ${styles.bannerAviso}`}>
      <span className={styles.bannerIcon}>—</span>
      <span>{mensagem ?? 'Nenhum andamento encontrado.'}</span>
    </div>
  )
  if (novos_andamentos > 0) return (
    <div className={`${styles.banner} ${styles.bannerSucesso}`}>
      <span className={styles.bannerIcon}>✓</span>
      <span>
        {novos_andamentos} novo{novos_andamentos > 1 ? 's' : ''} andamento{novos_andamentos > 1 ? 's' : ''} encontrado{novos_andamentos > 1 ? 's' : ''}.
      </span>
    </div>
  )
  return (
    <div className={`${styles.banner} ${styles.bannerNeutro}`}>
      <span className={styles.bannerIcon}>✓</span>
      <span>{temDataRef ? `Nenhum andamento novo desde ${dataRef}.` : 'Nenhum andamento novo.'}</span>
    </div>
  )
}

export default function AndamentosSection({ processoId, ultimoAndamentoData, ultimoCheck }: Props) {
  const qc = useQueryClient()
  const [fonte, setFonte] = useState<Fonte>('datajud')
  const [offset, setOffset] = useState(0)
  const [jusBRToken, setJusBRToken] = useState(() => loadStoredJusbrToken())
  const [showTokenModal, setShowTokenModal] = useState(false)
  const [ultimoAndamentoPre, setUltimoAndamentoPre] = useState<string | null | undefined>(ultimoAndamentoData)
  const PAGE = 10
  const tokenExpiry = jusBRToken ? formatTokenExpiry(jusBRToken) : null

  const fonteParam = fonte === 'datajud' ? 'datajud' : 'jusbr'

  const { data: andamentos = [], isLoading, isFetching } = useQuery({
    queryKey: ['andamentos', processoId, offset, fonte],
    queryFn: () => andamentosApi.listar(processoId, PAGE, offset, fonteParam),
    staleTime: 30_000,
  })

  const { data: count } = useQuery({
    queryKey: ['andamentos-count', processoId, fonte],
    queryFn: () => andamentosApi.contar(processoId, fonteParam),
    staleTime: 30_000,
  })

  const syncDataJud = useMutation({
    mutationFn: () => andamentosApi.sincronizar(processoId),
    onMutate: () => setUltimoAndamentoPre(ultimoAndamentoData),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['andamentos', processoId] })
      qc.invalidateQueries({ queryKey: ['andamentos-count', processoId] })
      qc.invalidateQueries({ queryKey: ['processos'] })
    },
  })

  const syncJusBR = useMutation({
    mutationFn: (token: string) => andamentosApi.sincronizarJusBR(processoId, token),
    onMutate: () => setUltimoAndamentoPre(ultimoAndamentoData),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['andamentos', processoId] })
      qc.invalidateQueries({ queryKey: ['andamentos-count', processoId] })
      qc.invalidateQueries({ queryKey: ['processos'] })
    },
  })

  const marcarLidos = useMutation({
    mutationFn: () => andamentosApi.marcarLidos(processoId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['andamentos', processoId] })
      qc.invalidateQueries({ queryKey: ['andamentos-count', processoId] })
      qc.invalidateQueries({ queryKey: ['processos'] })
    },
  })

  const isSyncing = syncDataJud.isPending || syncJusBR.isPending
  const syncData = fonte === 'datajud' ? syncDataJud.data : syncJusBR.data
  const temMais = (count?.total ?? 0) > offset + PAGE

  function handleFonte(f: Fonte) {
    setFonte(f)
    setOffset(0)
    syncDataJud.reset()
    syncJusBR.reset()
  }

  function handleSync() {
    if (fonte === 'datajud') {
      syncDataJud.mutate()
    } else {
      if (!jusBRToken) {
        setShowTokenModal(true)
      } else {
        syncJusBR.mutate(jusBRToken)
      }
    }
  }

  function handleToken(token: string) {
    setJusBRToken(token)
    saveStoredJusbrToken(token)
    syncJusBR.mutate(token)
  }

  return (
    <div className={styles.wrap}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <span className={styles.title}>Andamentos</span>
          {ultimoCheck && !isSyncing && !syncData && (
            <span className={styles.ultimoCheck}>última sync {formatDateTime(ultimoCheck)}</span>
          )}
        </div>

        <div className={styles.headerActions}>
          {/* Source toggle */}
          <div className={styles.fonteToggle}>
            <button
              className={`${styles.fonteBtn} ${fonte === 'datajud' ? styles.fonteBtnActive : ''}`}
              onClick={() => handleFonte('datajud')}
              title="DataJud — sincronização automática via CNJ (sem login)"
            >
              DataJud
            </button>
            <button
              className={`${styles.fonteBtn} ${fonte === 'jusbr' ? styles.fonteBtnActive : ''}`}
              onClick={() => handleFonte('jusbr')}
              title="jus.br — dados do portal autenticado (requer token)"
            >
              jus.br
            </button>
          </div>

          {(count?.nao_lidos ?? 0) > 0 && !isSyncing && (
            <button className={styles.btnLer} onClick={() => marcarLidos.mutate()} disabled={marcarLidos.isPending}>
              Marcar lidos
            </button>
          )}

          {/* Sync / token button */}
          {fonte === 'jusbr' && jusBRToken && (
            <button
              className={styles.btnTokenReset}
              onClick={() => setShowTokenModal(true)}
              title="Token configurado — clique para renovar"
            >
              🔑
            </button>
          )}
          <button
            className={styles.btnSync}
            onClick={handleSync}
            disabled={isSyncing}
          >
            {isSyncing ? (
              <span className={styles.syncingLabel}><span className={styles.spinner} /> Buscando…</span>
            ) : fonte === 'jusbr' && !jusBRToken ? (
              '🔑 Configurar token'
            ) : (
              '⟳ Sincronizar'
            )}
          </button>
        </div>
      </div>

      {/* jus.br token info bar */}
      {fonte === 'jusbr' && !jusBRToken && !isSyncing && !syncData && (
        <div className={styles.jusBRInfo}>
          <span>O modo <strong>jus.br</strong> requer um token de sessão obtido no portal. Clique em <strong>"🔑 Configurar token"</strong> para começar.</span>
        </div>
      )}
      {fonte === 'jusbr' && jusBRToken && !isSyncing && !syncData && (
        <div className={styles.jusBRInfo}>
          <span>
            Token do <strong>jus.br</strong> carregado automaticamente neste navegador.
            {tokenExpiry ? ` Expira em ${tokenExpiry}.` : ''}
          </span>
          <button
            className={styles.btnLer}
            onClick={() => {
              clearStoredJusbrToken()
              setJusBRToken('')
            }}
          >
            Limpar token
          </button>
        </div>
      )}

      {/* Progress bar */}
      {isSyncing && <div className={styles.progressBar}><div className={styles.progressFill} /></div>}

      {/* Result banner */}
      {!isSyncing && syncData && (
        <SyncBanner result={syncData} ultimoAndamentoPre={ultimoAndamentoPre} />
      )}

      {/* List */}
      {isLoading ? (
        <p className={styles.empty}>Carregando…</p>
      ) : andamentos.length === 0 ? (
        <div className={styles.emptyState}>
          {fonte === 'datajud' ? (
            ultimoCheck ? (
              <>
                <span className={styles.emptyIcon}>📭</span>
                <p className={styles.emptyMsg}>
                  {ultimoAndamentoData
                    ? `Nenhum andamento novo desde ${formatDate(ultimoAndamentoData)}.`
                    : 'Nenhum andamento encontrado no DataJud.'}
                </p>
                <p className={styles.emptyHint}>Última verificação: {formatDateTime(ultimoCheck)}</p>
              </>
            ) : (
              <>
                <span className={styles.emptyIcon}>🔍</span>
                <p className={styles.emptyMsg}>Nenhum andamento do DataJud ainda.</p>
                <p className={styles.emptyHint}>Clique em <strong>⟳ Sincronizar</strong> para buscar.</p>
              </>
            )
          ) : (
            <>
              <span className={styles.emptyIcon}>🔍</span>
              <p className={styles.emptyMsg}>Nenhum andamento do jus.br ainda.</p>
              <p className={styles.emptyHint}>
                {jusBRToken
                  ? 'Clique em ⟳ Sincronizar para buscar no portal.'
                  : 'Configure o token para sincronizar com o jus.br.'}
              </p>
            </>
          )}
        </div>
      ) : (
        <>
          <div className={styles.lista}>
            {andamentos.map((a) => <AndamentoCard key={a.id} andamento={a} />)}
          </div>
          <div className={styles.paginacao}>
            {offset > 0 && (
              <button className={styles.btnPage} onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Anteriores</button>
            )}
            <span className={styles.pageInfo}>
              {offset + 1}–{Math.min(offset + PAGE, count?.total ?? andamentos.length)} de {count?.total ?? '?'}
            </span>
            {temMais && (
              <button className={styles.btnPage} onClick={() => setOffset(offset + PAGE)} disabled={isFetching}>Ver mais →</button>
            )}
          </div>
        </>
      )}

      {/* Token modal */}
      {showTokenModal && (
        <InstrucoesJusBRModal
          onClose={() => setShowTokenModal(false)}
          onToken={handleToken}
          initialToken={jusBRToken}
        />
      )}
    </div>
  )
}

function AndamentoCard({ andamento: a }: { andamento: Andamento }) {
  return (
    <div className={`${styles.card} ${!a.lido ? styles.cardNaoLido : ''}`}>
      <div className={styles.cardMeta}>
        <span className={styles.data}>{formatDate(a.data_andamento)}</span>
        {a.grau && <span className={styles.grauBadge}>{a.grau}</span>}
        {a.tipo && <span className={styles.tipo}>{a.tipo}</span>}
        {!a.lido && <span className={styles.novoBadge}>Novo</span>}
      </div>
      <p className={styles.descricao}>{a.descricao}</p>
    </div>
  )
}
