import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa, TIPOS_PECA } from '../api/autosIa'
import type { Caso, Documento, DocumentoDrive, DocumentoDriveAnexo, GrafoAresta, GrafoNo, Peca, PecaDetalhe, TipoPeca } from '../api/autosIa'
import ReferenciaHover from '../components/autosIa/ReferenciaHover'
import GrafoTimeline from '../components/autosIa/GrafoTimeline'
import pageStyles from './Page.module.css'
import styles from './AutosIACasoPage.module.css'

type Aba = 'upload' | 'pecas' | 'documentos' | 'timeline' | 'grafo' | 'faq'

const ABAS: { key: Aba; label: string }[] = [
  { key: 'upload', label: 'Upload & Blocos' },
  { key: 'pecas', label: 'Peças & Busca' },
  { key: 'documentos', label: 'Documentos' },
  { key: 'timeline', label: 'Linha do Tempo' },
  { key: 'grafo', label: 'Grafo de Referências' },
  { key: 'faq', label: 'Perguntas' },
]

const STATUS_DOC_COR: Record<string, { bg: string; cor: string }> = {
  pendente: { bg: '#f3f4f6', cor: 'var(--gray-mid)' },
  processando: { bg: '#dbeafe', cor: '#1d4ed8' },
  concluido: { bg: '#dcfce7', cor: '#15803d' },
  erro: { bg: '#fee2e2', cor: '#b91c1c' },
  cancelado: { bg: '#f3f4f6', cor: 'var(--gray-mid)' },
}

function formatarData(d?: string | null) {
  if (!d) return null
  return new Date(d).toLocaleDateString('pt-BR')
}

function formatarHora(d?: string | null) {
  if (!d) return null
  return new Date(d).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function formatarUsd(v: number) {
  return `US$ ${v.toFixed(v < 1 ? 3 : 2)}`
}

const STATUS_SYNC_LABEL: Record<string, string> = {
  ok: 'sincronizado',
  erro: 'falhou',
  nenhum: 'sem novidades',
  processando: 'sincronizando...',
  cancelado: 'cancelado',
}

const ETAPA_SYNC_LABEL: Record<string, string> = {
  lendo: 'Lendo documentos',
  resumindo: 'Resumindo peças',
  reclassificando: 'Reclassificando peças',
}

export default function AutosIACasoPage() {
  const { casoId } = useParams<{ casoId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [aba, setAba] = useState<Aba>('upload')

  const { data: caso } = useQuery({
    queryKey: ['autos-ia', 'caso', casoId],
    queryFn: () => autosIa.obterCaso(casoId!),
    enabled: !!casoId,
    refetchInterval: (query) => (query.state.data?.ultimo_sync_status === 'processando' ? 3000 : false),
  })

  const emProcessamento = caso?.ultimo_sync_status === 'processando'

  const { data: estimativaImportacao } = useQuery({
    queryKey: ['autos-ia', 'estimativa-importacao', casoId],
    queryFn: () => autosIa.estimativaImportacao(casoId!),
    enabled: !!casoId && !!caso?.processo_id && !emProcessamento,
  })

  const { data: estimativaReclassificacao } = useQuery({
    queryKey: ['autos-ia', 'estimativa-reclassificacao', casoId],
    queryFn: () => autosIa.estimativaReclassificacao(casoId!),
    enabled: !!casoId && !emProcessamento,
  })

  const sincronizar = useMutation({
    mutationFn: () => autosIa.sincronizarAgora(casoId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] }),
  })

  const importarExistentes = useMutation({
    mutationFn: () => autosIa.importarExistentes(casoId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] }),
  })

  const cancelarSync = useMutation({
    mutationFn: () => autosIa.cancelarSync(casoId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] }),
  })

  const atualizarMetadados = useMutation({
    mutationFn: () => autosIa.atualizarMetadados(casoId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] }),
  })

  const reagrupar = useMutation({
    mutationFn: () => autosIa.reagrupar(casoId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'documentos-drive', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'grafo', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'pecas', casoId] })
    },
  })

  const deletarCaso = useMutation({
    mutationFn: () => autosIa.deletarCaso(casoId!),
    onSuccess: () => navigate('/autos-ia'),
  })

  const reclassificar = useMutation({
    mutationFn: () => autosIa.reclassificar(casoId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] }),
  })

  function confirmarReclassificar() {
    const est = estimativaReclassificacao
    if (!est || est.itens_pendentes === 0) {
      window.alert('Nenhuma peça elegível para reclassificar (precisa já ter sido resumida).')
      return
    }
    const aviso = `Reclassificar ${est.itens_pendentes} peça(s) já resumida(s) — atualiza tipo, `
      + `peticionante e ID de referência pelo conteúdo real, sem gerar resumo de novo.\n\n`
      + `Estimativa: ~${formatarUsd(est.custo_estimado_usd)} · ~${est.tempo_estimado_minutos} min.\n\nContinuar?`
    if (!window.confirm(aviso)) return
    reclassificar.mutate()
  }

  function confirmarEDisparar(acao: 'sincronizar' | 'importar') {
    const est = estimativaImportacao
    const aviso = est && est.itens_pendentes > 0
      ? `${est.itens_pendentes} documento(s) pendente(s) · estimativa ~${formatarUsd(est.custo_estimado_usd)} · ~${est.tempo_estimado_minutos} min.\n\nContinuar?`
      : 'Continuar?'
    if (!window.confirm(aviso)) return
    if (acao === 'sincronizar') sincronizar.mutate()
    else importarExistentes.mutate()
  }

  const { data: grafo } = useQuery({
    queryKey: ['autos-ia', 'grafo', casoId],
    queryFn: () => autosIa.obterGrafo(casoId!),
    enabled: !!casoId,
  })

  const nosPorId = useMemo(() => {
    const mapa = new Map<string, NonNullable<typeof grafo>['nos'][number]>()
    grafo?.nos.forEach((n) => mapa.set(n.id, n))
    return mapa
  }, [grafo])

  const arestasPorOrigem = useMemo(() => {
    const mapa = new Map<string, NonNullable<typeof grafo>['arestas']>()
    grafo?.arestas.forEach((a) => {
      const lista = mapa.get(a.peca_origem_id) ?? []
      lista.push(a)
      mapa.set(a.peca_origem_id, lista)
    })
    return mapa
  }, [grafo])

  if (!casoId) return null

  return (
    <div>
      <Link to="/autos-ia" className={styles.backLink}>← Voltar para Autos IA</Link>
      <div className={pageStyles.pageHeader}>
        <div>
          <h1 className={pageStyles.pageTitle}>{caso?.nome ?? 'Carregando...'}</h1>
          {caso && (
            <div className={styles.headerMeta}>
              {caso.numero_processo && <span>Processo {caso.numero_processo}</span>}
              <span>{caso.total_paginas} páginas indexadas</span>
              <span title="Custo real acumulado em chamadas de IA (segmentação + resumo) neste caso">
                {formatarUsd(caso.custo_usd_total)} gastos
              </span>
              <span className={`${pageStyles.badge} ${pageStyles[`status_${caso.status}`]}`}>{caso.status}</span>
              {caso.tem_peca_pendente_continuacao && (
                <span className={styles.warningBuffer}>
                  peça em aberto — continue enviando os próximos blocos
                </span>
              )}
              {caso.processo_id && (
                <>
                  <span>
                    {caso.sync_jusbr_ativo ? 'sync automático 3x/dia' : 'vinculado a um processo'}
                    {caso.ultimo_sync_status && ` · última sync: ${STATUS_SYNC_LABEL[caso.ultimo_sync_status] ?? caso.ultimo_sync_status}`}
                    {caso.ultima_sincronizacao_em && ` (${new Date(caso.ultima_sincronizacao_em).toLocaleString('pt-BR')})`}
                  </span>
                  {emProcessamento ? (
                    <button
                      className={pageStyles.btnSmall}
                      disabled={cancelarSync.isPending}
                      onClick={() => {
                        if (window.confirm('Cancelar a sincronização em andamento? As peças já lidas/resumidas até agora ficam salvas.')) {
                          cancelarSync.mutate()
                        }
                      }}
                    >
                      {cancelarSync.isPending ? 'Cancelando...' : 'Cancelar'}
                    </button>
                  ) : (
                    <>
                      <button
                        className={pageStyles.btnSmall}
                        disabled={sincronizar.isPending}
                        onClick={() => confirmarEDisparar('sincronizar')}
                      >
                        Sincronizar agora
                      </button>
                      <button
                        className={pageStyles.btnSmall}
                        disabled={importarExistentes.isPending}
                        onClick={() => confirmarEDisparar('importar')}
                        title="Importa só os documentos já baixados pelo jus.br, sem consultar a rede"
                      >
                        Importar documentos existentes
                      </button>
                      <button
                        className={pageStyles.btnSmall}
                        disabled={atualizarMetadados.isPending}
                        onClick={() => {
                          if (window.confirm('Consultar o jus.br só para atualizar metadados (ex.: hora de protocolo) dos andamentos já conhecidos? Não processa nenhuma peça nova — zero custo de IA.')) {
                            atualizarMetadados.mutate()
                          }
                        }}
                        title="Só atualiza dados como a hora de protocolo — não baixa nem processa peças novas"
                      >
                        {atualizarMetadados.isPending ? 'Atualizando...' : 'Atualizar metadados'}
                      </button>
                      <button
                        className={pageStyles.btnSmall}
                        disabled={reagrupar.isPending}
                        onClick={() => {
                          if (window.confirm('Reorganizar petição/anexo das peças já importadas, usando a hora de protocolo quando disponível? 100% local, sem IA nem rede.')) {
                            reagrupar.mutate()
                          }
                        }}
                        title="Reaplica o agrupamento petição/anexo nas peças já importadas — sem IA, sem rede"
                      >
                        {reagrupar.isPending ? 'Reagrupando...' : 'Reagrupar peças'}
                      </button>
                    </>
                  )}
                </>
              )}
              {!emProcessamento && estimativaReclassificacao && estimativaReclassificacao.itens_pendentes > 0 && (
                <button
                  className={pageStyles.btnSmall}
                  disabled={reclassificar.isPending}
                  onClick={confirmarReclassificar}
                  title="Atualiza tipo, peticionante e ID de referência das peças já resumidas, pelo conteúdo real — sem gerar resumo de novo"
                >
                  Reclassificar peças
                </button>
              )}
              <button
                className={pageStyles.btnDanger}
                disabled={deletarCaso.isPending || emProcessamento}
                title={emProcessamento ? 'Cancele a sincronização em andamento antes de excluir' : undefined}
                onClick={() => {
                  if (window.confirm(`Excluir o caso "${caso.nome}"? Apaga todas as peças, o grafo e as perguntas já indexadas — não pode ser desfeito.`)) {
                    deletarCaso.mutate()
                  }
                }}
              >
                {deletarCaso.isPending ? 'Excluindo...' : 'Excluir caso'}
              </button>
            </div>
          )}
          {caso?.processo_id && !emProcessamento && estimativaImportacao && estimativaImportacao.itens_pendentes > 0 && (
            <p style={{ fontSize: 12, color: 'var(--gray-mid)', marginTop: 6 }}>
              {estimativaImportacao.itens_pendentes} documento(s) do processo ainda não indexado(s) — projeção
              ~{formatarUsd(estimativaImportacao.custo_estimado_usd)} · ~{estimativaImportacao.tempo_estimado_minutos} min
              para importar tudo.
            </p>
          )}
          {emProcessamento && <SyncProgress caso={caso!} />}
          {caso?.ultimo_sync_status === 'cancelado' && caso.ultimo_sync_mensagem && (
            <p style={{ fontSize: 12, color: '#a16207', marginTop: 6 }}>{caso.ultimo_sync_mensagem}</p>
          )}
          {caso?.ultimo_sync_status === 'erro' && caso.ultimo_sync_mensagem && (
            <p style={{ fontSize: 12, color: '#b91c1c', marginTop: 6 }}>
              Falha na última sincronização: {caso.ultimo_sync_mensagem}
            </p>
          )}
        </div>
      </div>

      <div className={styles.tabs}>
        {ABAS.map((a) => (
          <button
            key={a.key}
            className={`${styles.tabBtn} ${aba === a.key ? styles.tabActive : ''}`}
            onClick={() => setAba(a.key)}
          >
            {a.label}
          </button>
        ))}
      </div>

      {aba === 'upload' && (
        <AbaUpload casoId={casoId} totalPaginas={caso?.total_paginas ?? 0} vinculadoAProcesso={!!caso?.processo_id} />
      )}
      {aba === 'pecas' && (
        <AbaPecas casoId={casoId} arestasPorOrigem={arestasPorOrigem} nosPorId={nosPorId} />
      )}
      {aba === 'documentos' && <AbaDocumentosDrive casoId={casoId} vinculadoAProcesso={!!caso?.processo_id} />}
      {aba === 'timeline' && (
        <AbaTimeline casoId={casoId} arestasPorOrigem={arestasPorOrigem} nosPorId={nosPorId} />
      )}
      {aba === 'grafo' && <AbaGrafo casoId={casoId} />}
      {aba === 'faq' && <AbaFaq casoId={casoId} nosPorId={nosPorId} />}
    </div>
  )
}

// ── Upload ───────────────────────────────────────────────────────────────

function AbaUpload({ casoId, totalPaginas, vinculadoAProcesso }: { casoId: string; totalPaginas: number; vinculadoAProcesso: boolean }) {
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [paginaInicio, setPaginaInicio] = useState('')
  const [progresso, setProgresso] = useState<number | null>(null)

  const { data: documentos = [] } = useQuery({
    queryKey: ['autos-ia', 'documentos', casoId],
    queryFn: () => autosIa.listarDocumentos(casoId),
    refetchInterval: (query) => {
      const lista = query.state.data ?? []
      return lista.some((d) => d.status === 'pendente' || d.status === 'processando') ? 3000 : false
    },
  })

  const invalidarDocumentos = () => {
    qc.invalidateQueries({ queryKey: ['autos-ia', 'documentos', casoId] })
    qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] })
  }

  const cancelarDocumento = useMutation({
    mutationFn: (documentoId: string) => autosIa.cancelarDocumento(documentoId),
    onSuccess: invalidarDocumentos,
  })

  const retomarDocumento = useMutation({
    mutationFn: (documentoId: string) => autosIa.retomarDocumento(documentoId),
    onSuccess: invalidarDocumentos,
  })

  const enviar = useMutation({
    mutationFn: (arquivo: File) =>
      autosIa.enviarBloco(casoId, arquivo, paginaInicio ? Number(paginaInicio) : null, setProgresso),
    onSuccess: () => {
      invalidarDocumentos()
      setProgresso(null)
      setPaginaInicio('')
      if (inputRef.current) inputRef.current.value = ''
    },
    onError: () => setProgresso(null),
  })

  return (
    <div>
      {vinculadoAProcesso && (
        <p style={{ fontSize: 12.5, color: 'var(--gray-mid)', marginBottom: 14 }}>
          Este caso está vinculado a um processo e sincroniza automaticamente com o jus.br —
          normalmente você não precisa subir blocos manualmente. Use o upload abaixo só para
          complementar com documentos que não estejam nos autos eletrônicos.
        </p>
      )}
      <form
        className={pageStyles.form}
        style={{ maxWidth: 640 }}
        onSubmit={(e) => {
          e.preventDefault()
          const arquivo = inputRef.current?.files?.[0]
          if (arquivo) enviar.mutate(arquivo)
        }}
      >
        <div className={styles.uploadRow}>
          <div className={pageStyles.formRow} style={{ flex: 1, marginBottom: 0 }}>
            <label className={pageStyles.formLabel}>Bloco de PDF *</label>
            <input ref={inputRef} type="file" accept="application/pdf" required />
          </div>
          <div className={pageStyles.formRow} style={{ width: 180, marginBottom: 0 }}>
            <label className={pageStyles.formLabel}>Página inicial</label>
            <input
              className={pageStyles.input}
              type="number"
              min={1}
              placeholder={`auto (${totalPaginas + 1})`}
              value={paginaInicio}
              onChange={(e) => setPaginaInicio(e.target.value)}
            />
          </div>
          <button type="submit" className={pageStyles.btnPrimary} disabled={enviar.isPending}>
            {enviar.isPending ? 'Enviando...' : 'Enviar bloco'}
          </button>
        </div>
        {progresso != null && (
          <div className={styles.progressBar}>
            <div className={styles.progressFill} style={{ width: `${progresso}%` }} />
          </div>
        )}
        {enviar.isError && (
          <p style={{ color: '#b91c1c', fontSize: 12.5, marginTop: 10 }}>
            Falha ao enviar o bloco. Tente novamente.
          </p>
        )}
      </form>

      {documentos.length === 0 ? (
        <p className={pageStyles.empty}>Nenhum bloco enviado ainda.</p>
      ) : (
        <div className={pageStyles.tableCard}>
          <table className={pageStyles.table}>
            <thead>
              <tr>
                <th>Arquivo</th>
                <th>Páginas</th>
                <th>Estimativa</th>
                <th>Progresso</th>
                <th>Custo real</th>
                <th>OCR</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {documentos.map((d) => (
                <tr key={d.id}>
                  <td>{d.nome_arquivo}</td>
                  <td>{d.pagina_inicio}–{d.pagina_fim}</td>
                  <td style={{ fontSize: 11.5, color: 'var(--gray-mid)' }}>
                    ~{d.estimativa.pecas_estimadas} peças · ~US$ {d.estimativa.custo_estimado_usd.toFixed(2)} · ~{d.estimativa.tempo_estimado_minutos} min
                  </td>
                  <td style={{ minWidth: 200 }}>
                    <ProgressoDocumento doc={d} />
                  </td>
                  <td style={{ fontSize: 11.5, color: 'var(--gray-mid)' }}>{formatarUsd(d.custo_usd)}</td>
                  <td>{d.paginas_ocr}</td>
                  <td>
                    {d.status === 'processando' && (
                      <button
                        className={pageStyles.btnSmall}
                        disabled={cancelarDocumento.isPending}
                        onClick={() => {
                          if (window.confirm('Cancelar o processamento deste bloco? As peças já resumidas ficam salvas.')) {
                            cancelarDocumento.mutate(d.id)
                          }
                        }}
                      >
                        Cancelar
                      </button>
                    )}
                    {(d.status === 'cancelado' || d.status === 'erro') && (
                      <button
                        className={pageStyles.btnSmall}
                        disabled={retomarDocumento.isPending}
                        onClick={() => retomarDocumento.mutate(d.id)}
                      >
                        Retomar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const ETAPA_LABEL: Record<string, string> = {
  extraindo: 'Extraindo texto',
  segmentando: 'Identificando peças',
  resumindo: 'Resumindo peças',
}

/** Relógio que atualiza periodicamente, para recalcular o ETA exibido mesmo
 * entre um refetch e outro (evita ficar preso ao "agora" do primeiro render). */
function useNow(intervalMs: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

function SyncProgress({ caso }: { caso: Caso }) {
  const agora = useNow(5000)

  const total = caso.sync_total_itens ?? 0
  const feito = caso.sync_itens_processados ?? 0
  const pct = total > 0 ? Math.min(100, Math.round((feito / total) * 100)) : 0

  let eta = ''
  if (caso.sync_iniciado_em && pct >= 3) {
    const elapsedMs = agora - new Date(caso.sync_iniciado_em).getTime()
    const restanteMs = Math.max(0, elapsedMs / (pct / 100) - elapsedMs)
    const min = Math.round(restanteMs / 60000)
    eta = min < 1 ? '< 1 min restante' : `~${min} min restante`
  }

  return (
    <div style={{ marginTop: 8, maxWidth: 420 }}>
      <div style={{ fontSize: 12, color: '#1d4ed8', marginBottom: 4 }}>
        {ETAPA_SYNC_LABEL[caso.sync_etapa ?? ''] ?? 'Processando'}
        {total > 0 && ` — ${feito}/${total}`}
        {eta && ` · ${eta}`}
        {` · ${formatarUsd(caso.custo_usd_total)} gastos até agora`}
      </div>
      <div className={styles.progressBar}>
        <div className={styles.progressFill} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function ProgressoDocumento({ doc }: { doc: Documento }) {
  const agora = useNow(5000)

  if (doc.status === 'pendente') {
    return <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Na fila...</span>
  }
  if (doc.status === 'erro') {
    return (
      <div>
        <span className={pageStyles.badge} style={{ background: STATUS_DOC_COR.erro.bg, color: STATUS_DOC_COR.erro.cor }}>
          erro
        </span>
        {doc.erro_mensagem && <div style={{ fontSize: 11, color: '#b91c1c', marginTop: 4 }}>{doc.erro_mensagem}</div>}
      </div>
    )
  }
  if (doc.status === 'concluido') {
    return (
      <span className={pageStyles.badge} style={{ background: STATUS_DOC_COR.concluido.bg, color: STATUS_DOC_COR.concluido.cor }}>
        concluído — {doc.pecas_geradas} peça{doc.pecas_geradas !== 1 ? 's' : ''}
      </span>
    )
  }
  if (doc.status === 'cancelado') {
    return (
      <span className={pageStyles.badge} style={{ background: STATUS_DOC_COR.cancelado.bg, color: STATUS_DOC_COR.cancelado.cor }}>
        cancelado — {doc.pecas_resumidas}/{doc.pecas_geradas || '?'} peça{doc.pecas_geradas !== 1 ? 's' : ''} resumida(s)
      </span>
    )
  }

  const emResumo = doc.etapa === 'resumindo'
  const total = emResumo ? doc.pecas_geradas : doc.total_paginas
  const feito = emResumo ? doc.pecas_resumidas : doc.paginas_processadas
  const pct = total > 0 ? Math.min(100, Math.round((feito / total) * 100)) : 0

  const elapsedMs = agora - new Date(doc.criado_em).getTime()
  let eta = ''
  if (pct >= 5) {
    const restanteMs = Math.max(0, elapsedMs / (pct / 100) - elapsedMs)
    const min = Math.round(restanteMs / 60000)
    eta = min < 1 ? '< 1 min restante' : `~${min} min restante`
  }

  return (
    <div>
      <div style={{ fontSize: 11.5, color: 'var(--gray-mid)', marginBottom: 4 }}>
        {ETAPA_LABEL[doc.etapa ?? ''] ?? 'Processando'} — {feito}/{total}{eta && ` · ${eta}`}
      </div>
      <div className={styles.progressBar} style={{ maxWidth: 180 }}>
        <div className={styles.progressFill} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// ── Peças / busca ────────────────────────────────────────────────────────

type ArestasMap = Map<string, GrafoAresta[]>
type NosMap = Map<string, GrafoNo>

function PecaCard({ peca, arestasPorOrigem, nosPorId }: { peca: Peca; arestasPorOrigem: ArestasMap; nosPorId: NosMap }) {
  const [aberta, setAberta] = useState(false)
  const [anexosAbertos, setAnexosAbertos] = useState(false)
  const { data: detalhe } = useQuery<PecaDetalhe>({
    queryKey: ['autos-ia', 'peca', peca.id],
    queryFn: () => autosIa.obterPeca(peca.id),
    enabled: aberta,
  })
  const { data: anexos = [] } = useQuery({
    queryKey: ['autos-ia', 'anexos', peca.id],
    queryFn: () => autosIa.listarAnexos(peca.id),
    enabled: anexosAbertos,
  })
  const arestas = arestasPorOrigem.get(peca.id) ?? []

  return (
    <div className={styles.pecaCard}>
      <div className={styles.pecaTop}>
        <div>
          <span className={styles.tipoBadge}>{peca.tipo}</span>
          <div className={styles.pecaTitulo}>{peca.titulo}</div>
          <div className={styles.pecaMeta}>
            <span>págs. {peca.pagina_inicio}-{peca.pagina_fim}</span>
            {peca.autor && <span>{peca.autor}</span>}
            {peca.data_peca && <span>{formatarData(peca.data_peca)}</span>}
            {peca.id_processual && <span>ID {peca.id_processual}</span>}
            {peca.origem === 'jusbr' && <span>jus.br</span>}
            {peca.status !== 'resumida' && (
              <span style={{ color: peca.status === 'erro' ? '#b91c1c' : '#a16207' }}>
                {peca.status === 'erro' ? `erro ao resumir: ${peca.erro_mensagem}` : 'resumo pendente...'}
              </span>
            )}
          </div>
        </div>
      </div>

      {peca.resumo && <div className={styles.pecaResumo}>{peca.resumo}</div>}

      {((peca.keywords?.length ?? 0) > 0 || arestas.length > 0) && (
        <div className={styles.chipsRow}>
          {peca.keywords?.map((k) => <span key={k} className={styles.keywordChip}>{k}</span>)}
          {arestas.map((a) => (
            <ReferenciaHover
              key={a.id}
              idMencionado={a.id_mencionado}
              no={a.peca_destino_id ? nosPorId.get(a.peca_destino_id) : undefined}
            />
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <button className={styles.verTextoBtn} onClick={() => setAberta(!aberta)}>
          {aberta ? 'Ocultar texto completo' : 'Ver texto completo'}
        </button>
        {peca.total_anexos > 0 && (
          <button className={styles.verTextoBtn} onClick={() => setAnexosAbertos(!anexosAbertos)}>
            {anexosAbertos ? '▲' : '▼'} {peca.total_anexos} documento{peca.total_anexos > 1 ? 's' : ''} anexo{peca.total_anexos > 1 ? 's' : ''}
          </button>
        )}
      </div>
      {aberta && (
        <div className={styles.textoCompleto}>{detalhe?.texto_md ?? 'Carregando...'}</div>
      )}
      {anexosAbertos && (
        <div className={styles.anexosLista}>
          {anexos.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Carregando...</p>
          ) : (
            anexos.map((a) => <PecaCard key={a.id} peca={a} arestasPorOrigem={arestasPorOrigem} nosPorId={nosPorId} />)
          )}
        </div>
      )}
    </div>
  )
}

const TAMANHO_PAGINA_PECAS = 100

function AbaPecas({ casoId, arestasPorOrigem, nosPorId }: { casoId: string; arestasPorOrigem: ArestasMap; nosPorId: NosMap }) {
  const [q, setQ] = useState('')
  const [tipo, setTipo] = useState('')
  const [dataInicio, setDataInicio] = useState('')
  const [dataFim, setDataFim] = useState('')

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['autos-ia', 'pecas', casoId, q, tipo, dataInicio, dataFim],
    queryFn: ({ pageParam }) => autosIa.listarPecas(casoId, {
      q: q || undefined,
      tipo: tipo || undefined,
      data_inicio: dataInicio || undefined,
      data_fim: dataFim || undefined,
      offset: pageParam,
      limit: TAMANHO_PAGINA_PECAS,
    }),
    initialPageParam: 0,
    getNextPageParam: (ultimaPagina, todasPaginas) =>
      ultimaPagina.length === TAMANHO_PAGINA_PECAS ? todasPaginas.length * TAMANHO_PAGINA_PECAS : undefined,
  })
  const pecas = data?.pages.flat() ?? []

  return (
    <div>
      <div className={styles.filtrosRow}>
        <div className={styles.campo}>
          <input
            className={pageStyles.input}
            placeholder="Buscar por tema (ex.: prescrição, honorários...)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div style={{ width: 160 }}>
          <select className={pageStyles.input} value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">Todos os tipos</option>
            {TIPOS_PECA.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div style={{ width: 150 }}>
          <input className={pageStyles.input} type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
        </div>
        <div style={{ width: 150 }}>
          <input className={pageStyles.input} type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} />
        </div>
        <a
          className={pageStyles.btnSmall}
          style={{ whiteSpace: 'nowrap' }}
          href={autosIa.urlDownloadPecas(casoId, { tipo: tipo || undefined })}
          target="_blank"
          rel="noreferrer"
        >
          ⬇ Baixar peças em PDF (sem anexos)
        </a>
      </div>

      {isLoading ? (
        <p className={pageStyles.empty}>Carregando...</p>
      ) : pecas.length === 0 ? (
        <p className={pageStyles.empty}>Nenhuma peça encontrada.</p>
      ) : (
        <>
          {pecas.map((p) => (
            <PecaCard key={p.id} peca={p} arestasPorOrigem={arestasPorOrigem} nosPorId={nosPorId} />
          ))}
          {hasNextPage && (
            <button
              className={pageStyles.btnSmall}
              style={{ display: 'block', margin: '16px auto' }}
              disabled={isFetchingNextPage}
              onClick={() => fetchNextPage()}
            >
              {isFetchingNextPage ? 'Carregando...' : `Carregar mais (${pecas.length} carregada(s))`}
            </button>
          )}
        </>
      )}
    </div>
  )
}

// ── Documentos (listagem compacta + link pro Drive) ─────────────────────────

const TAMANHO_PAGINA_DOCUMENTOS = 60

function LinhaDocumento({ doc, nivel, casoId }: { doc: DocumentoDrive | DocumentoDriveAnexo; nivel: number; casoId: string }) {
  const qc = useQueryClient()
  const anexos = 'anexos' in doc ? doc.anexos : []
  const [aberto, setAberto] = useState(false)
  const temAnexos = anexos.length > 0
  const ehPeticao = doc.tipo === 'peticao'

  const marcarTipo = useMutation({
    mutationFn: (tipo: TipoPeca) => autosIa.atualizarTipoPeca(doc.id, tipo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'documentos-drive', casoId] }),
  })

  return (
    <div className={styles.docItem}>
      <div className={ehPeticao ? styles.docBlocoPeticao : undefined}>
        <div className={styles.docRow} style={{ paddingLeft: nivel * 22 }}>
          {temAnexos ? (
            <button
              type="button"
              className={styles.docChevron}
              onClick={() => setAberto(!aberto)}
              aria-expanded={aberto}
              aria-label={aberto ? 'Recolher anexos' : 'Expandir anexos'}
            >
              {aberto ? '▾' : '▸'}
            </button>
          ) : (
            <span className={styles.docChevronVazio} />
          )}
          <span className={styles.docData} title={doc.protocolado_em ? `Protocolado às ${formatarHora(doc.protocolado_em)}` : undefined}>
            <span>{doc.data_peca ? formatarData(doc.data_peca) : '—'}</span>
            {doc.protocolado_em && <span className={styles.docHora}>{formatarHora(doc.protocolado_em)}</span>}
          </span>
          {doc.arquivo_drive_link ? (
            <a
              className={styles.docDriveIcone}
              href={doc.arquivo_drive_link}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              title="Abrir no Drive"
              aria-label="Abrir no Drive"
            >
              ↗
            </a>
          ) : (
            <span className={styles.docDriveIcone} />
          )}
          <span className={`${styles.docNomeIndexado} ${ehPeticao ? styles.docNomeIndexadoPeticao : ''}`}>
            {doc.nome_indexado || doc.titulo}
          </span>
          <span className={styles.tipoBadge}>{doc.tipo}</span>
          {temAnexos && <span className={styles.docAnexosCount}>{anexos.length} anexo{anexos.length > 1 ? 's' : ''}</span>}
          <button
            type="button"
            className={styles.docTogglePeticao}
            disabled={marcarTipo.isPending}
            onClick={() => marcarTipo.mutate(ehPeticao ? 'documento' : 'peticao')}
            title={ehPeticao ? 'Desmarcar como petição' : 'Marcar como petição'}
          >
            {ehPeticao ? 'Desmarcar petição' : 'Marcar petição'}
          </button>
        </div>
        <div className={styles.docRowSub} style={{ paddingLeft: nivel * 22 + 22 }}>
          {doc.arquivo_nome && <span className={styles.docArquivoNome}>{doc.arquivo_nome}</span>}
          {doc.resumo && <span className={styles.docResumo}>{doc.resumo}</span>}
        </div>
      </div>
      {temAnexos && aberto && (
        <div className={styles.docAnexos}>
          {anexos.map((a) => <LinhaDocumento key={a.id} doc={a} nivel={nivel + 1} casoId={casoId} />)}
        </div>
      )}
    </div>
  )
}

function AbaDocumentosDrive({ casoId, vinculadoAProcesso }: { casoId: string; vinculadoAProcesso: boolean }) {
  const [q, setQ] = useState('')

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['autos-ia', 'documentos-drive', casoId, q],
    queryFn: ({ pageParam }) => autosIa.listarDocumentosDrive(casoId, {
      q: q || undefined, offset: pageParam, limit: TAMANHO_PAGINA_DOCUMENTOS,
    }),
    initialPageParam: 0,
    getNextPageParam: (ultimaPagina, todasPaginas) =>
      ultimaPagina.length === TAMANHO_PAGINA_DOCUMENTOS ? todasPaginas.length * TAMANHO_PAGINA_DOCUMENTOS : undefined,
    enabled: vinculadoAProcesso,
  })
  const documentos = data?.pages.flat() ?? []

  if (!vinculadoAProcesso) {
    return (
      <p className={pageStyles.empty}>
        Esta aba só existe para casos vinculados a um processo (peças vindas do jus.br/Drive).
      </p>
    )
  }

  return (
    <div>
      <p className={styles.docLegenda}>
        Uma linha por peça, com os anexos dela recolhidos por baixo — clique na seta pra abrir.
        O nome em destaque vem do próprio nome do arquivo (sem IA); o resumo, quando já foi lido, aparece embaixo.
      </p>
      <div className={styles.filtrosRow} style={{ marginBottom: 12 }}>
        <input
          className={pageStyles.input}
          placeholder="Buscar por nome da peça ou do arquivo..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {isLoading ? (
        <p className={pageStyles.empty}>Carregando...</p>
      ) : documentos.length === 0 ? (
        <p className={pageStyles.empty}>Nenhum documento encontrado.</p>
      ) : (
        <div className={styles.docLista}>
          {documentos.map((d) => <LinhaDocumento key={d.id} doc={d} nivel={0} casoId={casoId} />)}
          {hasNextPage && (
            <button
              className={pageStyles.btnSmall}
              style={{ display: 'block', margin: '16px auto' }}
              disabled={isFetchingNextPage}
              onClick={() => fetchNextPage()}
            >
              {isFetchingNextPage ? 'Carregando...' : `Carregar mais (${documentos.length} carregado(s))`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Timeline ─────────────────────────────────────────────────────────────

function AbaTimeline({ casoId, arestasPorOrigem, nosPorId }: { casoId: string; arestasPorOrigem: ArestasMap; nosPorId: NosMap }) {
  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['autos-ia', 'pecas', casoId, 'timeline'],
    queryFn: ({ pageParam }) => autosIa.listarPecas(casoId, { offset: pageParam, limit: TAMANHO_PAGINA_PECAS }),
    initialPageParam: 0,
    getNextPageParam: (ultimaPagina, todasPaginas) =>
      ultimaPagina.length === TAMANHO_PAGINA_PECAS ? todasPaginas.length * TAMANHO_PAGINA_PECAS : undefined,
  })
  const pecas = data?.pages.flat() ?? []

  const grupos = useMemo(() => {
    // Mais recentes primeiro — é assim que um advogado revisita um processo: o que
    // aconteceu por último é o que importa saber primeiro.
    const comData = pecas.filter((p) => p.data_peca).sort((a, b) => (a.data_peca! > b.data_peca! ? -1 : 1))
    const semData = pecas.filter((p) => !p.data_peca)
    const mapa = new Map<string, Peca[]>()
    comData.forEach((p) => {
      const chave = p.data_peca!
      mapa.set(chave, [...(mapa.get(chave) ?? []), p])
    })
    const entradas: [string, Peca[]][] = Array.from(mapa.entries())
    if (semData.length > 0) entradas.push(['Sem data identificada', semData])
    return entradas
  }, [pecas])

  if (isLoading) return <p className={pageStyles.empty}>Carregando...</p>
  if (pecas.length === 0) return <p className={pageStyles.empty}>Nenhuma peça indexada ainda.</p>

  return (
    <div>
      {grupos.map(([data, itens]) => (
        <div key={data} className={styles.timelineGrupo}>
          <div className={styles.timelineData}>
            {data === 'Sem data identificada' ? data : formatarData(data)}
          </div>
          <div className={styles.timelineItens}>
            {itens.map((p) => (
              <PecaCard key={p.id} peca={p} arestasPorOrigem={arestasPorOrigem} nosPorId={nosPorId} />
            ))}
          </div>
        </div>
      ))}
      {hasNextPage && (
        <button
          className={pageStyles.btnSmall}
          style={{ display: 'block', margin: '16px auto' }}
          disabled={isFetchingNextPage}
          onClick={() => fetchNextPage()}
        >
          {isFetchingNextPage ? 'Carregando...' : `Carregar mais antigas (${pecas.length} carregada(s))`}
        </button>
      )}
    </div>
  )
}

// ── Grafo ────────────────────────────────────────────────────────────────

function AbaGrafo({ casoId }: { casoId: string }) {
  const { data: grafo, isLoading } = useQuery({
    queryKey: ['autos-ia', 'grafo', casoId],
    queryFn: () => autosIa.obterGrafo(casoId),
  })

  if (isLoading) return <p className={pageStyles.empty}>Carregando...</p>
  if (!grafo || grafo.nos.length === 0) return <p className={pageStyles.empty}>Nenhuma peça indexada ainda.</p>

  return <GrafoTimeline nos={grafo.nos} arestas={grafo.arestas} />
}

// ── FAQ ──────────────────────────────────────────────────────────────────

function AbaFaq({ casoId, nosPorId }: { casoId: string; nosPorId: NosMap }) {
  const qc = useQueryClient()
  const [pergunta, setPergunta] = useState('')

  const { data: perguntas = [] } = useQuery({
    queryKey: ['autos-ia', 'faq', casoId],
    queryFn: () => autosIa.listarFaq(casoId),
  })

  const perguntar = useMutation({
    mutationFn: () => autosIa.perguntar(casoId, pergunta),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['autos-ia', 'faq', casoId] })
      setPergunta('')
    },
  })

  const deletar = useMutation({
    mutationFn: (id: string) => autosIa.deletarPergunta(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'faq', casoId] }),
  })

  const reprocessar = useMutation({
    mutationFn: (id: string) => autosIa.reprocessarPergunta(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'faq', casoId] }),
  })

  return (
    <div>
      <form
        className={styles.faqForm}
        onSubmit={(e) => { e.preventDefault(); if (pergunta.trim()) perguntar.mutate() }}
      >
        <input
          className={pageStyles.input}
          placeholder="Pergunte algo sobre este processo (ex.: qual foi a última decisão sobre honorários?)"
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
        />
        <button className={pageStyles.btnPrimary} disabled={perguntar.isPending || !pergunta.trim()}>
          {perguntar.isPending ? 'Pensando...' : 'Perguntar'}
        </button>
      </form>

      {perguntas.length === 0 ? (
        <p className={pageStyles.empty}>Nenhuma pergunta ainda.</p>
      ) : (
        perguntas.map((f) => (
          <div key={f.id} className={styles.faqCard}>
            <div className={styles.faqPergunta}>{f.pergunta}</div>
            {f.status === 'pendente' && <p style={{ fontSize: 12.5, color: '#a16207' }}>Gerando resposta...</p>}
            {f.status === 'erro' && <p style={{ fontSize: 12.5, color: '#b91c1c' }}>Erro: {f.erro_mensagem}</p>}
            {f.resposta && <div className={styles.faqResposta}>{f.resposta}</div>}
            {f.pecas_relacionadas && f.pecas_relacionadas.length > 0 && (
              <div className={styles.faqFontes}>
                {f.pecas_relacionadas.map((id) => {
                  const no = nosPorId.get(id)
                  return no ? (
                    <span key={id} className={styles.keywordChip}>{no.titulo}</span>
                  ) : null
                })}
              </div>
            )}
            <div className={styles.faqActions}>
              <button className={pageStyles.btnSmall} onClick={() => reprocessar.mutate(f.id)}>
                Regerar resposta
              </button>
              <button className={pageStyles.btnDanger} onClick={() => deletar.mutate(f.id)}>
                Remover
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
