import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { diarioApi } from '../api/diario'
import type { AnaliseIA, DiarioSyncJobStatus, OabMonitorada, Publicacao, TipoAto } from '../api/diario'
import { processosApi } from '../api/processos'
import type { Processo } from '../api/processos'
import { clientesApi } from '../api/clientes'
import type { Cliente } from '../api/clientes'
import styles from './Page.module.css'
import diarioStyles from './DiarioPage.module.css'

// Tribunais de Justiça estaduais por UF — todos lidos da base nacional do DJEN/Comunica.
// Selecionar estados apenas filtra a consulta nacional; nenhum estado = DJEN nacional (todos).
const ESTADOS_BR: { uf: string; nome: string; sigla: string }[] = [
  { uf: 'AC', nome: 'Acre', sigla: 'TJAC' },
  { uf: 'AL', nome: 'Alagoas', sigla: 'TJAL' },
  { uf: 'AP', nome: 'Amapá', sigla: 'TJAP' },
  { uf: 'AM', nome: 'Amazonas', sigla: 'TJAM' },
  { uf: 'BA', nome: 'Bahia', sigla: 'TJBA' },
  { uf: 'CE', nome: 'Ceará', sigla: 'TJCE' },
  { uf: 'DF', nome: 'Distrito Federal', sigla: 'TJDFT' },
  { uf: 'ES', nome: 'Espírito Santo', sigla: 'TJES' },
  { uf: 'GO', nome: 'Goiás', sigla: 'TJGO' },
  { uf: 'MA', nome: 'Maranhão', sigla: 'TJMA' },
  { uf: 'MT', nome: 'Mato Grosso', sigla: 'TJMT' },
  { uf: 'MS', nome: 'Mato Grosso do Sul', sigla: 'TJMS' },
  { uf: 'MG', nome: 'Minas Gerais', sigla: 'TJMG' },
  { uf: 'PA', nome: 'Pará', sigla: 'TJPA' },
  { uf: 'PB', nome: 'Paraíba', sigla: 'TJPB' },
  { uf: 'PR', nome: 'Paraná', sigla: 'TJPR' },
  { uf: 'PE', nome: 'Pernambuco', sigla: 'TJPE' },
  { uf: 'PI', nome: 'Piauí', sigla: 'TJPI' },
  { uf: 'RJ', nome: 'Rio de Janeiro', sigla: 'TJRJ' },
  { uf: 'RN', nome: 'Rio Grande do Norte', sigla: 'TJRN' },
  { uf: 'RS', nome: 'Rio Grande do Sul', sigla: 'TJRS' },
  { uf: 'RO', nome: 'Rondônia', sigla: 'TJRO' },
  { uf: 'RR', nome: 'Roraima', sigla: 'TJRR' },
  { uf: 'SC', nome: 'Santa Catarina', sigla: 'TJSC' },
  { uf: 'SP', nome: 'São Paulo', sigla: 'TJSP' },
  { uf: 'SE', nome: 'Sergipe', sigla: 'TJSE' },
  { uf: 'TO', nome: 'Tocantins', sigla: 'TJTO' },
]
const SIGLA_PARA_UF: Record<string, string> = Object.fromEntries(ESTADOS_BR.map((e) => [e.sigla, e.uf]))

const PERIODOS_FILTRO: { label: string; dias: number | null }[] = [
  { label: 'Todo período', dias: null },
  { label: 'Últimos 7 dias', dias: 7 },
  { label: 'Últimos 15 dias', dias: 15 },
  { label: 'Últimos 30 dias', dias: 30 },
  { label: 'Últimos 90 dias', dias: 90 },
]

const FONTE_LABEL: Record<string, string> = {
  gmail: 'Gmail',
  scraping_tjes: 'TJES',
  scraping_tjsp: 'TJSP',
  scraping_tjam: 'TJAM',
  scraping_tjrj: 'TJRJ',
  scraping_djen: 'DJEN',
  pje_comunica: 'PJe Comunica',
  manual: 'Manual',
}

const TIPO_CORES: Record<TipoAto, string> = {
  sentenca:   diarioStyles.tipoSentenca,
  acordao:    diarioStyles.tipoAcordao,
  decisao:    diarioStyles.tipoDecisao,
  intimacao:  diarioStyles.tipoIntimacao,
  citacao:    diarioStyles.tipoCitacao,
  despacho:   diarioStyles.tipoDespacho,
  outro:      diarioStyles.tipoOutro,
}

function formatDate(d?: string) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

type MatchFilter = 'todos' | 'cadastrados' | 'exatos'
type DiarioEstadoFiltro = 'abertas' | 'tratadas' | 'rejeitadas' | 'todas'
type MatchKind = 'processo' | 'exato'

interface ProcessoRelacionado {
  id: string
  numero_cnj: string
  clienteNomes: string[]
  matchKind: MatchKind
}

interface PublicacaoMatchInfo {
  exactClientNames: string[]
  exactTermMatches: string[]
  probableClientNames: string[]
  // Nomes de clientes derivados de um processo cadastrado (match por CNJ) — vínculo confiável.
  linkedClientNames: string[]
  relatedProcesses: ProcessoRelacionado[]
  relatedTerms: string[]
  primaryProcessId?: string
  primaryClientName?: string
  hasRegisteredProcess: boolean
  hasExactName: boolean
  // Veio da busca por OAB monitorada (ex.: "14477/ES") — match forte.
  hasOabMatch: boolean
  oabMatch?: string
}

interface PublicacaoEnriquecida {
  pub: Publicacao
  match: PublicacaoMatchInfo
}

function normalizeText(value: string) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

function normalizeDigits(value: string) {
  return value.replace(/\D/g, '')
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function uniqueStrings(values: string[]) {
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values) {
    const cleaned = value.trim()
    const key = cleaned.toLocaleLowerCase()
    if (!cleaned || seen.has(key)) continue
    seen.add(key)
    result.push(cleaned)
  }
  return result
}

function extractRelevantTokens(name: string) {
  return uniqueStrings(name.match(/[A-Za-zÀ-ÿ0-9]+/g) ?? [])
    .map((token) => normalizeText(token))
    .filter((token) => token.length >= 4 && !['ltda', 'advogados', 'advocacia', 'sociedade'].includes(token))
}

function looksLikeCnj(value: string) {
  return normalizeDigits(value).length === 20
}

function isMonitorableTerm(value: string) {
  if (looksLikeCnj(value)) return true
  const tokens = extractRelevantTokens(value)
  if (tokens.length >= 2) return true
  return tokens.length === 1 && tokens[0].length >= 8
}

function textHasExactTerm(normalizedText: string, term: string) {
  const normalizedTerm = normalizeText(term)
  if (!normalizedTerm) return false
  const pattern = `(^|[^a-z0-9])${escapeRegExp(normalizedTerm).replace(/\ /g, '\\s+')}(?=$|[^a-z0-9])`
  return new RegExp(pattern, 'i').test(normalizedText)
}

function buildRelevantExcerpt(text: string, terms: string[], radius = 220) {
  const source = text.trim()
  if (!source) return ''

  const lower = source.toLowerCase()
  for (const term of uniqueStrings(terms).sort((a, b) => b.length - a.length)) {
    const idx = lower.indexOf(term.toLowerCase())
    if (idx < 0) continue
    const start = Math.max(0, idx - radius)
    const end = Math.min(source.length, idx + term.length + radius)
    const prefix = start > 0 ? '... ' : ''
    const suffix = end < source.length ? ' ...' : ''
    return `${prefix}${source.slice(start, end).trim()}${suffix}`
  }

  return source.slice(0, radius * 2)
}

function getProcessClientNames(processo: Processo, clientes: Cliente[]) {
  const byId = new Map(clientes.map((cliente) => [cliente.id, cliente.nome]))
  const names = [
    byId.get(processo.cliente_id) ?? '',
    ...(processo.clientes_litisconsorcio?.map((cliente) => cliente.nome ?? '') ?? []),
  ]
  return uniqueStrings(names)
}

function classifyPublication(
  pub: Publicacao,
  processos: Processo[],
  clientes: Cliente[],
  termosMonitorados: string[],
): PublicacaoMatchInfo {
  const text = `${pub.texto_completo ?? ''} ${pub.texto_resumo ?? ''}`
  const normalizedText = normalizeText(text)
  const exactClientNames = new Set<string>()
  const exactTermMatches = new Set<string>()
  const probableClientNames = new Set<string>()
  const relatedTerms = new Set<string>()
  const relatedProcesses: ProcessoRelacionado[] = []

  for (const processo of processos) {
    const processDigits = normalizeDigits(processo.numero_cnj)
    const clientNames = getProcessClientNames(processo, clientes)

    const processMatched =
      pub.processo_id === processo.id ||
      (!!pub.numero_cnj && normalizeDigits(pub.numero_cnj) === processDigits)

    if (processMatched) {
      relatedTerms.add(processo.numero_cnj)
      relatedProcesses.push({
        id: processo.id,
        numero_cnj: processo.numero_cnj,
        clienteNomes: clientNames,
        matchKind: 'processo',
      })
      clientNames.forEach((name) => {
        probableClientNames.add(name)
      })
    }

    const exactNames = clientNames.filter((name) => isMonitorableTerm(name) && textHasExactTerm(normalizedText, name))
    if (exactNames.length > 0) {
      exactNames.forEach((name) => {
        exactClientNames.add(name)
        exactTermMatches.add(name)
        probableClientNames.add(name)
        relatedTerms.add(name)
      })
      continue
    }
  }

  relatedProcesses.sort((a, b) => {
    const rank = { processo: 0, exato: 1 }
    return rank[a.matchKind] - rank[b.matchKind]
  })

  const hasRegisteredProcess = relatedProcesses.some((processo) => processo.matchKind === 'processo')
  const primary = relatedProcesses[0]

  for (const termo of termosMonitorados) {
    const normalizedTerm = normalizeText(termo)
    if (!normalizedTerm) continue
    if (!isMonitorableTerm(termo)) continue
    if (textHasExactTerm(normalizedText, termo)) {
      exactTermMatches.add(termo)
      relatedTerms.add(termo)
      continue
    }
  }

  if (primary?.numero_cnj) relatedTerms.add(primary.numero_cnj)

  const oabMatch = (pub.match_oab ?? '').trim()
  // Cliente confiável só quando vem de um processo cadastrado (match por CNJ).
  const linkedClientNames = uniqueStrings(relatedProcesses.flatMap((p) => p.clienteNomes))

  return {
    exactClientNames: [...exactClientNames],
    exactTermMatches: [...exactTermMatches],
    probableClientNames: [...probableClientNames],
    linkedClientNames,
    relatedProcesses,
    relatedTerms: uniqueStrings([...relatedTerms]),
    primaryProcessId: primary?.id,
    primaryClientName: primary?.clienteNomes[0] ?? [...probableClientNames][0],
    hasRegisteredProcess,
    hasExactName: exactClientNames.size > 0 || exactTermMatches.size > 0,
    hasOabMatch: oabMatch.length > 0,
    oabMatch: oabMatch || undefined,
  }
}

function buildHighlightedHtml(text: string, terms: string[]) {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  const normalizedTerms = uniqueStrings(terms)
    .filter((term) => term.trim().length >= 3)
    .sort((a, b) => b.length - a.length)

  if (normalizedTerms.length === 0) return escaped

  const pattern = normalizedTerms.map(escapeRegExp).join('|')
  const regex = new RegExp(`(${pattern})`, 'gi')
  return escaped.replace(regex, '<strong class="diario-highlight">$1</strong>')
}

export default function DiarioPage() {
  const qc = useQueryClient()
  const [expandido, setExpandido] = useState<string | null>(null)
  const [vincularId, setVincularId] = useState<string | null>(null)
  const [processoSelecionado, setProcessoSelecionado] = useState('')
  const [filtroEstado, setFiltroEstado] = useState<DiarioEstadoFiltro>('abertas')
  const [filtroComConteudo, setFiltroComConteudo] = useState(false)
  const [filtroMatch, setFiltroMatch] = useState<MatchFilter>('todos')
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [syncJobId, setSyncJobId] = useState<string | null>(null)
  const [syncJobLabel, setSyncJobLabel] = useState<string | null>(null)
  const [acaoMsg, setAcaoMsg] = useState<Record<string, string>>({})
  const [daysBack, setDaysBack] = useState(3)
  const [termosCustom, setTermosCustom] = useState<string[]>([])
  const [novoTermo, setNovoTermo] = useState('')
  const [oabs, setOabs] = useState<OabMonitorada[]>([])
  const [novaOabNumero, setNovaOabNumero] = useState('')
  const [novaOabUf, setNovaOabUf] = useState('')
  const [_termosAberto, _setTermosAberto] = useState(false)
  // Estados (siglas de tribunal) escolhidos para sincronizar. Vazio = DJEN nacional (todos).
  const [estadosSync, setEstadosSync] = useState<string[]>([])
  const [estadosAberto, setEstadosAberto] = useState(false)
  // Filtros do feed
  const [filtroPeriodoDias, setFiltroPeriodoDias] = useState<number | null>(null)
  const [buscaCliente, setBuscaCliente] = useState('')
  const [filtroTribunal, setFiltroTribunal] = useState('')
  const [buscaMonitorCliente, setBuscaMonitorCliente] = useState('')


  const parseAnalise = (pub: { analise_ia?: string }): AnaliseIA | null => {
    if (!pub.analise_ia) return null
    try { return JSON.parse(pub.analise_ia) } catch { return null }
  }

  const filtroPublicacoes =
    filtroEstado === 'abertas'
      ? { lida: false, rejeitada: false }
      : filtroEstado === 'tratadas'
        ? { lida: true, rejeitada: false }
        : filtroEstado === 'rejeitadas'
          ? { rejeitada: true }
          : {}

  const { data: publicacoes = [], isLoading } = useQuery({
    queryKey: ['diario', filtroEstado],
    queryFn: () => diarioApi.listar(filtroPublicacoes),
  })

  const { data: syncJob } = useQuery<DiarioSyncJobStatus>({
    queryKey: ['diario-sync-job', syncJobId],
    queryFn: () => diarioApi.syncScrapingStatus(syncJobId!),
    enabled: !!syncJobId,
    refetchInterval: syncJobId ? 1000 : false,
  })

  useEffect(() => {
    if (!syncJob || (syncJob.status !== 'concluido' && syncJob.status !== 'erro')) return
    qc.invalidateQueries({ queryKey: ['diario'] })
    const label = syncJobLabel ?? syncJob.tribunais.join(', ')
    if (syncJob.status === 'concluido') {
      setSyncMsg(
        `${label}: ${syncJob.inseridas} novas, ${syncJob.duplicatas} já existentes, ${syncJob.erros} erros`,
      )
    } else {
      setSyncMsg(`${label}: falha na leitura. ${syncJob.error ?? ''}`.trim())
    }
    setSyncJobId(null)
    setSyncJobLabel(null)
    setTimeout(() => setSyncMsg(null), 9000)
  }, [qc, syncJob, syncJobLabel])

  const { data: googleStatus } = useQuery({
    queryKey: ['google-status'],
    queryFn: () => diarioApi.googleStatus(),
    refetchInterval: 10000,
  })

  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  // Só clientes marcados para monitoramento entram na busca por nome — evita ruído de homônimo.
  const clientesMonitorados = clientes.filter((c) => c.monitorar_diario)
  const nomesClientesMonitorados = clientesMonitorados.map((c) => c.nome)

  const { data: monitoramento } = useQuery({
    queryKey: ['diario-monitoramento'],
    queryFn: () => diarioApi.monitoramento(),
  })

  useEffect(() => {
    if (monitoramento) {
      setTermosCustom(monitoramento.termos_extras ?? [])
      setOabs(monitoramento.oabs ?? [])
    }
  }, [monitoramento])

  const syncGmail = useMutation({
    mutationFn: () => diarioApi.syncGmail(daysBack),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      setSyncMsg(`Gmail: ${r.inseridas} novas, ${r.duplicatas} duplicatas`)
      setTimeout(() => setSyncMsg(null), 5000)
    },
  })

  const termosNomesMonitorados = [...nomesClientesMonitorados, ...termosCustom].filter(Boolean)

  const salvarMonitoramento = useMutation({
    mutationFn: (payload: { termos_extras?: string[]; oabs?: OabMonitorada[] }) =>
      diarioApi.salvarMonitoramento({
        tribunais: monitoramento?.tribunais?.length ? monitoramento.tribunais : ['TJES', 'TJSP', 'TJAM'],
        auto_sync: monitoramento?.auto_sync ?? true,
        termos_extras: payload.termos_extras ?? termosCustom,
        oabs: payload.oabs ?? oabs,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['diario-monitoramento'] })
      setTermosCustom(data.termos_extras ?? [])
      setOabs(data.oabs ?? [])
    },
  })

  const toggleMonitorarCliente = useMutation({
    mutationFn: ({ id, monitorar_diario }: { id: string; monitorar_diario: boolean }) =>
      clientesApi.atualizar(id, { monitorar_diario }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clientes'] }),
  })

  const syncScraping = useMutation({
    mutationFn: ({ tribunais, label }: { tribunais: string[]; label: string }) =>
      diarioApi.iniciarSyncScraping(tribunais, daysBack).then((r) => ({ ...r, label })),
    onSuccess: (r) => {
      setSyncJobId(r.job_id)
      setSyncJobLabel(r.label)
      setSyncMsg(`${r.label}: iniciando leitura dia a dia...`)
    },
  })

  const sincronizarEstados = () => {
    const tribunais = estadosSync.length ? estadosSync : ['DJEN']
    const label = estadosSync.length === 0
      ? 'DJEN nacional'
      : estadosSync.length === 1
        ? (SIGLA_PARA_UF[estadosSync[0]] ?? estadosSync[0])
        : `${estadosSync.length} estados`
    setEstadosAberto(false)
    syncScraping.mutate({ tribunais, label })
  }

  const marcarLida = useMutation({
    mutationFn: (id: string) => diarioApi.marcarLida(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diario'] }),
  })

  const rejeitar = useMutation({
    mutationFn: (id: string) => diarioApi.rejeitar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diario'] }),
  })

  const reabrir = useMutation({
    mutationFn: (id: string) => diarioApi.reabrir(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diario'] }),
  })

  const vincular = useMutation({
    mutationFn: ({ id, processo_id }: { id: string; processo_id: string }) =>
      diarioApi.vincularProcesso(id, processo_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      setVincularId(null)
      setProcessoSelecionado('')
    },
  })

  const analisar = useMutation({
    mutationFn: (id: string) => diarioApi.analisar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diario'] }),
  })

  const criarPrazo = useMutation({
    mutationFn: (id: string) => diarioApi.criarPrazo(id),
    onSuccess: (r, id) => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      qc.invalidateQueries({ queryKey: ['prazos'] })
      setAcaoMsg((m) => ({ ...m, [id]: `Prazo criado! Vence em ${r.data_limite}` }))
    },
    onError: (e: unknown, id) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Erro ao criar prazo'
      setAcaoMsg((m) => ({ ...m, [id]: `⚠ ${msg}` }))
    },
  })

  const criarTese = useMutation({
    mutationFn: (id: string) => diarioApi.criarTese(id),
    onSuccess: (_r, id) => {
      qc.invalidateQueries({ queryKey: ['teses'] })
      setAcaoMsg((m) => ({ ...m, [id]: 'Tese criada! Acesse a aba Teses IA.' }))
    },
  })

  const copiarTextoPublicacao = async (pub: Publicacao, match: PublicacaoMatchInfo) => {
    const baseText = pub.texto_completo || pub.texto_resumo || ''
    const html = buildHighlightedHtml(baseText, match.relatedTerms)
    try {
      if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
        await navigator.clipboard.write([
          new ClipboardItem({
            'text/html': new Blob([html], { type: 'text/html' }),
            'text/plain': new Blob([baseText], { type: 'text/plain' }),
          }),
        ])
      } else {
        await navigator.clipboard.writeText(baseText)
      }
      setAcaoMsg((m) => ({ ...m, [pub.id]: 'Texto copiado com destaques.' }))
    } catch {
      setAcaoMsg((m) => ({ ...m, [pub.id]: 'Não foi possível copiar o texto.' }))
    }
  }

  const criarPrazoDireto = async (item: PublicacaoEnriquecida) => {
    const { pub, match } = item
    try {
      if (!pub.processo_id) {
        if (!match.primaryProcessId) {
          setAcaoMsg((m) => ({ ...m, [pub.id]: '⚠ Vincule a publicação a um processo antes de criar o prazo.' }))
          return
        }
        await vincular.mutateAsync({ id: pub.id, processo_id: match.primaryProcessId })
      }
      if (!pub.analise_ia) {
        await analisar.mutateAsync(pub.id)
      }
      await criarPrazo.mutateAsync(pub.id)
    } catch {
      // mensagens já tratadas nas mutations
    }
  }

  const SEM_PUB = 'Sem publicações nesta edição.'
  const publicacoesEnriquecidas = [...publicacoes]
    .map((pub) => ({ pub, match: classifyPublication(pub, processos, clientes, termosNomesMonitorados) }))
    .filter(({ match }) => match.hasRegisteredProcess || match.hasExactName || match.hasOabMatch)
    .sort((a, b) => {
      const dateA = new Date(`${a.pub.data_publicacao}T12:00:00`).getTime()
      const dateB = new Date(`${b.pub.data_publicacao}T12:00:00`).getTime()
      return dateB - dateA
    })

  // Tribunais (siglas) presentes nos resultados, para o filtro por estado.
  const tribunaisPresentes = uniqueStrings(
    publicacoesEnriquecidas.map(({ pub }) => (pub.tribunal ?? '').trim()).filter(Boolean),
  ).sort()

  const periodoCutoff = filtroPeriodoDias
    ? new Date(Date.now() - filtroPeriodoDias * 24 * 60 * 60 * 1000)
    : null
  const buscaClienteNorm = normalizeText(buscaCliente)

  const publicacoesFiltradas = publicacoesEnriquecidas.filter(({ pub, match }) => {
    if (filtroComConteudo && (pub.texto_resumo === SEM_PUB || !pub.texto_resumo)) return false
    if (filtroMatch === 'cadastrados' && !match.hasRegisteredProcess) return false
    if (filtroMatch === 'exatos' && !match.hasExactName) return false
    if (filtroTribunal && (pub.tribunal ?? '') !== filtroTribunal) return false
    if (periodoCutoff && new Date(`${pub.data_publicacao}T12:00:00`) < periodoCutoff) return false
    if (buscaClienteNorm) {
      const alvo = normalizeText(
        [
          ...match.linkedClientNames,
          ...match.exactClientNames,
          match.primaryClientName ?? '',
          pub.cliente_nome_pub ?? '',
        ].join(' '),
      )
      if (!alvo.includes(buscaClienteNorm)) return false
    }
    return true
  })

  const syncEmAndamento = syncScraping.isPending || !!syncJobId
  const syncPercentual = syncJob?.total_days
    ? Math.round((syncJob.completed_days / syncJob.total_days) * 100)
    : 0
  const abertasCount = publicacoesEnriquecidas.filter(
    ({ pub }) => !pub.lida && !pub.rejeitada && pub.texto_resumo !== 'Sem publicações nesta edição.',
  ).length

  return (
    <div>
      {googleStatus && !googleStatus.conectado && (
        <div className={diarioStyles.authBanner}>
          <span>⚠ Google não autenticado — o sync do Gmail não funcionará.</span>
          <a
            href="http://localhost:8000/auth/google"
            className={diarioStyles.btnAuth}
          >
            Conectar Google
          </a>
        </div>
      )}

      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          Diário Oficial
          {abertasCount > 0 && (
            <span className={diarioStyles.badge}>
              {abertasCount}
            </span>
          )}
        </h1>
        <div className={diarioStyles.headerActions}>
          <div className={diarioStyles.daysControl}>
            <span className={diarioStyles.daysLabel}>dias</span>
            <input
              type="number"
              className={diarioStyles.daysInput}
              min={1}
              max={30}
              value={daysBack}
              onChange={(e) => setDaysBack(Math.max(1, Math.min(30, Number(e.target.value))))}
            />
          </div>
          <button
            className={diarioStyles.btnGmail}
            onClick={() => syncGmail.mutate()}
            disabled={syncGmail.isPending}
          >
            {syncGmail.isPending ? 'Buscando...' : '↓ Gmail'}
          </button>
        </div>
      </div>

      {/* Sincronizar — leitura nacional do DJEN, com filtro opcional por estado */}
      <div className={diarioStyles.syncBar}>
        <div className={diarioStyles.estadosDropdown}>
          <button
            type="button"
            className={diarioStyles.estadosToggle}
            onClick={() => setEstadosAberto((v) => !v)}
            disabled={syncEmAndamento}
          >
            {estadosSync.length === 0
              ? 'Todos os estados (DJEN nacional)'
              : `${estadosSync.length} estado(s): ${estadosSync.map((s) => SIGLA_PARA_UF[s] ?? s).join(', ')}`}
            <span className={diarioStyles.estadosCaret}>▾</span>
          </button>
          {estadosAberto && (
            <div className={diarioStyles.estadosPanel}>
              <div className={diarioStyles.estadosPanelHead}>
                <button type="button" className={diarioStyles.estadosMini} onClick={() => setEstadosSync([])}>
                  Limpar (nacional)
                </button>
                <button
                  type="button"
                  className={diarioStyles.estadosMini}
                  onClick={() => setEstadosSync(ESTADOS_BR.map((e) => e.sigla))}
                >
                  Selecionar todos
                </button>
              </div>
              <div className={diarioStyles.estadosGrid}>
                {ESTADOS_BR.map((e) => {
                  const marcado = estadosSync.includes(e.sigla)
                  return (
                    <label key={e.sigla} className={diarioStyles.estadoItem} title={e.nome}>
                      <input
                        type="checkbox"
                        checked={marcado}
                        onChange={() =>
                          setEstadosSync((prev) =>
                            marcado ? prev.filter((s) => s !== e.sigla) : [...prev, e.sigla],
                          )
                        }
                      />
                      <span className={diarioStyles.estadoUf}>{e.uf}</span>
                      <span className={diarioStyles.estadoNome}>{e.nome}</span>
                    </label>
                  )
                })}
              </div>
            </div>
          )}
        </div>
        <button
          className={diarioStyles.btnSincronizar}
          onClick={sincronizarEstados}
          disabled={syncEmAndamento}
        >
          {syncEmAndamento ? `Lendo ${syncJob?.current_label ?? syncJobLabel ?? ''}...` : '↓ Sincronizar DJEN'}
        </button>
      </div>

      {syncMsg && <div className={diarioStyles.syncMsg}>{syncMsg}</div>}

      {syncJob && (
        <div className={diarioStyles.syncProgressBox}>
          <div className={diarioStyles.syncProgressHeader}>
            <span>{syncJobLabel ?? syncJob.tribunais.join(', ')}</span>
            <strong>{syncPercentual}%</strong>
          </div>
          <div className={diarioStyles.syncProgressTrack}>
            <div className={diarioStyles.syncProgressFill} style={{ width: `${syncPercentual}%` }} />
          </div>
          <div className={diarioStyles.syncProgressMeta}>
            <span>{syncJob.message ?? 'Lendo Diário Oficial...'}</span>
            <span>{syncJob.completed_days}/{syncJob.total_days} dias</span>
          </div>
        </div>
      )}

      <div className={diarioStyles.syncMsg} style={{ background: '#1f2937', borderColor: '#374151', color: '#cbd5e1' }}>
        A leitura usa a base nacional do DJEN/Comunica, filtrada pelas OABs e clientes monitorados. Sem estado selecionado, busca em todo o Brasil; escolha estados para restringir a consulta.
      </div>

      {/* Monitoramento automático do Diário Oficial */}
      <div className={diarioStyles.termosBox}>
        <div className={diarioStyles.termosInline} style={{ flexWrap: 'wrap', gap: '10px' }}>
          <span className={diarioStyles.termosLabel}>
            Monitoramento automático:
            <span className={diarioStyles.termosInfo} title="Camadas por confiança: OAB e processos cadastrados são match forte; nomes (clientes selecionados e adicionais) são match médio.">
              OAB · processos · clientes selecionados · nomes
            </span>
          </span>

          {/* OABs monitoradas */}
          <details className={diarioStyles.termosCollapse}>
            <summary className={diarioStyles.termosSummary}>
              OABs ({oabs.length})
            </summary>
            <div className={diarioStyles.termosChips}>
              {oabs.map((o, i) => (
                <span key={`${o.numero}/${o.uf}`} className={diarioStyles.termoChipCustom}>
                  {o.numero}/{o.uf}
                  <button
                    className={diarioStyles.termoRemove}
                    onClick={() => {
                      const next = oabs.filter((_, j) => j !== i)
                      setOabs(next)
                      salvarMonitoramento.mutate({ oabs: next })
                    }}
                  >×</button>
                </span>
              ))}
              <div className={diarioStyles.termoAddInline} style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                <input
                  className={diarioStyles.termoInputInline}
                  placeholder="Número"
                  value={novaOabNumero}
                  onChange={(e) => setNovaOabNumero(e.target.value.replace(/\D/g, ''))}
                  style={{ width: '80px' }}
                />
                <input
                  className={diarioStyles.termoInputInline}
                  placeholder="UF"
                  value={novaOabUf}
                  maxLength={2}
                  onChange={(e) => setNovaOabUf(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
                  style={{ width: '46px' }}
                />
                <button
                  className={diarioStyles.btnVincular}
                  disabled={!novaOabNumero || novaOabUf.length !== 2}
                  onClick={() => {
                    const nova = { numero: novaOabNumero, uf: novaOabUf }
                    if (!oabs.some((o) => o.numero === nova.numero && o.uf === nova.uf)) {
                      const next = [...oabs, nova]
                      setOabs(next)
                      salvarMonitoramento.mutate({ oabs: next })
                    }
                    setNovaOabNumero('')
                    setNovaOabUf('')
                  }}
                >
                  + OAB
                </button>
              </div>
            </div>
          </details>

          {/* Clientes monitorados por nome */}
          <details className={diarioStyles.termosCollapse}>
            <summary className={diarioStyles.termosSummary}>
              Clientes monitorados ({clientesMonitorados.length})
            </summary>
            <div className={diarioStyles.clienteMonitorBox}>
              <input
                className={diarioStyles.clienteMonitorBusca}
                placeholder="Filtrar clientes..."
                value={buscaMonitorCliente}
                onChange={(e) => setBuscaMonitorCliente(e.target.value)}
              />
              <div className={diarioStyles.clienteMonitorLista}>
                {[...clientes]
                  .sort((a, b) => a.nome.localeCompare(b.nome))
                  .filter((c) => normalizeText(c.nome).includes(normalizeText(buscaMonitorCliente)))
                  .map((c) => {
                    const ativo = !!c.monitorar_diario
                    return (
                      <button
                        key={c.id}
                        type="button"
                        className={`${diarioStyles.clienteMonitorItem} ${ativo ? diarioStyles.clienteMonitorAtivo : ''}`}
                        disabled={toggleMonitorarCliente.isPending}
                        onClick={() => toggleMonitorarCliente.mutate({ id: c.id, monitorar_diario: !ativo })}
                        title={c.nome}
                      >
                        <span className={`${diarioStyles.clienteMonitorCheck} ${ativo ? diarioStyles.clienteMonitorCheckOn : ''}`}>
                          {ativo ? '✓' : ''}
                        </span>
                        <span className={diarioStyles.clienteMonitorNome}>{c.nome}</span>
                      </button>
                    )
                  })}
                {clientes.length === 0 && (
                  <span className={diarioStyles.clienteMonitorVazio}>Nenhum cliente cadastrado.</span>
                )}
              </div>
            </div>
          </details>

          {/* Nomes adicionais (sem OAB vinculada) */}
          <details className={diarioStyles.termosCollapse}>
            <summary className={diarioStyles.termosSummary}>
              Nomes adicionais ({termosCustom.length})
            </summary>
            <div className={diarioStyles.termosChips}>
              {termosCustom.map((t, i) => (
                <span key={i} className={diarioStyles.termoChipCustom}>
                  {t}
                  <button
                    className={diarioStyles.termoRemove}
                    onClick={() => {
                      const next = termosCustom.filter((_, j) => j !== i)
                      setTermosCustom(next)
                      salvarMonitoramento.mutate({ termos_extras: next })
                    }}
                  >×</button>
                </span>
              ))}
              <div className={diarioStyles.termoAddInline}>
                <input
                  className={diarioStyles.termoInputInline}
                  placeholder="+ Adicionar nome/termo..."
                  value={novoTermo}
                  onChange={(e) => setNovoTermo(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && novoTermo.trim()) {
                      const term = novoTermo.trim()
                      const next = Array.from(new Set([...termosCustom, term]))
                      setTermosCustom(next)
                      salvarMonitoramento.mutate({ termos_extras: next })
                      setNovoTermo('')
                    }
                  }}
                />
              </div>
            </div>
          </details>
        </div>
      </div>

      <div className={diarioStyles.filtros}>
        <button
          className={`${diarioStyles.filtroBtn} ${filtroEstado === 'abertas' ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroEstado('abertas')}
        >
          Em aberto
        </button>
        <button
          className={`${diarioStyles.filtroBtn} ${filtroEstado === 'tratadas' ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroEstado('tratadas')}
        >
          Tratadas
        </button>
        <button
          className={`${diarioStyles.filtroBtn} ${filtroEstado === 'rejeitadas' ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroEstado('rejeitadas')}
        >
          Rejeitadas
        </button>
        <button
          className={`${diarioStyles.filtroBtn} ${filtroEstado === 'todas' ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroEstado('todas')}
        >
          Todas
        </button>
        <button
          className={`${diarioStyles.filtroBtn} ${filtroComConteudo ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroComConteudo((v) => !v)}
          title="Ocultar entradas sem publicações nesta edição"
        >
          Com conteúdo
        </button>
        <button
          className={`${diarioStyles.filtroBtn} ${filtroMatch === 'cadastrados' ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroMatch((v) => v === 'cadastrados' ? 'todos' : 'cadastrados')}
        >
          Processos cadastrados
        </button>
        <button
          className={`${diarioStyles.filtroBtn} ${filtroMatch === 'exatos' ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroMatch((v) => v === 'exatos' ? 'todos' : 'exatos')}
        >
          Nomes exatos
        </button>
      </div>

      <div className={diarioStyles.filtrosAvancados}>
        <label className={diarioStyles.filtroCampo}>
          <span className={diarioStyles.filtroCampoLabel}>Período</span>
          <select
            className={diarioStyles.filtroSelect}
            value={filtroPeriodoDias ?? ''}
            onChange={(e) => setFiltroPeriodoDias(e.target.value ? Number(e.target.value) : null)}
          >
            {PERIODOS_FILTRO.map((p) => (
              <option key={p.label} value={p.dias ?? ''}>{p.label}</option>
            ))}
          </select>
        </label>

        <label className={diarioStyles.filtroCampo}>
          <span className={diarioStyles.filtroCampoLabel}>Tribunal/UF</span>
          <select
            className={diarioStyles.filtroSelect}
            value={filtroTribunal}
            onChange={(e) => setFiltroTribunal(e.target.value)}
          >
            <option value="">Todos</option>
            {tribunaisPresentes.map((t) => (
              <option key={t} value={t}>{SIGLA_PARA_UF[t] ? `${SIGLA_PARA_UF[t]} · ${t}` : t}</option>
            ))}
          </select>
        </label>

        <label className={`${diarioStyles.filtroCampo} ${diarioStyles.filtroCampoBusca}`}>
          <span className={diarioStyles.filtroCampoLabel}>Cliente</span>
          <input
            className={diarioStyles.filtroInput}
            placeholder="Buscar por nome de cliente..."
            value={buscaCliente}
            onChange={(e) => setBuscaCliente(e.target.value)}
          />
          {buscaCliente && (
            <button type="button" className={diarioStyles.filtroLimpar} onClick={() => setBuscaCliente('')}>×</button>
          )}
        </label>

        {(filtroPeriodoDias || filtroTribunal || buscaCliente) && (
          <button
            type="button"
            className={diarioStyles.filtroBtn}
            onClick={() => { setFiltroPeriodoDias(null); setFiltroTribunal(''); setBuscaCliente('') }}
          >
            Limpar filtros
          </button>
        )}
      </div>

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : publicacoesFiltradas.length === 0 ? (
        <p className={styles.empty}>
          {filtroComConteudo
            ? 'Nenhuma publicação com conteúdo encontrada.'
            : filtroEstado === 'abertas'
              ? 'Nenhuma publicação em aberto. Use os botões acima para sincronizar.'
              : filtroEstado === 'tratadas'
                ? 'Nenhuma publicação tratada ainda.'
                : filtroEstado === 'rejeitadas'
                  ? 'Nenhuma publicação rejeitada.'
              : 'Nenhuma publicação importada ainda.'}
        </p>
      ) : (
        <div className={diarioStyles.feed}>
          {publicacoesFiltradas.map(({ pub, match }) => {
            const textoBase = pub.texto_completo || pub.texto_resumo || ''
            const resumoExibicao = buildRelevantExcerpt(textoBase, match.relatedTerms)
            const nomesExatos = uniqueStrings([...match.exactClientNames, ...match.exactTermMatches])

            return (
            <div
              key={pub.id}
              className={`${diarioStyles.card} ${pub.lida ? diarioStyles.cardLida : ''} ${pub.rejeitada ? diarioStyles.cardRejeitada : ''} ${pub.texto_resumo === 'Sem publicações nesta edição.' ? diarioStyles.cardSemPub : ''}`}
            >
              <div className={diarioStyles.cardHeader}>
                <div className={diarioStyles.cardMeta}>
                  {pub.url_fonte ? (
                    <a
                      href={pub.url_fonte}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`${diarioStyles.fonte} ${diarioStyles.fonteLink}`}
                      title={`Abrir no ${FONTE_LABEL[pub.fonte]}`}
                    >
                      {FONTE_LABEL[pub.fonte]} ↗
                    </a>
                  ) : (
                    <span className={diarioStyles.fonte}>{FONTE_LABEL[pub.fonte]}</span>
                  )}
                  {pub.tipo_ato && (
                    <span className={`${diarioStyles.tipoAto} ${TIPO_CORES[pub.tipo_ato]}`}>
                      {pub.tipo_ato}
                    </span>
                  )}
                  {pub.tribunal && (
                    <span className={diarioStyles.tribunal}>{pub.tribunal}</span>
                  )}
                  <span className={diarioStyles.data}>{formatDate(pub.data_publicacao)}</span>
                </div>
                <div className={diarioStyles.cardActions}>
                  {pub.rejeitada ? (
                    <button
                      className={diarioStyles.btnLida}
                      onClick={() => reabrir.mutate(pub.id)}
                    >
                      Reabrir
                    </button>
                  ) : !pub.lida && (
                    <button
                      className={diarioStyles.btnLida}
                      onClick={() => marcarLida.mutate(pub.id)}
                    >
                      ✓ Lida
                    </button>
                  )}
                  <button
                    className={diarioStyles.btnVer}
                    onClick={() => setExpandido(expandido === pub.id ? null : pub.id)}
                  >
                    {expandido === pub.id ? 'Fechar' : 'Ver texto'}
                  </button>
                  <button
                    className={diarioStyles.btnCopy}
                    onClick={() => copiarTextoPublicacao(pub, match)}
                  >
                    Copiar
                  </button>
                  <button
                    className={styles.btnDanger}
                    onClick={() => { if (confirm('Rejeitar esta publicação?')) rejeitar.mutate(pub.id) }}
                    disabled={pub.rejeitada}
                  >
                    ×
                  </button>
                </div>
              </div>

              {pub.numero_cnj && (
                <div className={diarioStyles.cnj}>
                  <span className={diarioStyles.iaLabel}>CNJ publicado</span>
                  <code>{pub.numero_cnj}</code>
                  {pub.processo_id ? (
                    <span className={diarioStyles.vinculado}>
                      Processo cadastrado no sistema
                    </span>
                  ) : (
                    <button
                      className={diarioStyles.btnVincular}
                      onClick={() => setVincularId(pub.id)}
                    >
                      Vincular processo
                    </button>
                  )}
                </div>
              )}

              <div className={diarioStyles.matchBox}>
                {match.hasOabMatch && (
                  <span className={`${diarioStyles.matchBadge} ${diarioStyles.matchProcesso}`} title="Encontrado pela OAB monitorada — match forte">
                    OAB {match.oabMatch}
                  </span>
                )}
                {match.hasRegisteredProcess && (
                  <span className={`${diarioStyles.matchBadge} ${diarioStyles.matchProcesso}`} title="Processo cadastrado no sistema (match por CNJ) — match forte">Processo cadastrado</span>
                )}
                {match.hasExactName && (
                  <span className={`${diarioStyles.matchBadge} ${diarioStyles.matchExato}`} title="Nome encontrado no texto — confirme o cliente correto">Nome encontrado</span>
                )}
              </div>

              {(match.hasOabMatch || match.linkedClientNames.length > 0 || match.relatedProcesses.length > 0 || nomesExatos.length > 0) && (
                <div className={diarioStyles.matchDetails}>
                  {match.hasOabMatch && (
                    <div>
                      <span className={diarioStyles.iaLabel}>OAB monitorada</span> {match.oabMatch}
                    </div>
                  )}
                  {match.linkedClientNames.length > 0 && (
                    <div>
                      <span className={diarioStyles.iaLabel}>Cliente</span> {match.linkedClientNames.slice(0, 3).join(' · ')}
                    </div>
                  )}
                  {match.relatedProcesses.length > 0 && (
                    <div>
                      <span className={diarioStyles.iaLabel}>Processo cadastrado</span>{' '}
                      {match.relatedProcesses.slice(0, 3).map((processo) => processo.numero_cnj).join(' · ')}
                    </div>
                  )}
                  {nomesExatos.length > 0 && (
                    <div>
                      <span className={diarioStyles.iaLabel}>Nome encontrado no texto</span> {nomesExatos.slice(0, 3).join(' · ')}
                    </div>
                  )}
                </div>
              )}

              {vincularId === pub.id && (
                <div className={diarioStyles.vincularForm}>
                  <select
                    className={styles.input}
                    value={processoSelecionado}
                    onChange={(e) => setProcessoSelecionado(e.target.value)}
                  >
                    <option value="">Selecione...</option>
                    {processos.map((p) => (
                      <option key={p.id} value={p.id}>{p.numero_cnj}</option>
                    ))}
                  </select>
                  <button
                    className={styles.btnPrimary}
                    disabled={!processoSelecionado}
                    onClick={() => vincular.mutate({ id: pub.id, processo_id: processoSelecionado })}
                  >
                    Confirmar
                  </button>
                  <button
                    className={diarioStyles.btnCancelar}
                    onClick={() => setVincularId(null)}
                  >
                    Cancelar
                  </button>
                </div>
              )}

              {resumoExibicao && (
                <p
                  className={diarioStyles.resumo}
                  dangerouslySetInnerHTML={{ __html: buildHighlightedHtml(resumoExibicao, match.relatedTerms) }}
                />
              )}

              {/* Painel IA — oculto para "sem publicações" */}
              {pub.texto_resumo !== 'Sem publicações nesta edição.' && (() => {
                const analise = parseAnalise(pub)
                const isAnalisando = analisar.isPending && analisar.variables === pub.id
                return (
                  <div className={diarioStyles.iaPanel}>
                    {!analise ? (
                      <div className={diarioStyles.iaAcoes}>
                        <button
                          className={diarioStyles.btnAnalisar}
                          disabled={isAnalisando}
                          onClick={() => analisar.mutate(pub.id)}
                        >
                          {isAnalisando ? '⏳ Analisando...' : '✦ Analisar com IA'}
                        </button>
                        <button
                          className={diarioStyles.btnCriarPrazo}
                          disabled={isAnalisando || !!pub.prazo_id}
                          onClick={() => criarPrazoDireto({ pub, match })}
                        >
                          {pub.prazo_id ? 'Prazo já criado' : isAnalisando ? 'Preparando...' : '+ Criar Prazo'}
                        </button>
                      </div>
                    ) : analise.erro ? (
                      <div className={diarioStyles.iaErro}>
                        ⚠ Erro na análise: {analise.erro}
                        <button className={diarioStyles.btnAnalisar} onClick={() => analisar.mutate(pub.id)}>
                          Tentar novamente
                        </button>
                      </div>
                    ) : (
                      <div className={diarioStyles.iaResultado}>
                        <div className={diarioStyles.iaGrid}>
                          {analise.cliente_nome && (
                            <div><span className={diarioStyles.iaLabel}>Cliente</span> {analise.cliente_nome}</div>
                          )}
                          {analise.tipo_ato && (
                            <div><span className={diarioStyles.iaLabel}>Ato</span> {analise.tipo_ato}</div>
                          )}
                          {analise.requer_resposta && analise.peca_necessaria && (
                            <div>
                              <span className={diarioStyles.iaLabel}>Peça</span>{' '}
                              <strong>{analise.peca_necessaria}</strong>
                              {analise.dias_prazo && ` · ${analise.dias_prazo} dias ${analise.tipo_contagem ?? 'úteis'}`}
                            </div>
                          )}
                          {!analise.requer_resposta && (
                            <div className={diarioStyles.iaSemResposta}>Não requer resposta</div>
                          )}
                        </div>
                        <p className={diarioStyles.iaResumo}>{analise.resumo}</p>
                        <div className={diarioStyles.iaAcoes}>
                          <button
                            className={diarioStyles.btnCriarPrazo}
                            disabled={!!pub.prazo_id || (criarPrazo.isPending && criarPrazo.variables === pub.id) || (analisar.isPending && analisar.variables === pub.id)}
                            onClick={() => criarPrazoDireto({ pub, match })}
                          >
                            {pub.prazo_id
                              ? 'Prazo já criado'
                              : criarPrazo.isPending && criarPrazo.variables === pub.id
                              ? 'Criando...'
                              : !pub.processo_id && match.primaryProcessId
                                ? '+ Vincular e Criar Prazo'
                                : '+ Criar Prazo'}
                          </button>
                          <button
                            className={diarioStyles.btnCriarTese}
                            disabled={criarTese.isPending && criarTese.variables === pub.id}
                            onClick={() => criarTese.mutate(pub.id)}
                          >
                            {criarTese.isPending && criarTese.variables === pub.id
                              ? 'Criando...' : '✦ Criar Tese IA'}
                          </button>
                          <button
                            className={diarioStyles.btnAnalisarSmall}
                            onClick={() => analisar.mutate(pub.id)}
                          >
                            ↻
                          </button>
                        </div>
                        {acaoMsg[pub.id] && (
                          <div className={diarioStyles.acaoMsg}>{acaoMsg[pub.id]}</div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })()}

              {expandido === pub.id && pub.texto_completo && (
                <div
                  className={diarioStyles.textoCompleto}
                  dangerouslySetInnerHTML={{ __html: buildHighlightedHtml(pub.texto_completo, match.relatedTerms) }}
                />
              )}
            </div>
          )})}
        </div>
      )}
    </div>
  )
}
