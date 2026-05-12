import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { diarioApi } from '../api/diario'
import type { AnaliseIA, Publicacao, TipoAto } from '../api/diario'
import { processosApi } from '../api/processos'
import { clientesApi } from '../api/clientes'
import styles from './Page.module.css'
import diarioStyles from './DiarioPage.module.css'

const FONTES_DIARIO = [
  { key: 'DJEN', label: 'DJEN', tribunais: ['DJEN'] },
  { key: 'TJSP', label: 'DJSP', tribunais: ['TJSP'] },
  { key: 'TJES', label: 'DJES', tribunais: ['TJES'] },
  { key: 'TJAM', label: 'DJAM', tribunais: ['TJAM'] },
  { key: 'TJRJ', label: 'DJRJ', tribunais: ['TJRJ'] },
] as const

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

type DiarioTab = 'todos' | 'processo' | 'advogado' | 'cliente' | 'revisar'

interface PublicacaoEnriquecida {
  pub: Publicacao
  tab: DiarioTab
  termosDestaque: string[]
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

function cleanMonitorName(value: string) {
  return value.replace(/\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim()
}

function getMatchTab(pub: Publicacao): DiarioTab {
  if (pub.match_tipo === 'processo') return 'processo'
  if (pub.match_tipo === 'advogado') return 'advogado'
  if (pub.match_tipo === 'cliente') return 'cliente'
  return 'revisar'
}

function getMatchPriority(tab: DiarioTab) {
  const rank: Record<DiarioTab, number> = {
    processo: 0,
    advogado: 1,
    cliente: 2,
    revisar: 3,
    todos: 4,
  }
  return rank[tab] ?? 4
}

function getMatchLabel(pub: Publicacao) {
  if (pub.match_tipo === 'processo') return 'Processo cadastrado'
  if (pub.match_tipo === 'advogado') return 'Advogado monitorado'
  if (pub.match_tipo === 'cliente') return 'Cliente monitorado'
  return 'Revisar'
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

function buildHighlightTerms(pub: Publicacao) {
  return uniqueStrings([
    pub.match_nome ?? '',
    pub.match_tipo === 'processo' ? pub.numero_cnj ?? '' : '',
  ].filter(Boolean))
}

function extractErrorMessage(error: unknown, fallback: string) {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
}

export default function DiarioPage() {
  const qc = useQueryClient()
  const [expandido, setExpandido] = useState<string | null>(null)
  const [vincularId, setVincularId] = useState<string | null>(null)
  const [processoSelecionado, setProcessoSelecionado] = useState('')
  const [filtroLida, setFiltroLida] = useState<'todas' | 'nao_lidas'>('nao_lidas')
  const [filtroComConteudo, setFiltroComConteudo] = useState(false)
  const [abaDiario, setAbaDiario] = useState<DiarioTab>('todos')
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [acaoMsg, setAcaoMsg] = useState<Record<string, string>>({})
  const [daysBack, setDaysBack] = useState(3)
  const [advogadosMonitorados, setAdvogadosMonitorados] = useState<string[]>([])
  const [clientesExtras, setClientesExtras] = useState<string[]>([])
  const [novoAdvogado, setNovoAdvogado] = useState('')
  const [novoClienteExtra, setNovoClienteExtra] = useState('')
  const [pjeModalAberto, setPjeModalAberto] = useState(false)
  const [pjeCpf, setPjeCpf] = useState('')
  const [pjeSenha, setPjeSenha] = useState('')
  const [pjeSaving, setPjeSaving] = useState(false)


  const parseAnalise = (pub: { analise_ia?: string }): AnaliseIA | null => {
    if (!pub.analise_ia) return null
    try { return JSON.parse(pub.analise_ia) } catch { return null }
  }

  const { data: publicacoes = [], isLoading } = useQuery({
    queryKey: ['diario', filtroLida],
    queryFn: () =>
      diarioApi.listar(filtroLida === 'nao_lidas' ? { lida: false } : {}),
  })

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

  const clienteNomePorId = new Map(clientes.map((cliente) => [cliente.id, cliente.nome]))
  const processoPorId = new Map(processos.map((processo) => [processo.id, processo]))

  const getClienteDoProcesso = (pub: Publicacao) => {
    const processoId = pub.processo_id || pub.match_processo_id
    if (!processoId) return null
    const processo = processoPorId.get(processoId)
    if (!processo) return null
    const nomes = [
      clienteNomePorId.get(processo.cliente_id) ?? '',
      ...(processo.clientes_litisconsorcio?.map((cliente) => cliente.nome ?? '') ?? []),
    ]
    return uniqueStrings(nomes)[0] ?? null
  }

  const { data: monitoramento } = useQuery({
    queryKey: ['diario-monitoramento'],
    queryFn: () => diarioApi.monitoramento(),
  })

  useEffect(() => {
    if (monitoramento) {
      setAdvogadosMonitorados(monitoramento.advogados_monitorados ?? monitoramento.termos_extras ?? [])
      setClientesExtras(monitoramento.clientes_monitorados_extras ?? [])
    }
  }, [monitoramento])

  const syncGmail = useMutation({
    mutationFn: () => diarioApi.syncGmail(daysBack),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      const erroMsg = r.erros ? `, ${r.erros} erro(s)` : ''
      setSyncMsg(r.mensagem || `Gmail: ${r.inseridas} novas, ${r.duplicatas} duplicatas${erroMsg}`)
      setTimeout(() => setSyncMsg(null), 5000)
    },
  })

  const salvarMonitoramento = useMutation({
    mutationFn: (payload: { advogados_monitorados: string[]; clientes_monitorados_extras: string[] }) =>
      diarioApi.salvarMonitoramento({
        tribunais: monitoramento?.tribunais?.length ? monitoramento.tribunais : ['TJES', 'TJSP', 'TJAM'],
        auto_sync: monitoramento?.auto_sync ?? true,
        termos_extras: payload.advogados_monitorados,
        advogados_monitorados: payload.advogados_monitorados,
        clientes_monitorados_extras: payload.clientes_monitorados_extras,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['diario-monitoramento'] })
      setAdvogadosMonitorados(data.advogados_monitorados ?? data.termos_extras ?? [])
      setClientesExtras(data.clientes_monitorados_extras ?? [])
    },
  })

  const syncScraping = useMutation({
    mutationFn: ({ tribunais, label }: { tribunais: string[]; label: string }) =>
      diarioApi.syncScraping(tribunais, [], daysBack).then((r) => ({ ...r, label })),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      const erroMsg = r.erros ? `, ${r.erros} erro(s)` : ''
      setSyncMsg(r.mensagem || `${r.label}: ${r.inseridas} novas, ${r.duplicatas} duplicatas${erroMsg}`)
      setTimeout(() => setSyncMsg(null), 5000)
    },
  })

  const syncClientes = useMutation({
    mutationFn: () => diarioApi.syncClientes(daysBack),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      const erroMsg = r.erros ? `, ${r.erros} erro(s)` : ''
      setSyncMsg(r.mensagem || `Clientes: ${r.inseridas} novas, ${r.duplicatas} duplicatas${erroMsg}`)
      setTimeout(() => setSyncMsg(null), 6000)
    },
  })

  const reclassificar = useMutation({
    mutationFn: () => diarioApi.reclassificar(),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      setSyncMsg(`Reclassificação: ${r.duplicatas} publicação(ões) atualizada(s).`)
      setTimeout(() => setSyncMsg(null), 5000)
    },
  })

  const { data: pjeConfig } = useQuery({
    queryKey: ['pje-config'],
    queryFn: () => diarioApi.pjeConfig(),
  })

  const syncPje = useMutation({
    mutationFn: () => diarioApi.syncPje(),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      setSyncMsg(`PJe: ${r.inseridas} novas, ${r.duplicatas} duplicatas (${r.total_pje} total)`)
      setTimeout(() => setSyncMsg(null), 6000)
    },
    onError: () => {
      setPjeModalAberto(true)
    },
  })

  const handlePjeClick = () => {
    if (pjeConfig?.configurado) {
      syncPje.mutate()
    } else {
      setPjeModalAberto(true)
    }
  }

  const handlePjeSaveConfig = async () => {
    if (!pjeCpf || !pjeSenha) return
    setPjeSaving(true)
    try {
      await diarioApi.savePjeConfig(pjeCpf, pjeSenha)
      qc.invalidateQueries({ queryKey: ['pje-config'] })
      setPjeModalAberto(false)
      syncPje.mutate()
    } finally {
      setPjeSaving(false)
    }
  }

  const marcarLida = useMutation({
    mutationFn: (id: string) => diarioApi.marcarLida(id),
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

  const deletar = useMutation({
    mutationFn: (id: string) => diarioApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diario'] }),
  })

  const analisar = useMutation({
    mutationFn: (id: string) => diarioApi.analisar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diario'] }),
    onError: (e: unknown, id) => {
      setAcaoMsg((m) => ({ ...m, [id]: `⚠ ${extractErrorMessage(e, 'Erro ao analisar publicação')}` }))
    },
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

  const copiarTextoPublicacao = async (pub: Publicacao, termosDestaque: string[]) => {
    const baseText = pub.texto_completo || pub.texto_resumo || ''
    const html = buildHighlightedHtml(baseText, termosDestaque)
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
    const { pub } = item
    try {
      if (!pub.processo_id) {
        if (!pub.match_processo_id) {
          setAcaoMsg((m) => ({ ...m, [pub.id]: '⚠ Vincule a publicação a um processo antes de criar o prazo.' }))
          return
        }
        await vincular.mutateAsync({ id: pub.id, processo_id: pub.match_processo_id })
      }
      if (!pub.analise_ia) {
        await analisar.mutateAsync(pub.id)
      }
      await criarPrazo.mutateAsync(pub.id)
    } catch (e) {
      setAcaoMsg((m) => ({ ...m, [pub.id]: m[pub.id] || `⚠ ${extractErrorMessage(e, 'Não foi possível criar o prazo')}` }))
    }
  }

  const SEM_PUB = 'Sem publicações nesta edição.'
  const publicacoesEnriquecidas = [...publicacoes]
    .map((pub) => ({ pub, tab: getMatchTab(pub), termosDestaque: buildHighlightTerms(pub) }))
    .sort((a, b) => {
      const dateA = new Date(`${a.pub.data_publicacao}T12:00:00`).getTime()
      const dateB = new Date(`${b.pub.data_publicacao}T12:00:00`).getTime()
      if (dateA !== dateB) return dateB - dateA

      const priorityA = getMatchPriority(a.tab)
      const priorityB = getMatchPriority(b.tab)
      if (priorityA !== priorityB) return priorityA - priorityB

      return new Date(b.pub.created_at).getTime() - new Date(a.pub.created_at).getTime()
    })

  const publicacoesFiltradas = publicacoesEnriquecidas.filter(({ pub, tab }) => {
    if (filtroComConteudo && (pub.texto_resumo === SEM_PUB || !pub.texto_resumo)) return false
    if (abaDiario !== 'todos' && tab !== abaDiario) return false
    return true
  })

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
          {publicacoesEnriquecidas.filter(({ pub }) => !pub.lida && pub.texto_resumo !== 'Sem publicações nesta edição.').length > 0 && (
            <span className={diarioStyles.badge}>
              {publicacoesEnriquecidas.filter(({ pub }) => !pub.lida && pub.texto_resumo !== 'Sem publicações nesta edição.').length}
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
          <button
            className={diarioStyles.btnGmail}
            onClick={handlePjeClick}
            disabled={syncPje.isPending}
            style={{ background: '#2a1a40', borderColor: '#7c3aed', color: '#a78bfa' }}
          >
            {syncPje.isPending ? 'Buscando...' : '↓ PJe Comunica'}
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
        {FONTES_DIARIO.map((fonte) => {
          const carregando = syncScraping.isPending && syncScraping.variables?.label === fonte.label
          return (
            <button
              key={fonte.key}
              className={diarioStyles.btnTribunais}
              onClick={() => syncScraping.mutate({ tribunais: [...fonte.tribunais], label: fonte.label })}
              disabled={syncScraping.isPending}
              style={{
                opacity: syncScraping.isPending && !carregando ? 0.7 : 1,
                minWidth: '110px',
              }}
            >
              {carregando ? `Buscando ${fonte.label}...` : `↓ ${fonte.label}`}
            </button>
          )
        })}
        <button
          className={diarioStyles.btnTribunais}
          onClick={() => syncClientes.mutate()}
          disabled={syncClientes.isPending || syncScraping.isPending}
          style={{ minWidth: '150px', background: '#173b2f', borderColor: '#2f855a', color: '#bbf7d0' }}
        >
          {syncClientes.isPending ? 'Buscando clientes...' : '↓ Buscar clientes'}
        </button>
        <button
          className={diarioStyles.btnTribunais}
          onClick={() => reclassificar.mutate()}
          disabled={reclassificar.isPending}
          style={{ minWidth: '130px', background: '#2f2a1a', borderColor: '#a16207', color: '#fde68a' }}
        >
          {reclassificar.isPending ? 'Reclassificando...' : 'Reclassificar'}
        </button>
      </div>

      {/* Modal PJe */}
      {pjeModalAberto && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{
            background: '#1a1b1e', border: '1px solid #333', borderRadius: '10px',
            padding: '24px', width: '360px', display: 'flex', flexDirection: 'column', gap: '14px',
          }}>
            <h3 style={{ margin: 0, color: '#a78bfa' }}>PJe Comunica — Credenciais</h3>
            <p style={{ margin: 0, fontSize: '13px', color: '#888' }}>
              Configure seu CPF e senha do PJe para importar comunicações processuais.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '12px', color: '#aaa' }}>CPF (login)</label>
              <input
                type="text"
                placeholder="000.000.000-00"
                value={pjeCpf}
                onChange={(e) => setPjeCpf(e.target.value)}
                style={{
                  background: '#111', border: '1px solid #333', borderRadius: '6px',
                  color: '#fff', padding: '8px 10px', fontSize: '14px',
                }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '12px', color: '#aaa' }}>Senha</label>
              <input
                type="password"
                placeholder="Senha PJe"
                value={pjeSenha}
                onChange={(e) => setPjeSenha(e.target.value)}
                style={{
                  background: '#111', border: '1px solid #333', borderRadius: '6px',
                  color: '#fff', padding: '8px 10px', fontSize: '14px',
                }}
                onKeyDown={(e) => { if (e.key === 'Enter') handlePjeSaveConfig() }}
              />
            </div>
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setPjeModalAberto(false)}
                style={{
                  background: 'transparent', border: '1px solid #444', color: '#aaa',
                  borderRadius: '6px', padding: '8px 16px', cursor: 'pointer',
                }}
              >
                Cancelar
              </button>
              <button
                onClick={handlePjeSaveConfig}
                disabled={!pjeCpf || !pjeSenha || pjeSaving}
                style={{
                  background: '#7c3aed', border: 'none', color: '#fff',
                  borderRadius: '6px', padding: '8px 16px', cursor: 'pointer',
                  opacity: (!pjeCpf || !pjeSenha || pjeSaving) ? 0.5 : 1,
                }}
              >
                {pjeSaving ? 'Salvando...' : 'Salvar e Sincronizar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {syncMsg && <div className={diarioStyles.syncMsg}>{syncMsg}</div>}

      <div className={diarioStyles.syncMsg} style={{ background: '#1f2937', borderColor: '#374151', color: '#cbd5e1' }}>
        Os botões por tribunal e o cron buscam apenas processos cadastrados e advogados monitorados. A busca por clientes fica separada no botão "Buscar clientes" para reduzir ruído e excesso de consultas.
      </div>

      {/* Termos de Monitoramento */}
      <div className={diarioStyles.termosBox}>
        <div className={diarioStyles.termosInline}>
          <span className={diarioStyles.termosLabel}>
            Monitoramento:
            <span className={diarioStyles.termosInfo} title="Processos cadastrados entram automaticamente pela leitura de CNJ exato">
              {processos.length} processo{processos.length !== 1 ? 's' : ''} (CNJ exato)
            </span>
          </span>
          <details className={diarioStyles.termosCollapse}>
            <summary className={diarioStyles.termosSummary}>
              Advogados monitorados ({advogadosMonitorados.length})
            </summary>
            <div className={diarioStyles.termosChips}>
              {advogadosMonitorados.map((t, i) => (
                <span key={i} className={diarioStyles.termoChipCustom}>
                  {t}
                  <button
                    className={diarioStyles.termoRemove}
                    onClick={() => {
                      const next = advogadosMonitorados.filter((_, j) => j !== i)
                      setAdvogadosMonitorados(next)
                      salvarMonitoramento.mutate({ advogados_monitorados: next, clientes_monitorados_extras: clientesExtras })
                    }}
                  >×</button>
                </span>
              ))}
              <div className={diarioStyles.termoAddInline}>
                <input
                  className={diarioStyles.termoInputInline}
                  placeholder="+ Adicionar advogado..."
                  value={novoAdvogado}
                  onChange={(e) => setNovoAdvogado(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && novoAdvogado.trim()) {
                      const term = cleanMonitorName(novoAdvogado)
                      const next = uniqueStrings([...advogadosMonitorados, term])
                      setAdvogadosMonitorados(next)
                      salvarMonitoramento.mutate({ advogados_monitorados: next, clientes_monitorados_extras: clientesExtras })
                      setNovoAdvogado('')
                    }
                  }}
                />
              </div>
            </div>
          </details>
          <details className={diarioStyles.termosCollapse}>
            <summary className={diarioStyles.termosSummary}>
              Clientes extras ({clientesExtras.length})
            </summary>
            <div className={diarioStyles.termosChips}>
              {clientesExtras.map((t, i) => (
                <span key={i} className={diarioStyles.termoChipCustom}>
                  {t}
                  <button
                    className={diarioStyles.termoRemove}
                    onClick={() => {
                      const next = clientesExtras.filter((_, j) => j !== i)
                      setClientesExtras(next)
                      salvarMonitoramento.mutate({ advogados_monitorados: advogadosMonitorados, clientes_monitorados_extras: next })
                    }}
                  >×</button>
                </span>
              ))}
              <div className={diarioStyles.termoAddInline}>
                <input
                  className={diarioStyles.termoInputInline}
                  placeholder="+ Adicionar cliente/nome..."
                  value={novoClienteExtra}
                  onChange={(e) => setNovoClienteExtra(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && novoClienteExtra.trim()) {
                      const term = cleanMonitorName(novoClienteExtra)
                      const next = uniqueStrings([...clientesExtras, term])
                      setClientesExtras(next)
                      salvarMonitoramento.mutate({ advogados_monitorados: advogadosMonitorados, clientes_monitorados_extras: next })
                      setNovoClienteExtra('')
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
          className={`${diarioStyles.filtroBtn} ${filtroLida === 'nao_lidas' ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroLida('nao_lidas')}
        >
          Não lidas
        </button>
        <button
          className={`${diarioStyles.filtroBtn} ${filtroLida === 'todas' ? diarioStyles.filtroAtivo : ''}`}
          onClick={() => setFiltroLida('todas')}
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
        {([
          ['todos', 'Todas'],
          ['processo', 'Processos'],
          ['advogado', 'Advogados'],
          ['cliente', 'Clientes'],
          ['revisar', 'Revisar'],
        ] as const).map(([tab, label]) => (
          <button
            key={tab}
            className={`${diarioStyles.filtroBtn} ${abaDiario === tab ? diarioStyles.filtroAtivo : ''}`}
            onClick={() => setAbaDiario(tab)}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : publicacoesFiltradas.length === 0 ? (
        <p className={styles.empty}>
          {filtroComConteudo
            ? 'Nenhuma publicação com conteúdo encontrada.'
            : filtroLida === 'nao_lidas'
              ? 'Nenhuma publicação não lida. Use os botões acima para sincronizar.'
              : 'Nenhuma publicação importada ainda.'}
        </p>
      ) : (
        <div className={diarioStyles.feed}>
          {publicacoesFiltradas.map(({ pub, tab, termosDestaque }) => {
            const textoBase = pub.texto_completo || pub.texto_resumo || ''
            const resumoExibicao = buildRelevantExcerpt(textoBase, termosDestaque)
            const matchLabel = getMatchLabel(pub)
            const clienteDoProcesso = getClienteDoProcesso(pub)

            return (
            <div
              key={pub.id}
              className={`${diarioStyles.card} ${pub.lida ? diarioStyles.cardLida : ''} ${pub.texto_resumo === 'Sem publicações nesta edição.' ? diarioStyles.cardSemPub : ''}`}
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
                  {!pub.lida && (
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
                    onClick={() => copiarTextoPublicacao(pub, termosDestaque)}
                  >
                    Copiar
                  </button>
                  <button
                    className={styles.btnDanger}
                    onClick={() => { if (confirm('Remover?')) deletar.mutate(pub.id) }}
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
                {tab === 'processo' && (
                  <span className={`${diarioStyles.matchBadge} ${diarioStyles.matchProcesso}`}>Processo cadastrado</span>
                )}
                {tab === 'advogado' && (
                  <span className={`${diarioStyles.matchBadge} ${diarioStyles.matchExato}`}>Advogado monitorado</span>
                )}
                {tab === 'cliente' && (
                  <span className={`${diarioStyles.matchBadge} ${diarioStyles.matchExato}`}>Cliente monitorado</span>
                )}
                {tab === 'revisar' && (
                  <span className={`${diarioStyles.matchBadge} ${diarioStyles.matchExato}`}>Revisar</span>
                )}
              </div>

              <div className={diarioStyles.matchDetails}>
                {tab !== 'processo' && (
                  <div>
                    <span className={diarioStyles.iaLabel}>Encontrado por</span> {matchLabel}
                  </div>
                )}
                {pub.match_nome && (
                  <div>
                    <span className={diarioStyles.iaLabel}>{tab === 'processo' ? 'CNJ cadastrado' : 'Nome encontrado'}</span> {pub.match_nome}
                  </div>
                )}
                {clienteDoProcesso && (
                  <div>
                    <span className={diarioStyles.iaLabel}>Cliente do processo</span> {clienteDoProcesso}
                  </div>
                )}
              </div>

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
                  dangerouslySetInnerHTML={{ __html: buildHighlightedHtml(resumoExibicao, termosDestaque) }}
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
                          onClick={() => criarPrazoDireto({ pub, tab, termosDestaque })}
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
                          {clienteDoProcesso && (
                            <div><span className={diarioStyles.iaLabel}>Cliente</span> {clienteDoProcesso}</div>
                          )}
                          {!clienteDoProcesso && tab === 'cliente' && pub.match_nome && (
                            <div><span className={diarioStyles.iaLabel}>Cliente</span> {pub.match_nome}</div>
                          )}
                          {!clienteDoProcesso && tab !== 'cliente' && analise.cliente_nome && (
                            <div><span className={diarioStyles.iaLabel}>Nome citado (IA)</span> {analise.cliente_nome}</div>
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
                            onClick={() => criarPrazoDireto({ pub, tab, termosDestaque })}
                          >
                            {pub.prazo_id
                              ? 'Prazo já criado'
                              : criarPrazo.isPending && criarPrazo.variables === pub.id
                              ? 'Criando...'
                              : !pub.processo_id && pub.match_processo_id
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
                  dangerouslySetInnerHTML={{ __html: buildHighlightedHtml(pub.texto_completo, termosDestaque) }}
                />
              )}
            </div>
          )})}
        </div>
      )}
    </div>
  )
}
