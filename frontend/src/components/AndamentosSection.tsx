import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { andamentosApi } from '../api/andamentos'
import type { Andamento, JusbrSessionStatus, JusbrSyncJobStatus, SincronizacaoResult } from '../api/andamentos'
import InstrucoesJusBRModal from './InstrucoesJusBRModal'
import ConectarGovBrModal from './ConectarGovBrModal'
import { JUSBR_VERSION } from '../jusbrVersion'
import styles from './AndamentosSection.module.css'
import {
  clearStoredJusbrToken,
  saveStoredJusbrToken,
} from '../utils/jusbrToken'

interface Props {
  processoId: string
  tribunal?: string | null
  ultimoAndamentoData?: string | null
  ultimoCheck?: string | null
  /** Nº de andamentos novos deste lote (sessão) — destaca os N mais recentes. */
  novosLoteCount?: number
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

function formatDetectedHost(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    return new URL(url).host
  } catch {
    return null
  }
}


function extractApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (typeof error.message === 'string' && error.message.trim()) return error.message
  }
  if (error instanceof Error && error.message.trim()) return error.message
  return fallback
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
        {mensagem ? ` ${mensagem}` : ''}
      </span>
    </div>
  )
  return (
    <div className={`${styles.banner} ${styles.bannerNeutro}`}>
      <span className={styles.bannerIcon}>✓</span>
      <span>
        {temDataRef ? `Nenhum andamento novo desde ${dataRef}.` : 'Nenhum andamento novo.'}
        {mensagem ? ` ${mensagem}` : ''}
      </span>
    </div>
  )
}

export default function AndamentosSection({ processoId, ultimoAndamentoData, ultimoCheck, novosLoteCount = 0 }: Props) {
  const qc = useQueryClient()
  const [fonte, setFonte] = useState<Fonte>('jusbr')
  const [offset, setOffset] = useState(0)
  const [showTokenModal, setShowTokenModal] = useState(false)
  const [showPkceModal, setShowPkceModal] = useState(false)
  const [ultimoAndamentoPre, setUltimoAndamentoPre] = useState<string | null | undefined>(ultimoAndamentoData)
  const [jusbrJobId, setJusbrJobId] = useState<string | null>(null)
  const [jusbrJobResult, setJusbrJobResult] = useState<SincronizacaoResult | null>(null)
  const [jusbrJobError, setJusbrJobError] = useState<string | null>(null)
  const PAGE = 10

  const fonteParam = fonte === 'datajud' ? 'datajud' : 'jusbr'

  const { data: jusbrSession, refetch: refetchJusbrSession } = useQuery<JusbrSessionStatus>({
    queryKey: ['jusbr-session'],
    queryFn: () => andamentosApi.obterSessaoJusBR(),
    staleTime: 30_000,
  })
  const tokenExpiry = jusbrSession?.expires_at ? formatDateTime(jusbrSession.expires_at) : null
  const detectedHost = formatDetectedHost(jusbrSession?.detected_url)

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

  const startJusBR = useMutation({
    mutationFn: () => andamentosApi.iniciarSincronizacaoJusBR(processoId),
    onMutate: () => {
      setUltimoAndamentoPre(ultimoAndamentoData)
      setJusbrJobResult(null)
      setJusbrJobError(null)
    },
    onSuccess: ({ job_id }) => setJusbrJobId(job_id),
  })

  const { data: jusbrJob } = useQuery<JusbrSyncJobStatus>({
    queryKey: ['jusbr-sync-job', jusbrJobId],
    queryFn: () => andamentosApi.statusSincronizacaoJusBR(jusbrJobId!),
    enabled: !!jusbrJobId,
    refetchInterval: jusbrJobId ? 1200 : false,
  })

  useEffect(() => {
    if (!jusbrJob) return
    if (jusbrJob.status === 'concluido') {
      setJusbrJobResult(jusbrJob.result)
      setJusbrJobError(null)
      setJusbrJobId(null)
      qc.invalidateQueries({ queryKey: ['andamentos', processoId] })
      qc.invalidateQueries({ queryKey: ['andamentos-count', processoId] })
      qc.invalidateQueries({ queryKey: ['processos'] })
    }
    if (jusbrJob.status === 'erro') {
      setJusbrJobError(jusbrJob.error || jusbrJob.message || 'Falha ao sincronizar jus.br.')
      setJusbrJobId(null)
    }
  }, [jusbrJob, processoId, qc])

  const marcarLidos = useMutation({
    mutationFn: () => andamentosApi.marcarLidos(processoId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['andamentos', processoId] })
      qc.invalidateQueries({ queryKey: ['andamentos-count', processoId] })
      qc.invalidateQueries({ queryKey: ['processos'] })
    },
  })

  const isJusBRJobRunning = !!jusbrJobId && (!jusbrJob || jusbrJob.status === 'rodando')
  const isSyncing = syncDataJud.isPending || startJusBR.isPending || isJusBRJobRunning
  const syncData = useMemo(() => {
    const data = fonte === 'datajud' ? syncDataJud.data : jusbrJobResult
    if (data) return data
    const error = fonte === 'datajud' ? syncDataJud.error : startJusBR.error
    if (!error && !(fonte === 'jusbr' && jusbrJobError)) return null
    return {
      processo_id: processoId,
      tribunal: null,
      status: 'erro' as const,
      novos_andamentos: 0,
      mensagem: fonte === 'jusbr' && jusbrJobError
        ? jusbrJobError
        : extractApiErrorMessage(error, 'Falha ao sincronizar andamentos.'),
      ultimo_andamento_data: ultimoAndamentoPre ?? null,
    }
  }, [fonte, processoId, syncDataJud.data, syncDataJud.error, jusbrJobResult, jusbrJobError, startJusBR.error, ultimoAndamentoPre])
  const temMais = (count?.total ?? 0) > offset + PAGE
  // Os N andamentos mais recentes (por created_at) na 1ª página são os "novos
  // deste lote". Só vale na 1ª página, onde os recém-inseridos aparecem.
  const novoLoteIds = useMemo(() => {
    if (!novosLoteCount || offset !== 0) return new Set<string>()
    const ordenados = [...andamentos].sort((a, b) =>
      (b.created_at || '').localeCompare(a.created_at || ''),
    )
    return new Set(ordenados.slice(0, novosLoteCount).map((a) => a.id))
  }, [andamentos, novosLoteCount, offset])
  const jusbrAtivo = !!jusbrSession?.active
  const jusbrProgressPct = jusbrJob?.total
    ? Math.min(100, Math.round((jusbrJob.processed / jusbrJob.total) * 100))
    : 0

  function handleFonte(f: Fonte) {
    setFonte(f)
    setOffset(0)
    syncDataJud.reset()
    startJusBR.reset()
    setJusbrJobResult(null)
    setJusbrJobError(null)
  }

  function handleSync() {
    if (fonte === 'datajud') {
      syncDataJud.mutate()
    } else {
      if (!jusbrAtivo) {
        setShowTokenModal(true)
      } else {
        startJusBR.mutate()
      }
    }
  }

  const configurarSessao = useMutation({
    mutationFn: (capture: string) => andamentosApi.configurarSessaoJusBR(capture),
    onMutate: () => {
      setJusbrJobError(null)
    },
    onSuccess: async (_, capture) => {
      saveStoredJusbrToken(capture)
      await refetchJusbrSession()
      setShowTokenModal(false)
      startJusBR.mutate()
    },
    onError: (error: unknown) => {
      setJusbrJobError(extractApiErrorMessage(error, 'Não foi possível configurar a sessão do jus.br.'))
    },
  })

  function handleToken(capture: string) {
    configurarSessao.mutate(capture)
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
              DataJud v1
            </button>
            <button
              className={`${styles.fonteBtn} ${fonte === 'jusbr' ? styles.fonteBtnActive : ''}`}
              onClick={() => handleFonte('jusbr')}
              title="jus.br — sessão compartilhada do portal com diagnostico melhorado"
            >
              jus.br {JUSBR_VERSION}
            </button>
          </div>

          {(count?.nao_lidos ?? 0) > 0 && !isSyncing && (
            <button className={styles.btnLer} onClick={() => marcarLidos.mutate()} disabled={marcarLidos.isPending}>
              Marcar lidos
            </button>
          )}

          {/* Sync / token button */}
          {fonte === 'jusbr' && jusbrAtivo && (
            <button
              className={styles.btnTokenReset}
              onClick={() => setShowTokenModal(true)}
              title="Sessão ativa — clique para renovar (colar JSON)"
            >
              🔑
            </button>
          )}
          {fonte === 'jusbr' && (
            <button
              className={styles.btnTokenReset}
              onClick={() => setShowPkceModal(true)}
              title="Conectar via gov.br (login PKCE, sessão não expira)"
            >
              🔐
            </button>
          )}
          <button
            className={styles.btnSync}
            onClick={handleSync}
            disabled={isSyncing}
          >
            {isSyncing ? (
              <span className={styles.syncingLabel}><span className={styles.spinner} /> Buscando…</span>
            ) : fonte === 'jusbr' && !jusbrAtivo ? (
              `🔑 Conectar jus.br ${JUSBR_VERSION}`
            ) : (
              '⟳ Sincronizar'
            )}
          </button>
        </div>
      </div>

      {/* jus.br token info bar */}
      {fonte === 'jusbr' && !jusbrAtivo && !isSyncing && !syncData && (
        <div className={styles.jusBRInfo}>
          <span>O modo <strong>jus.br {JUSBR_VERSION}</strong> usa uma sessão compartilhada do portal. Para baixar <strong>documentos reais</strong>, conecte de preferência com <strong>cURL</strong> ou <strong>headers</strong> autenticados; a resposta de <strong>/processos</strong> não ativa o botão.</span>
        </div>
      )}
      {fonte === 'jusbr' && jusbrAtivo && !isSyncing && !syncData && (
        <div className={styles.jusBRInfo}>
          <span>
            Sessão do <strong>jus.br {JUSBR_VERSION}</strong> ativa no backend e reutilizada automaticamente para todos os processos.
            {tokenExpiry ? ` Expira em ${tokenExpiry}.` : ''}
            {jusbrSession?.capture_kind ? ` Tipo salvo: ${jusbrSession.capture_kind}.` : ''}
            {` Cookies: ${jusbrSession?.has_cookies ? 'sim' : 'não'}.`}
            {!jusbrSession?.has_cookies ? ' Se documentos não vierem, renove com JSON de token ou cURL/headers que tenham Authorization: Bearer.' : ''}
            {!jusbrSession?.has_cookies && detectedHost ? ` Captura atual: ${detectedHost}.` : ''}
          </span>
          <button
            className={styles.btnLer}
            onClick={async () => {
              await andamentosApi.limparSessaoJusBR()
              clearStoredJusbrToken()
              await refetchJusbrSession()
            }}
          >
            Limpar sessão
          </button>
        </div>
      )}

      {/* Progress bar */}
      {isSyncing && (
        <div className={styles.progressWrap}>
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={jusbrJob?.total ? { width: `${jusbrProgressPct}%`, animation: 'none' } : undefined}
            />
          </div>
          {fonte === 'jusbr' && (
            <div className={styles.progressText}>
              <span>{jusbrJob?.message || 'Preparando sincronização do jus.br...'}</span>
              {jusbrJob?.total ? (
                <strong>{jusbrJob.processed}/{jusbrJob.total} processados · {jusbrJob.uploaded} no Drive</strong>
              ) : null}
            </div>
          )}
        </div>
      )}

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
                {jusbrAtivo
                  ? 'Clique em ⟳ Sincronizar para buscar no portal.'
                  : 'Configure a sessão para sincronizar com o jus.br.'}
              </p>
            </>
          )}
        </div>
      ) : (
        <>
          <div className={styles.lista}>
            {andamentos.map((a) => (
              <AndamentoCard key={a.id} andamento={a} novoLote={novoLoteIds.has(a.id)} />
            ))}
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
          initialToken=""
          isSubmitting={configurarSessao.isPending}
          error={configurarSessao.isError ? extractApiErrorMessage(configurarSessao.error, 'Não foi possível configurar a sessão do jus.br.') : null}
        />
      )}

      {/* PKCE modal (sessão perene via gov.br) */}
      {showPkceModal && (
        <ConectarGovBrModal
          onClose={() => setShowPkceModal(false)}
          onSuccess={() => {
            qc.invalidateQueries({ queryKey: ['jusbr-session'] })
          }}
        />
      )}
    </div>
  )
}

function AndamentoCard({ andamento: a, novoLote = false }: { andamento: Andamento; novoLote?: boolean }) {
  const arquivoUrl = andamentosApi.arquivoUrl(a.id)
  return (
    <div className={`${styles.card} ${novoLote ? styles.cardNovoLote : !a.lido ? styles.cardNaoLido : ''}`}>
      <div className={styles.cardMeta}>
        <span className={styles.data}>{formatDate(a.data_andamento)}</span>
        {a.grau && <span className={styles.grauBadge}>{a.grau}</span>}
        {a.tipo && <span className={styles.tipo}>{a.tipo}</span>}
        {novoLote
          ? <span className={styles.novoLoteBadge}>Novo neste lote</span>
          : !a.lido && <span className={styles.novoBadge}>Novo</span>}
        {a.arquivo_nome && (
          <a
            className={styles.btnArquivo}
            href={arquivoUrl}
            target="_blank"
            rel="noopener noreferrer"
            title={a.arquivo_nome}
          >
            Arquivo
          </a>
        )}
      </div>
      <p className={styles.descricao}>{a.descricao}</p>
      <span className={styles.atualizadoEm}>
        Última atualização: {formatDateTime(a.created_at)}
      </span>
    </div>
  )
}
