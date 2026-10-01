import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa, TIPOS_PECA } from '../api/autosIa'
import type { Caso, Documento, DocumentoDrive, DocumentoDriveAnexo, FaqPergunta, GrafoAresta, GrafoNo, Peca, PecaDetalhe, TipoPeca } from '../api/autosIa'
import ReferenciaHover from '../components/autosIa/ReferenciaHover'
import GrafoRede from '../components/autosIa/GrafoRede'
import Modal from '../components/Modal'
import pageStyles from './Page.module.css'
import { useColapsaveis } from '../utils/colapsaveis'
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
  // `data_peca` chega como "AAAA-MM-DD" (date, sem hora) — `new Date(string)`
  // nesse formato é interpretado como meia-noite em UTC pelo JS, e ao formatar
  // no fuso local (Brasil, UTC-3) isso "volta" um dia (25/09 virava 24/09 na
  // tela, mesmo com o dado certo no banco). Construir a data pelos componentes
  // ano/mês/dia usa o construtor local do JS, sem essa conversão de fuso.
  const [ano, mes, dia] = d.split('T')[0].split('-').map(Number)
  return new Date(ano, mes - 1, dia).toLocaleDateString('pt-BR')
}

// Horário de protocolo é sempre exibido em Brasília (fonte dos dados), não no
// fuso do navegador — viajando (ex.: Los Angeles, UTC-7/-8) a hora "andava"
// junto com o fuso do computador. Isso é só exibição: a ordenação das peças
// é feita no backend, a partir do instante guardado, e não muda.
const FUSO_PROTOCOLO = 'America/Sao_Paulo'

function formatarHora(d?: string | null) {
  if (!d) return null
  return new Date(d).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: FUSO_PROTOCOLO })
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
  consultando: 'Consultando jus.br/DataJud',
  conferindo: 'Conferindo documentos já salvos',
  baixando: 'Baixando documento novo do jus.br',
  lendo: 'Lendo documentos',
  resumindo: 'Resumindo peças',
  reclassificando: 'Reclassificando peças',
}

export default function AutosIACasoPage() {
  const { casoId } = useParams<{ casoId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [aba, setAba] = useState<Aba>('upload')
  const [modalExcluir, setModalExcluir] = useState(false)

  const { data: caso } = useQuery({
    queryKey: ['autos-ia', 'caso', casoId],
    queryFn: () => autosIa.obterCaso(casoId!),
    enabled: !!casoId,
    refetchInterval: (query) => (query.state.data?.ultimo_sync_status === 'processando' ? 3000 : false),
  })

  const emProcessamento = caso?.ultimo_sync_status === 'processando'

  // Enquanto uma sincronização roda, só o card de progresso (que tem sua
  // própria query) se atualiza sozinho — as abas de Documentos/Peças/Grafo
  // ficavam paradas na foto de quando a aba foi aberta, mesmo com peças
  // novas sendo criadas no banco em tempo real. Sem isso, dava a impressão
  // de sincronização travada mesmo quando ela estava avançando normalmente.
  useEffect(() => {
    if (!emProcessamento || !casoId) return
    // 15s (era 5s) e só com a aba visível: cada ciclo refaz Grafo + todas as
    // páginas já carregadas de Peças e Documentos, e o servidor do banco é
    // pequeno — o ciclo de 5s multiplicava a carga justamente durante a
    // sincronização, quando o banco já está mais exigido.
    const id = setInterval(() => {
      if (document.visibilityState !== 'visible') return
      qc.invalidateQueries({ queryKey: ['autos-ia', 'documentos-drive', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'pecas', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'grafo', casoId] })
    }, 15000)
    return () => clearInterval(id)
  }, [emProcessamento, casoId, qc])

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

  const { data: pendentesResumo } = useQuery({
    queryKey: ['autos-ia', 'pendentes-resumo', casoId],
    queryFn: () => autosIa.contarPendentesResumo(casoId!),
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

  const pularDocumentoAtual = useMutation({
    mutationFn: () => autosIa.pularDocumentoAtual(casoId!),
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

  const recalcularIds = useMutation({
    mutationFn: () => autosIa.recalcularIds(casoId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'grafo', casoId] })
    },
  })

  const resumirPendentes = useMutation({
    mutationFn: () => autosIa.resumirPendentes(casoId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] }),
  })

  const relerPendentes = useMutation({
    mutationFn: () => autosIa.relerPendentes(casoId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'caso', casoId] }),
  })

  const deletarCaso = useMutation({
    mutationFn: () => autosIa.deletarCaso(casoId!),
    onSuccess: () => navigate('/autos-ia'),
    onError: (e: any) => {
      setModalExcluir(false)
      alert(`Erro ao excluir: ${e?.response?.data?.detail || e?.message}`)
    },
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
                    <>
                      <button
                        className={pageStyles.btnSmall}
                        disabled={pularDocumentoAtual.isPending}
                        onClick={() => {
                          if (window.confirm('Pular o documento que está sendo lido agora? A sincronização continua para o próximo — o link completo do Drive fica salvo pra reler depois.')) {
                            pularDocumentoAtual.mutate()
                          }
                        }}
                        title="Pula só o documento atual (útil se for muito grande) — a sincronização segue para o próximo"
                      >
                        {pularDocumentoAtual.isPending ? 'Pulando...' : 'Pular este documento'}
                      </button>
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
                    </>
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
                      <button
                        className={pageStyles.btnSmall}
                        disabled={recalcularIds.isPending}
                        onClick={() => {
                          if (window.confirm('Corrigir o ID processual das peças já importadas usando o dado que o jus.br já entrega pronto, e reconectar referências que dependiam disso? 100% local, sem IA nem rede — não mexe em petição principal/anexos.')) {
                            recalcularIds.mutate()
                          }
                        }}
                        title="Corrige id_processual pelo documento_id real do jus.br e reconecta referências — sem IA, sem rede, sem mexer em principal/anexos"
                      >
                        {recalcularIds.isPending ? 'Recalculando...' : 'Recalcular IDs'}
                      </button>
                      {!!pendentesResumo?.pendentes && (
                        <button
                          className={pageStyles.btnSmall}
                          disabled={resumirPendentes.isPending}
                          onClick={() => {
                            if (window.confirm(`Resumir ${pendentesResumo.pendentes} peça(s) já lida(s) mas ainda sem resumo — sem consultar o jus.br nem reler nenhum documento novo. Continuar?`)) {
                              resumirPendentes.mutate()
                            }
                          }}
                          title="Só resume o que já foi lido — sem ler documentos novos"
                        >
                          {resumirPendentes.isPending ? 'Resumindo...' : `Resumir pendentes (${pendentesResumo.pendentes})`}
                        </button>
                      )}
                      <button
                        className={pageStyles.btnSmall}
                        disabled={relerPendentes.isPending}
                        onClick={() => {
                          if (window.confirm('Reler (baixar de novo do Drive + resumir de novo) TODAS as peças com falha de leitura registrada neste caso — inclui as que já viraram "resumida" mas com resumo genérico, porque a leitura original não trouxe o texto de verdade? Uma peça de cada vez, para não sobrecarregar. Pode levar alguns minutos.')) {
                            relerPendentes.mutate()
                          }
                        }}
                        title='Baixa de novo do Drive + resume de novo TODAS as peças com falha de leitura registrada — uma de cada vez'
                      >
                        {relerPendentes.isPending ? 'Relendo pendentes...' : 'Reler pendentes'}
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
                onClick={() => setModalExcluir(true)}
              >
                {deletarCaso.isPending ? 'Excluindo...' : 'Excluir caso'}
              </button>
            </div>
          )}
          {caso && modalExcluir && (
            <ModalConfirmarExclusao
              nomeCaso={caso.nome}
              isPending={deletarCaso.isPending}
              onConfirmar={() => deletarCaso.mutate()}
              onClose={() => setModalExcluir(false)}
            />
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

const CONFIRMACAO_EXCLUSAO = 'DELETAR'

function ModalConfirmarExclusao({
  nomeCaso, isPending, onConfirmar, onClose,
}: { nomeCaso: string; isPending: boolean; onConfirmar: () => void; onClose: () => void }) {
  const [texto, setTexto] = useState('')
  const confirmado = texto.trim() === CONFIRMACAO_EXCLUSAO

  return (
    <Modal title="Excluir caso" onClose={onClose}>
      <p style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 12 }}>
        Excluir <strong>"{nomeCaso}"</strong>? Apaga todas as peças, o grafo e as perguntas já
        indexadas — todo o custo e tempo de leitura já gastos nesse caso se perdem, e não pode ser desfeito.
      </p>
      <p style={{ fontSize: 12.5, marginBottom: 6 }}>
        Digite <strong>{CONFIRMACAO_EXCLUSAO}</strong> para confirmar:
      </p>
      <input
        className={pageStyles.input}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder={CONFIRMACAO_EXCLUSAO}
        autoFocus
      />
      <div style={{ display: 'flex', gap: 8, marginTop: 14, justifyContent: 'flex-end' }}>
        <button className={pageStyles.btnSmall} onClick={onClose}>Cancelar</button>
        <button
          className={pageStyles.btnDanger}
          disabled={!confirmado || isPending}
          onClick={onConfirmar}
        >
          {isPending ? 'Excluindo...' : 'Excluir definitivamente'}
        </button>
      </div>
    </Modal>
  )
}

function SyncProgress({ caso }: { caso: Caso }) {
  const agora = useNow(1000)

  const total = caso.sync_total_itens ?? 0
  const feito = caso.sync_itens_processados ?? 0
  const pct = total > 0 ? Math.min(100, Math.round((feito / total) * 100)) : 0
  const inicioMs = caso.sync_iniciado_em ? new Date(caso.sync_iniciado_em).getTime() : null

  // Marca quando "feito" mudou pela última vez — o ritmo médio real (do que já
  // foi processado) dá a base pra estimar o progresso do documento ATUAL.
  const ultimaMudancaRef = useRef({ feito, em: agora })
  if (ultimaMudancaRef.current.feito !== feito) {
    ultimaMudancaRef.current = { feito, em: agora }
  }

  let eta = ''
  if (inicioMs && pct >= 3) {
    const elapsedMs = agora - inicioMs
    const restanteMs = Math.max(0, elapsedMs / (pct / 100) - elapsedMs)
    const min = Math.round(restanteMs / 60000)
    eta = min < 1 ? '< 1 min restante' : `~${min} min restante`
  }

  // Barra secundária: sobe segundo a segundo com base no ritmo médio real —
  // distingue "só demorando" (sobe, estabiliza perto de 95-97% e espera o
  // próximo) de "travado de verdade" (fica parada ali por muito mais tempo
  // que a média do que já foi processado até agora).
  let pctDocumentoAtual: number | null = null
  if (inicioMs && feito > 0 && feito < total) {
    const ritmoMedioMs = (ultimaMudancaRef.current.em - inicioMs) / feito
    if (ritmoMedioMs > 0) {
      const decorridoDesdeUltimo = agora - ultimaMudancaRef.current.em
      pctDocumentoAtual = Math.min(97, Math.round((decorridoDesdeUltimo / ritmoMedioMs) * 100))
    }
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
      {caso.sync_detalhe && (
        <div style={{ fontSize: 11, color: 'var(--gray-mid)', marginTop: 5, fontStyle: 'italic' }}>
          {caso.sync_detalhe}
        </div>
      )}
      {pctDocumentoAtual != null && (
        <>
          <div style={{ fontSize: 10, color: 'var(--gray-mid)', marginTop: 5 }}>
            Documento atual (estimado pelo ritmo médio)
          </div>
          <div className={styles.progressBarSecundaria}>
            <div className={styles.progressFillSecundaria} style={{ width: `${pctDocumentoAtual}%` }} />
          </div>
        </>
      )}
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
            placeholder="Buscar por tema, palavra-chave ou ID (ex.: prescrição, honorários, Evento 45...)"
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

/** Busca rápida de outra peça-mãe do caso pra virar o "anexar a" manual —
 * correção pro agrupamento automático não conseguir juntar duas peças que
 * ficaram longe demais em hora de protocolo, ou não bater na classificação. */
function AnexarAPicker({
  casoId, pecaId, onConfirmar, onCancelar,
}: { casoId: string; pecaId: string; onConfirmar: (alvoId: string) => void; onCancelar: () => void }) {
  const [termo, setTermo] = useState('')
  const { data, isFetching } = useQuery({
    queryKey: ['autos-ia', 'documentos-drive', 'busca-anexar', casoId, termo],
    queryFn: () => autosIa.listarDocumentosDrive(casoId, { q: termo, ordem: 'desc', limit: 8 }),
    enabled: termo.trim().length >= 3,
  })
  const candidatos = (data ?? []).filter((d) => d.id !== pecaId)

  return (
    <div className={styles.anexarPicker}>
      <input
        className={pageStyles.input}
        placeholder="Buscar peça pra anexar (mín. 3 letras)..."
        value={termo}
        onChange={(e) => setTermo(e.target.value)}
        autoFocus
      />
      {isFetching && <p style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Buscando...</p>}
      {termo.trim().length >= 3 && !isFetching && candidatos.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Nenhuma peça encontrada.</p>
      )}
      {candidatos.map((c) => (
        <button
          key={c.id}
          type="button"
          className={styles.anexarPickerItem}
          onClick={() => onConfirmar(c.id)}
        >
          <strong>{c.titulo_customizado || c.titulo}</strong>
          {c.arquivo_nome && <span> — {c.arquivo_nome}</span>}
        </button>
      ))}
      <button type="button" className={styles.docTogglePeticao} onClick={onCancelar}>Cancelar</button>
    </div>
  )
}

function LinhaDocumento({ doc, nivel, casoId }: { doc: DocumentoDrive | DocumentoDriveAnexo; nivel: number; casoId: string }) {
  const qc = useQueryClient()
  const anexos = 'anexos' in doc ? doc.anexos : []
  const { estaAberto, alternar } = useColapsaveis(casoId)
  const aberto = estaAberto(`doc:${doc.id}`)
  const [resumoAberto, setResumoAberto] = useState(false)
  const [editando, setEditando] = useState(false)
  const [anexandoAberto, setAnexandoAberto] = useState(false)
  const [rascunhoTitulo, setRascunhoTitulo] = useState(doc.titulo_customizado ?? '')
  const [rascunhoNota, setRascunhoNota] = useState(doc.nota_usuario ?? '')
  const [rascunhoKeywords, setRascunhoKeywords] = useState((doc.keywords_usuario ?? []).join(', '))
  const [rascunhoAdvogado, setRascunhoAdvogado] = useState(doc.advogado_responsavel ?? '')
  // Sugestões dos nomes já usados no caso (só busca quando o painel de edição abre).
  const { data: advogadosSugeridos } = useQuery({
    queryKey: ['autos-ia', 'advogados', casoId],
    queryFn: () => autosIa.listarAdvogadosResponsaveis(casoId),
    enabled: editando,
    staleTime: 60_000,
  })
  const temAnexos = anexos.length > 0
  const ehPeticao = doc.tipo === 'peticao'
  const temResumo = !!doc.resumo
  const nomeOriginal = doc.nome_indexado || doc.titulo
  const ehAnexo = nivel > 0
  // Um tick = arquivo baixado; dois = baixado E já lido (resumo gerado). Ler
  // implica ter o arquivo, mesmo que o link do Drive ainda não tenha sido gravado.
  const lido = doc.status === 'resumida' && !doc.erro_mensagem
  const baixado = lido || !!doc.arquivo_drive_link

  const invalidarDocumentos = () => {
    qc.invalidateQueries({ queryKey: ['autos-ia', 'documentos-drive', casoId] })
    qc.invalidateQueries({ queryKey: ['autos-ia', 'grafo', casoId] })
    qc.invalidateQueries({ queryKey: ['autos-ia', 'pecas', casoId] })
  }

  const marcarTipo = useMutation({
    mutationFn: (tipo: TipoPeca) => autosIa.atualizarTipoPeca(doc.id, tipo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['autos-ia', 'documentos-drive', casoId] }),
  })

  const tornarPrincipal = useMutation({
    mutationFn: () => autosIa.tornarPrincipal(doc.id),
    onSuccess: invalidarDocumentos,
  })

  const desvincular = useMutation({
    mutationFn: () => autosIa.desvincularPeca(doc.id),
    onSuccess: invalidarDocumentos,
  })

  const anexarA = useMutation({
    mutationFn: (alvoId: string) => autosIa.anexarA(doc.id, alvoId),
    onSuccess: () => {
      invalidarDocumentos()
      setAnexandoAberto(false)
    },
  })

  const reler = useMutation({
    mutationFn: () => autosIa.relerPeca(doc.id),
    onSuccess: () => {
      // A releitura roda em segundo plano (download + IA) — sem polling
      // dedicado pra essa única peça, o "Relendo..." nunca saía da tela
      // sozinho. Não é elegante, mas cobre o caso comum (poucos segundos).
      invalidarDocumentos()
      setTimeout(invalidarDocumentos, 5000)
      setTimeout(invalidarDocumentos, 12000)
    },
    onError: (e: any) => alert(`Erro ao reler: ${e?.response?.data?.detail || e?.message}`),
  })

  const salvarAnotacao = useMutation({
    mutationFn: () => autosIa.atualizarAnotacaoPeca(doc.id, {
      titulo_customizado: rascunhoTitulo.trim() || null,
      nota_usuario: rascunhoNota.trim() || null,
      keywords_usuario: rascunhoKeywords.trim()
        ? rascunhoKeywords.split(',').map((k) => k.trim()).filter(Boolean)
        : null,
      advogado_responsavel: rascunhoAdvogado.trim() || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['autos-ia', 'documentos-drive', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'grafo', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'advogados', casoId] })
      setEditando(false)
    },
  })

  return (
    <div className={styles.docItem}>
      <div className={ehPeticao ? styles.docBlocoPeticao : undefined}>
        <div className={styles.docRow} style={{ paddingLeft: nivel * 22 }}>
          {temAnexos ? (
            <button
              type="button"
              className={styles.docChevron}
              onClick={() => alternar(`doc:${doc.id}`)}
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
          {lido ? (
            <span className={`${styles.docTicks} ${styles.docTicksLido}`} title="Baixado e lido" aria-label="Baixado e lido">✓✓</span>
          ) : baixado ? (
            <span className={styles.docTicks} title="Baixado (ainda não lido)" aria-label="Baixado, ainda não lido">✓</span>
          ) : (
            <span className={styles.docTicks} />
          )}
          <span
            className={[
              styles.docNomeIndexado,
              ehPeticao ? styles.docNomeIndexadoPeticao : '',
              doc.titulo_customizado ? styles.docNomeCustomizado : '',
            ].join(' ')}
            title={doc.titulo_customizado ? `Nome editado por você (original: ${nomeOriginal})` : undefined}
          >
            {doc.titulo_customizado || nomeOriginal}
          </span>
          <button
            type="button"
            className={styles.docEditarBtn}
            onClick={() => setEditando(!editando)}
            aria-expanded={editando}
            title="Editar nome, nota e palavras-chave"
          >
            ✎
          </button>
          {ehPeticao && (
            <button
              type="button"
              className={styles.docResumoBtn}
              disabled={!temResumo}
              onClick={() => setResumoAberto(!resumoAberto)}
              aria-expanded={resumoAberto}
              title={temResumo ? 'Ver resumo desta petição' : 'Ainda sem leitura a fundo desta petição'}
            >
              ?
            </button>
          )}
          <span className={styles.tipoBadge}>{doc.tipo}</span>
          {doc.erro_mensagem && <span className={styles.docAvisoLeitura} title={doc.erro_mensagem}>⚠</span>}
          {doc.erro_mensagem && (
            <button
              type="button"
              className={styles.docTogglePeticao}
              disabled={reler.isPending || doc.status === 'pendente_resumo'}
              onClick={() => reler.mutate()}
              title="Baixa o arquivo de novo do Drive e gera um resumo novo — só esta peça"
            >
              {reler.isPending || doc.status === 'pendente_resumo' ? 'Relendo...' : 'Reler documento'}
            </button>
          )}
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
          {ehAnexo ? (
            <>
              <button
                type="button"
                className={styles.docTogglePeticao}
                disabled={tornarPrincipal.isPending}
                onClick={() => tornarPrincipal.mutate()}
                title="Fazer desta peça o principal do grupo — o principal atual e os demais anexos passam a ficar embaixo dela"
              >
                Tornar principal
              </button>
              <button
                type="button"
                className={styles.docTogglePeticao}
                disabled={desvincular.isPending}
                onClick={() => desvincular.mutate()}
                title="Desfazer o vínculo de anexo — volta a ser uma peça própria, independente"
              >
                Desvincular
              </button>
            </>
          ) : (
            <button
              type="button"
              className={styles.docTogglePeticao}
              onClick={() => setAnexandoAberto(!anexandoAberto)}
              aria-expanded={anexandoAberto}
              title="Vincular manualmente esta peça como anexo de outra — pro agrupamento automático não ter juntado as duas"
            >
              Anexar a...
            </button>
          )}
        </div>
        {anexandoAberto && (
          <div style={{ paddingLeft: nivel * 22 + 22, marginTop: 4 }}>
            <AnexarAPicker
              casoId={casoId}
              pecaId={doc.id}
              onConfirmar={(alvoId) => anexarA.mutate(alvoId)}
              onCancelar={() => setAnexandoAberto(false)}
            />
          </div>
        )}
        <div className={styles.docRowSub} style={{ paddingLeft: nivel * 22 + 22 }}>
          {doc.titulo_customizado && <span className={styles.docNomeOriginal}>original: {nomeOriginal}</span>}
          {doc.id_processual && <span className={styles.docIdProcessual}>ID: {doc.id_processual}</span>}
          {doc.arquivo_nome && <span className={styles.docArquivoNome}>{doc.arquivo_nome}</span>}
          {doc.resumo && <span className={styles.docResumo}>{doc.resumo}</span>}
          {doc.nota_usuario && <span className={styles.docNotaUsuario}>{doc.nota_usuario}</span>}
          {((doc.keywords_usuario?.length ?? 0) > 0 || doc.advogado_responsavel) && (
            <div className={styles.docChipsLinha}>
              {doc.advogado_responsavel && (
                <span className={styles.chipAdvogado} title="Advogado responsável">⚖ {doc.advogado_responsavel}</span>
              )}
              {doc.keywords_usuario?.map((k) => <span key={k} className={styles.chipManual}>{k}</span>)}
            </div>
          )}
        </div>
        {resumoAberto && temResumo && (
          <div className={styles.docResumoPopup} style={{ left: nivel * 22 + 22 }} role="dialog">
            {doc.resumo}
          </div>
        )}
        {editando && (
          <div className={styles.docEditarPainel} style={{ marginLeft: nivel * 22 + 22 }}>
            <input
              className={pageStyles.input}
              placeholder={`Nome customizado (original: ${nomeOriginal})`}
              value={rascunhoTitulo}
              onChange={(e) => setRascunhoTitulo(e.target.value)}
            />
            <textarea
              className={pageStyles.input}
              placeholder="Minha nota sobre este andamento..."
              rows={2}
              value={rascunhoNota}
              onChange={(e) => setRascunhoNota(e.target.value)}
            />
            <input
              className={pageStyles.input}
              placeholder="Palavras-chave, separadas por vírgula"
              value={rascunhoKeywords}
              onChange={(e) => setRascunhoKeywords(e.target.value)}
            />
            <input
              className={pageStyles.input}
              placeholder="Advogado responsável"
              list={`advogados-${doc.id}`}
              maxLength={255}
              value={rascunhoAdvogado}
              onChange={(e) => setRascunhoAdvogado(e.target.value)}
            />
            <datalist id={`advogados-${doc.id}`}>
              {(advogadosSugeridos ?? []).map((n) => <option key={n} value={n} />)}
            </datalist>
            <div className={styles.docEditarAcoes}>
              <button
                type="button"
                className={pageStyles.btnSmall}
                disabled={salvarAnotacao.isPending}
                onClick={() => salvarAnotacao.mutate()}
              >
                {salvarAnotacao.isPending ? 'Salvando...' : 'Salvar'}
              </button>
              <button type="button" className={styles.docTogglePeticao} onClick={() => setEditando(false)}>
                Cancelar
              </button>
            </div>
          </div>
        )}
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
  const [ordem, setOrdem] = useState<'asc' | 'desc'>('desc')

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['autos-ia', 'documentos-drive', casoId, q, ordem],
    queryFn: ({ pageParam }) => autosIa.listarDocumentosDrive(casoId, {
      q: q || undefined, ordem, offset: pageParam, limit: TAMANHO_PAGINA_DOCUMENTOS,
    }),
    initialPageParam: 0,
    getNextPageParam: (ultimaPagina, todasPaginas) =>
      ultimaPagina.length === TAMANHO_PAGINA_DOCUMENTOS ? todasPaginas.length * TAMANHO_PAGINA_DOCUMENTOS : undefined,
    enabled: vinculadoAProcesso,
  })
  const documentos = data?.pages.flat() ?? []
  const { recolherTodos, expandirTodos } = useColapsaveis(casoId)

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
          placeholder="Buscar por nome, ID, nota, palavra-chave ou advogado..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button
          type="button"
          className={pageStyles.btnSmall}
          onClick={() => setOrdem(ordem === 'desc' ? 'asc' : 'desc')}
          title="Alternar ordem cronológica"
        >
          {ordem === 'desc' ? '↓ Mais novas primeiro' : '↑ Mais antigas primeiro'}
        </button>
        <button
          type="button"
          className={pageStyles.btnSmall}
          onClick={() => recolherTodos('doc')}
          title="Recolhe os anexos de todas as peças (fica salvo ao sair da tela)"
        >
          ▸ Recolher tudo
        </button>
        <button
          type="button"
          className={pageStyles.btnSmall}
          onClick={() => expandirTodos('doc')}
        >
          ▾ Expandir tudo
        </button>
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
  const qc = useQueryClient()
  const { data: grafo, isLoading } = useQuery({
    queryKey: ['autos-ia', 'grafo', casoId],
    queryFn: () => autosIa.obterGrafo(casoId),
  })

  if (isLoading) return <p className={pageStyles.empty}>Carregando...</p>
  if (!grafo || grafo.nos.length === 0) return <p className={pageStyles.empty}>Nenhuma peça indexada ainda.</p>

  const onRelido = () => {
    // Releitura roda em segundo plano — sem polling dedicado a essa peça,
    // agenda mais duas invalidações pra pegar o resultado sem precisar
    // a pessoa recarregar a página manualmente (mesmo padrão da aba Documentos).
    const invalidar = () => {
      qc.invalidateQueries({ queryKey: ['autos-ia', 'grafo', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'documentos-drive', casoId] })
      qc.invalidateQueries({ queryKey: ['autos-ia', 'pecas', casoId] })
    }
    invalidar()
    setTimeout(invalidar, 5000)
    setTimeout(invalidar, 12000)
  }

  return <GrafoRede nos={grafo.nos} arestas={grafo.arestas} onRelido={onRelido} />
}

// ── FAQ ──────────────────────────────────────────────────────────────────

function AbaFaq({ casoId, nosPorId }: { casoId: string; nosPorId: NosMap }) {
  const qc = useQueryClient()
  const [pergunta, setPergunta] = useState('')
  const { recolherTodos, expandirTodos } = useColapsaveis(casoId)

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
        <>
        <div className={styles.filtrosRow} style={{ marginBottom: 8 }}>
          <button
            type="button"
            className={pageStyles.btnSmall}
            onClick={() => recolherTodos('faq')}
            title="Recolhe todas as respostas (fica salvo ao sair da tela)"
          >
            ▸ Recolher tudo
          </button>
          <button type="button" className={pageStyles.btnSmall} onClick={() => expandirTodos('faq')}>
            ▾ Expandir tudo
          </button>
        </div>
        {perguntas.map((f) => (
          <FaqCard
            key={f.id}
            casoId={casoId}
            pergunta={f}
            nosPorId={nosPorId}
            onReprocessar={() => reprocessar.mutate(f.id)}
            onDeletar={() => deletar.mutate(f.id)}
          />
        ))}
        </>
      )}
    </div>
  )
}

function FaqCard({
  casoId, pergunta: f, nosPorId, onReprocessar, onDeletar,
}: { casoId: string; pergunta: FaqPergunta; nosPorId: NosMap; onReprocessar: () => void; onDeletar: () => void }) {
  const { estaAberto, alternar } = useColapsaveis(casoId)
  const aberto = estaAberto(`faq:${f.id}`)

  return (
    <div className={styles.faqCard}>
      <button
        type="button"
        className={styles.faqPerguntaBtn}
        onClick={() => alternar(`faq:${f.id}`)}
        aria-expanded={aberto}
      >
        <span className={styles.faqPergunta}>{f.pergunta}</span>
        <span className={styles.faqToggle}>
          {f.custo_usd > 0 && <span className={styles.faqCusto}>{formatarUsd(f.custo_usd)}</span>}
          {aberto ? '▾ Retrair' : '▸ Expandir'}
        </span>
      </button>
      {aberto && (
        <>
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
            <button className={pageStyles.btnSmall} onClick={onReprocessar}>
              Regerar resposta
            </button>
            <button className={pageStyles.btnDanger} onClick={onDeletar}>
              Remover
            </button>
          </div>
        </>
      )}
    </div>
  )
}
