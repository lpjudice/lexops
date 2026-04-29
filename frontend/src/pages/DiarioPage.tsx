import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { diarioApi } from '../api/diario'
import type { AnaliseIA, TipoAto } from '../api/diario'
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

export default function DiarioPage() {
  const qc = useQueryClient()
  const [expandido, setExpandido] = useState<string | null>(null)
  const [vincularId, setVincularId] = useState<string | null>(null)
  const [processoSelecionado, setProcessoSelecionado] = useState('')
  const [filtroLida, setFiltroLida] = useState<'todas' | 'nao_lidas'>('nao_lidas')
  const [filtroComConteudo, setFiltroComConteudo] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [acaoMsg, setAcaoMsg] = useState<Record<string, string>>({})
  const [daysBack, setDaysBack] = useState(3)
  const [termosCustom, setTermosCustom] = useState<string[]>([])
  const [novoTermo, setNovoTermo] = useState('')
  const [_termosAberto, _setTermosAberto] = useState(false)
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

  const nomesClientes = clientes.map((c) => c.nome)

  const { data: monitoramento } = useQuery({
    queryKey: ['diario-monitoramento'],
    queryFn: () => diarioApi.monitoramento(),
  })

  useEffect(() => {
    if (monitoramento?.termos_extras) {
      setTermosCustom(monitoramento.termos_extras)
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

  const todosTermos = [...nomesClientes, ...termosCustom].filter(Boolean)

  const salvarMonitoramento = useMutation({
    mutationFn: (payload: { termos_extras: string[] }) =>
      diarioApi.salvarMonitoramento({
        tribunais: monitoramento?.tribunais?.length ? monitoramento.tribunais : ['TJES', 'TJSP', 'TJAM'],
        auto_sync: monitoramento?.auto_sync ?? true,
        termos_extras: payload.termos_extras,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['diario-monitoramento'] })
      setTermosCustom(data.termos_extras)
    },
  })

  const syncScraping = useMutation({
    mutationFn: ({ tribunais, label }: { tribunais: string[]; label: string }) =>
      diarioApi.syncScraping(tribunais, todosTermos, daysBack).then((r) => ({ ...r, label })),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['diario'] })
      setSyncMsg(`${r.label}: ${r.inseridas} novas, ${r.duplicatas} duplicatas`)
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

  const processoNome = (id?: string) =>
    id ? processos.find((p) => p.id === id)?.numero_cnj ?? id : null

  const SEM_PUB = 'Sem publicações nesta edição.'
  const publicacoesFiltradas = filtroComConteudo
    ? publicacoes.filter((p) => p.texto_resumo !== SEM_PUB && !!p.texto_resumo)
    : publicacoes

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
          {publicacoes.filter((p) => !p.lida && p.texto_resumo !== 'Sem publicações nesta edição.').length > 0 && (
            <span className={diarioStyles.badge}>
              {publicacoes.filter((p) => !p.lida && p.texto_resumo !== 'Sem publicações nesta edição.').length}
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
        Cada botão consulta uma fonte separada. O botão `DJEN` faz uma busca pública best-effort. O botão `PJe Comunica` é outra integração, autenticada, e não substitui o `DJEN`.
      </div>

      {/* Termos de Monitoramento */}
      <div className={diarioStyles.termosBox}>
        <div className={diarioStyles.termosInline}>
          <span className={diarioStyles.termosLabel}>
            Monitoramento:
            <span className={diarioStyles.termosInfo} title={`${nomesClientes.length} cliente(s) monitorados automaticamente`}>
              {nomesClientes.length} cliente{nomesClientes.length !== 1 ? 's' : ''} (auto)
            </span>
          </span>
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
                placeholder="+ Adicionar termo..."
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
          {publicacoesFiltradas.map((pub) => (
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
                    className={styles.btnDanger}
                    onClick={() => { if (confirm('Remover?')) deletar.mutate(pub.id) }}
                  >
                    ×
                  </button>
                </div>
              </div>

              {pub.numero_cnj && (
                <div className={diarioStyles.cnj}>
                  <code>{pub.numero_cnj}</code>
                  {pub.processo_id ? (
                    <span className={diarioStyles.vinculado}>
                      → {processoNome(pub.processo_id)}
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

              {pub.texto_resumo && (
                <p className={diarioStyles.resumo}>{pub.texto_resumo}</p>
              )}

              {/* Painel IA — oculto para "sem publicações" */}
              {pub.texto_resumo !== 'Sem publicações nesta edição.' && (() => {
                const analise = parseAnalise(pub)
                const isAnalisando = analisar.isPending && analisar.variables === pub.id
                return (
                  <div className={diarioStyles.iaPanel}>
                    {!analise ? (
                      <button
                        className={diarioStyles.btnAnalisar}
                        disabled={isAnalisando}
                        onClick={() => analisar.mutate(pub.id)}
                      >
                        {isAnalisando ? '⏳ Analisando...' : '✦ Analisar com IA'}
                      </button>
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
                          {analise.requer_resposta && (
                            <button
                              className={diarioStyles.btnCriarPrazo}
                              disabled={criarPrazo.isPending && criarPrazo.variables === pub.id}
                              onClick={() => criarPrazo.mutate(pub.id)}
                            >
                              {criarPrazo.isPending && criarPrazo.variables === pub.id
                                ? 'Criando...' : '+ Criar Prazo'}
                            </button>
                          )}
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
                <pre className={diarioStyles.textoCompleto}>{pub.texto_completo}</pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
