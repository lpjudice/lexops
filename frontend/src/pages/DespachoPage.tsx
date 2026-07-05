import { useMemo, useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { despachoApi } from '../api/despacho'
import type { PublicacaoPendente, TarefaSugerida } from '../api/despacho'
import { processosApi } from '../api/processos'
import { clientesApi } from '../api/clientes'
import ResponsavelComboBox from '../components/ResponsavelComboBox'
import styles from './Page.module.css'

const CONFIANCA_LABEL: Record<string, { texto: string; cor: string; bg: string }> = {
  alta: { texto: 'CNJ exato', cor: '#15803d', bg: '#dcfce7' },
  media: { texto: 'OAB', cor: '#92400e', bg: '#fef3c7' },
  baixa: { texto: 'só por nome', cor: '#b91c1c', bg: '#fee2e2' },
  sem_vinculo: { texto: 'sem vínculo', cor: '#6b7280', bg: '#f3f4f6' },
}

const FONTE_LABEL: Record<string, { texto: string; icone: string }> = {
  gmail: { texto: 'Recorte Digital OAB', icone: '📧' },
  scraping_djen: { texto: 'Diário Oficial (DJEN)', icone: '📰' },
  scraping_tjes: { texto: 'Diário Oficial (TJES)', icone: '📰' },
  scraping_tjsp: { texto: 'Diário Oficial (TJSP)', icone: '📰' },
  scraping_tjam: { texto: 'Diário Oficial (TJAM)', icone: '📰' },
  scraping_tjrj: { texto: 'Diário Oficial (TJRJ)', icone: '📰' },
  pje_comunica: { texto: 'PJe Comunica', icone: '⚖️' },
  manual: { texto: 'Manual', icone: '✍️' },
}

function ChipFonte({ fonte }: { fonte: string }) {
  const f = FONTE_LABEL[fonte] || { texto: fonte, icone: '•' }
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color: '#3730a3', background: '#e0e7ff', padding: '2px 8px', borderRadius: 999, whiteSpace: 'nowrap' }}>
      {f.icone} {f.texto}
    </span>
  )
}

const PRESETS_DIAS = [30, 60, 90] as const

export default function DespachoPage() {
  const qc = useQueryClient()
  const [corrigindoId, setCorrigindoId] = useState<string | null>(null)
  const [buscaProcesso, setBuscaProcesso] = useState('')
  const [gerandoId, setGerandoId] = useState<string | null>(null)
  const [aba, setAba] = useState<'pendentes' | 'tratadas'>('pendentes')
  const [filtroTratadasAberto, setFiltroTratadasAberto] = useState(false)
  const [diasFiltro, setDiasFiltro] = useState<number | null>(null)
  const [dataInicioManual, setDataInicioManual] = useState('')
  const [dataFimManual, setDataFimManual] = useState('')

  const filtroTratadasParams = useMemo(() => {
    if (dataInicioManual || dataFimManual) {
      return { data_inicio: dataInicioManual || undefined, data_fim: dataFimManual || undefined }
    }
    if (diasFiltro) return { dias: diasFiltro }
    return undefined
  }, [diasFiltro, dataInicioManual, dataFimManual])

  const { data: pendentesRaw = [], isLoading: carregandoPendentes } = useQuery({
    queryKey: ['despacho-pendentes'],
    queryFn: () => despachoApi.listarPendentes(),
    enabled: aba === 'pendentes',
  })

  const { data: tratadas = [], isLoading: carregandoTratadas } = useQuery({
    queryKey: ['despacho-tratadas', filtroTratadasParams],
    queryFn: () => despachoApi.listarTratadas(filtroTratadasParams),
    enabled: aba === 'tratadas',
  })

  const pendentes = pendentesRaw
  const isLoading = aba === 'pendentes' ? carregandoPendentes : carregandoTratadas

  const { data: processos = [] } = useQuery({
    queryKey: ['processos-todos'],
    queryFn: () => processosApi.listar(),
    enabled: !!corrigindoId,
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes-todos'],
    queryFn: () => clientesApi.listar(),
    enabled: !!corrigindoId,
  })

  const clienteNomePorId = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of clientes) m.set(c.id, c.nome)
    return m
  }, [clientes])

  const processosFiltrados = useMemo(() => {
    if (!buscaProcesso.trim()) return []
    const q = buscaProcesso.toLowerCase()
    return processos.filter((p) =>
      p.numero_cnj.toLowerCase().includes(q) ||
      (clienteNomePorId.get(p.cliente_id) || '').toLowerCase().includes(q)
    ).slice(0, 15)
  }, [processos, buscaProcesso, clienteNomePorId])

  const confirmar = useMutation({
    mutationFn: ({ id, processoId }: { id: string; processoId: string | null }) =>
      despachoApi.confirmar(id, processoId, true),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
      setCorrigindoId(null)
      setBuscaProcesso('')
    },
  })

  const rejeitar = useMutation({
    mutationFn: (id: string) => despachoApi.rejeitar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['despacho-pendentes'] }),
  })

  const desfazerVinculo = useMutation({
    mutationFn: (id: string) => despachoApi.confirmar(id, null, false),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['despacho-pendentes'] }),
  })

  const reverter = useMutation({
    mutationFn: (id: string) => despachoApi.reverter(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['despacho-tratadas'] })
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
    },
  })

  const gerarSugestao = async (id: string) => {
    setGerandoId(id)
    try {
      await despachoApi.sugerir(id)
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
    } finally {
      setGerandoId(null)
    }
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Despacho</h1>
      </div>
      <p style={{ fontSize: 13, color: 'var(--gray-mid)', marginTop: -8, marginBottom: 12 }}>
        Publicações novas do Diário aguardando confirmação de vínculo e sugestão de ação do gestor jurídico.
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['pendentes', 'tratadas'] as const).map((a) => (
          <button key={a} onClick={() => setAba(a)}
            style={{
              fontSize: 12, fontWeight: 600, padding: '6px 14px', borderRadius: 999, cursor: 'pointer',
              border: aba === a ? 'none' : '1px solid #ddd',
              background: aba === a ? 'var(--teal)' : '#fff',
              color: aba === a ? '#fff' : 'var(--gray-mid)',
            }}
          >
            {a === 'pendentes' ? 'Pendentes' : 'Tratadas'}
          </button>
        ))}
      </div>

      {isLoading && <p>Carregando...</p>}

      {aba === 'tratadas' ? (
        <>
          <div style={{ marginBottom: 14 }}>
            {!filtroTratadasAberto ? (
              <button
                onClick={() => setFiltroTratadasAberto(true)}
                style={{ fontSize: 12, fontWeight: 600, color: 'var(--teal)', background: '#fff', border: '1px solid var(--teal)', borderRadius: 999, padding: '5px 12px', cursor: 'pointer' }}
              >
                {diasFiltro || dataInicioManual || dataFimManual ? '📅 Filtro ativo — ajustar' : '📅 Ver meses anteriores'}
              </button>
            ) : (
              <div style={{ background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 12, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <button
                  onClick={() => { setDiasFiltro(null); setDataInicioManual(''); setDataFimManual('') }}
                  style={{
                    fontSize: 12, fontWeight: 600, padding: '5px 10px', borderRadius: 6, cursor: 'pointer',
                    border: !diasFiltro && !dataInicioManual && !dataFimManual ? 'none' : '1px solid #ddd',
                    background: !diasFiltro && !dataInicioManual && !dataFimManual ? 'var(--teal)' : '#fff',
                    color: !diasFiltro && !dataInicioManual && !dataFimManual ? '#fff' : 'var(--dark)',
                  }}
                >
                  Mês corrente
                </button>
                {PRESETS_DIAS.map((d) => (
                  <button
                    key={d}
                    onClick={() => { setDiasFiltro(d); setDataInicioManual(''); setDataFimManual('') }}
                    style={{
                      fontSize: 12, fontWeight: 600, padding: '5px 10px', borderRadius: 6, cursor: 'pointer',
                      border: diasFiltro === d ? 'none' : '1px solid #ddd',
                      background: diasFiltro === d ? 'var(--teal)' : '#fff',
                      color: diasFiltro === d ? '#fff' : 'var(--dark)',
                    }}
                  >
                    últimos {d} dias
                  </button>
                ))}
                <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>ou:</span>
                <input
                  type="date"
                  value={dataInicioManual}
                  onChange={(e) => { setDataInicioManual(e.target.value); setDiasFiltro(null) }}
                  style={{ fontSize: 12, padding: '5px 8px', border: '1px solid #ddd', borderRadius: 6 }}
                />
                <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>até</span>
                <input
                  type="date"
                  value={dataFimManual}
                  onChange={(e) => { setDataFimManual(e.target.value); setDiasFiltro(null) }}
                  style={{ fontSize: 12, padding: '5px 8px', border: '1px solid #ddd', borderRadius: 6 }}
                />
                <button
                  onClick={() => setFiltroTratadasAberto(false)}
                  style={{ fontSize: 12, color: 'var(--gray-mid)', background: 'none', border: 'none', cursor: 'pointer', marginLeft: 'auto' }}
                >
                  fechar
                </button>
              </div>
            )}
          </div>
          {!isLoading && tratadas.length === 0 && (
            <p style={{ color: 'var(--gray-mid)' }}>Nenhuma publicação tratada ainda.</p>
          )}
          {tratadas.map((p) => (
            <div key={p.id} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 16, marginBottom: 14, maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--dark)', marginBottom: 4, overflowWrap: 'anywhere' }}>
                {p.cliente_nome || p.cliente_nome_pub || 'Cliente não identificado'}
                {(p.processo_numero_cnj || p.numero_cnj) && (
                  <span style={{ fontWeight: 500, color: 'var(--teal)', marginLeft: 8 }}>
                    {p.processo_numero_cnj || p.numero_cnj}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
                <ChipFonte fonte={p.fonte} />
                <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>
                  {p.data_publicacao} · {p.tribunal || '?'} · {p.tipo_ato || 'ato n/d'}
                </span>
              </div>
              <p style={{ fontSize: 13, color: 'var(--dark)', margin: '0 0 8px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{p.texto_resumo}</p>
              {p.rejeitada ? (
                <p style={{ fontSize: 12, color: '#b91c1c', margin: '0 0 8px' }}>✕ Descartada (não era do escritório)</p>
              ) : (
                <>
                  {p.sugestao_acao && (
                    <p style={{ fontSize: 12, color: 'var(--dark)', margin: '0 0 6px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{p.sugestao_acao.resumo_raciocinio}</p>
                  )}
                  {p.prazo_id ? (
                    <p style={{ fontSize: 12, margin: '0 0 4px' }}>
                      📅 Prazo criado — <a href="/prazos" style={{ color: 'var(--teal)' }}>ver em Prazos</a>
                    </p>
                  ) : p.sugestao_acao && (
                    <p style={{ fontSize: 12, color: 'var(--gray-mid)', margin: '0 0 4px' }}>— Sem prazo criado para esta publicação</p>
                  )}
                  {p.tarefas_criadas.length > 0 && (
                    <div style={{ fontSize: 12, margin: '0 0 4px' }}>
                      ✅ Tarefas criadas — <a href="/tarefas" style={{ color: 'var(--teal)' }}>ver em Tarefas</a>
                      <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                        {p.tarefas_criadas.map((t) => (
                          <li key={t.id}>{t.titulo}{t.responsavel ? ` (${t.responsavel})` : ''}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {p.peca_doc_url && (
                    <p style={{ fontSize: 12, margin: '4px 0' }}>
                      📄 <a href={p.peca_doc_url} target="_blank" rel="noreferrer" style={{ color: 'var(--teal)' }}>Abrir peça no Google Docs</a>
                    </p>
                  )}
                </>
              )}
              <button
                onClick={() => reverter.mutate(p.id)}
                disabled={reverter.isPending}
                style={{ fontSize: 12, color: 'var(--gray-mid)', background: 'none', border: '1px solid #ddd', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', marginTop: 8 }}
              >
                ↺ Voltar pra pendentes
              </button>
            </div>
          ))}
        </>
      ) : (
      <>
      {!isLoading && pendentes.length === 0 && (
        <p style={{ color: 'var(--gray-mid)' }}>Nenhuma publicação pendente.</p>
      )}

      {pendentes.map((p) => {
        const conf = CONFIANCA_LABEL[p.confianca]
        return (
          <div key={p.id} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 16, marginBottom: 14, maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--dark)', marginBottom: 4, overflowWrap: 'anywhere' }}>
                  {p.cliente_nome || p.cliente_nome_pub || 'Cliente não identificado'}
                  {(p.processo_numero_cnj || p.numero_cnj) && (
                    <span style={{ fontWeight: 500, color: 'var(--teal)', marginLeft: 8 }}>
                      {p.processo_numero_cnj || p.numero_cnj}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: conf.cor, background: conf.bg, padding: '2px 8px', borderRadius: 999 }}>
                    {conf.texto}
                  </span>
                  <ChipFonte fonte={p.fonte} />
                  <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>
                    {p.data_publicacao} · {p.tribunal || '?'} · {p.tipo_ato || 'ato n/d'}
                  </span>
                </div>
                <p style={{ fontSize: 13, color: 'var(--dark)', margin: '0 0 8px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{p.texto_resumo}</p>
                <p style={{ fontSize: 12, color: 'var(--gray-mid)', margin: 0, overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
                  CNJ extraído: {p.numero_cnj || '—'} · Nome extraído: {p.cliente_nome_pub || '—'}
                </p>
              </div>
            </div>

            {/* Vínculo */}
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #f5f5f5' }}>
              {p.vinculo_confirmado && p.processo_numero_cnj ? (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 13 }}>
                    ✓ Vinculado a <strong>{p.processo_numero_cnj}</strong> ({p.cliente_nome})
                  </span>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {!p.sugestao_acao && (
                      <button
                        onClick={() => gerarSugestao(p.id)}
                        disabled={gerandoId === p.id}
                        style={{ fontSize: 12, fontWeight: 600, color: '#fff', background: 'var(--teal)', border: 'none', borderRadius: 6, padding: '6px 12px', cursor: 'pointer' }}
                      >
                        {gerandoId === p.id ? 'Analisando...' : 'Pedir sugestão de ação'}
                      </button>
                    )}
                    <button
                      onClick={() => { if (confirm('Desfazer o vínculo com este processo? A sugestão/peça geradas serão descartadas.')) desfazerVinculo.mutate(p.id) }}
                      style={{ fontSize: 12, color: '#b91c1c', background: 'none', border: 'none', cursor: 'pointer' }}
                    >
                      desfazer vínculo
                    </button>
                  </div>
                </div>
              ) : corrigindoId === p.id ? (
                <div>
                  <input
                    autoFocus
                    placeholder="Buscar por número CNJ ou nome do cliente..."
                    value={buscaProcesso}
                    onChange={(e) => setBuscaProcesso(e.target.value)}
                    style={{ width: '100%', padding: 8, fontSize: 13, border: '1px solid #ddd', borderRadius: 6, boxSizing: 'border-box' }}
                  />
                  {processosFiltrados.length > 0 && (
                    <ul style={{ listStyle: 'none', margin: '6px 0 0', padding: 0, border: '1px solid #eee', borderRadius: 6, maxHeight: 180, overflowY: 'auto' }}>
                      {processosFiltrados.map((proc) => (
                        <li key={proc.id}
                          onClick={() => confirmar.mutate({ id: p.id, processoId: proc.id })}
                          style={{ padding: '8px 10px', fontSize: 13, cursor: 'pointer', borderBottom: '1px solid #f5f5f5' }}
                        >
                          {proc.numero_cnj} — {clienteNomePorId.get(proc.cliente_id) || '?'}
                        </li>
                      ))}
                    </ul>
                  )}
                  <button onClick={() => { setCorrigindoId(null); setBuscaProcesso('') }}
                    style={{ marginTop: 6, fontSize: 12, color: 'var(--gray-mid)', background: 'none', border: 'none', cursor: 'pointer' }}>
                    cancelar
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 13, color: 'var(--dark)' }}>
                    {p.processo_numero_cnj ? `Está correto? ${p.processo_numero_cnj} — ${p.cliente_nome}` : 'Nenhum processo identificado automaticamente.'}
                  </span>
                  {p.processo_id && (
                    <button
                      onClick={() => confirmar.mutate({ id: p.id, processoId: p.processo_id })}
                      style={{ fontSize: 12, fontWeight: 600, color: '#fff', background: '#15803d', border: 'none', borderRadius: 6, padding: '5px 10px', cursor: 'pointer' }}
                    >
                      Sim, confirmar
                    </button>
                  )}
                  <button
                    onClick={() => setCorrigindoId(p.id)}
                    style={{ fontSize: 12, fontWeight: 600, color: 'var(--teal)', background: 'none', border: '1px solid var(--teal)', borderRadius: 6, padding: '5px 10px', cursor: 'pointer' }}
                  >
                    {p.processo_id ? 'Não, é outro' : 'Selecionar processo'}
                  </button>
                  <button
                    onClick={() => rejeitar.mutate(p.id)}
                    style={{ fontSize: 12, color: '#b91c1c', background: 'none', border: 'none', cursor: 'pointer' }}
                  >
                    Descartar (não é nosso)
                  </button>
                </div>
              )}
            </div>

            {p.sugestao_acao && <SugestaoAcaoPainel publicacao={p} />}
          </div>
        )
      })}
      </>
      )}
    </div>
  )
}

function SugestaoAcaoPainel({ publicacao: p }: { publicacao: PublicacaoPendente }) {
  const qc = useQueryClient()
  const sugestao = p.sugestao_acao!
  const opcoes = sugestao.opcoes_prazo || []

  const [opcaoIdx, setOpcaoIdx] = useState(0)
  const [tarefas, setTarefas] = useState<(TarefaSugerida & { marcada: boolean })[]>(
    (sugestao.tarefas_sugeridas || []).map((t) => ({ ...t, marcada: true }))
  )
  const [novaTarefa, setNovaTarefa] = useState('')
  const [promptExtra, setPromptExtra] = useState('')
  const [tipoPecaManual, setTipoPecaManual] = useState('')
  const [diasPrazoManual, setDiasPrazoManual] = useState<number | ''>('')
  const [tipoContagemManual, setTipoContagemManual] = useState<'uteis' | 'corridos'>('uteis')
  const [gerandoPeca, setGerandoPeca] = useState(false)
  const [aprovando, setAprovando] = useState(false)
  const [responsavelPrazo, setResponsavelPrazo] = useState<{ nome: string; email: string; id?: string | null }>({ nome: '', email: '', id: null })

  const opcaoEscolhida = opcoes[opcaoIdx]
  // Quando a IA não sugeriu nenhum caminho de prazo, ainda assim dá pra gerar
  // uma peça avulsa (ex: uma tarefa manual "peticionar") a partir de um tipo
  // digitado à mão — não cria prazo nenhum, só o documento.
  const opcaoParaPeca = opcaoEscolhida || (tipoPecaManual.trim()
    ? { label: tipoPecaManual.trim(), peca_necessaria: 'outro', dias_prazo: 0, tipo_contagem: 'uteis' as const }
    : null)

  const toggleTarefa = (i: number) =>
    setTarefas((prev) => prev.map((t, idx) => idx === i ? { ...t, marcada: !t.marcada } : t))

  const atualizarResponsavelTarefa = (i: number, v: { nome: string; id?: string | null }) =>
    setTarefas((prev) => prev.map((t, idx) => idx === i ? { ...t, responsavel: v.nome || null, responsavel_id: v.id || null } : t))

  const adicionarTarefa = () => {
    if (!novaTarefa.trim()) return
    setTarefas((prev) => [...prev, { titulo: novaTarefa.trim(), responsavel: null, marcada: true }])
    setNovaTarefa('')
  }

  const gerarPeca = async () => {
    if (!opcaoParaPeca) return
    setGerandoPeca(true)
    try {
      await despachoApi.gerarPeca(p.id, opcaoParaPeca, promptExtra)
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
    } catch {
      // Mesma lógica do fluxo de aprovar: confere o estado real antes de
      // avisar erro, pra não contradizer o que de fato aconteceu.
      const atual = await despachoApi.obter(p.id).catch(() => null)
      if (atual?.peca_doc_url) {
        qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
      } else {
        alert('Não foi possível gerar a peça. Tente de novo.')
      }
    } finally {
      setGerandoPeca(false)
    }
  }

  const aprovar = async () => {
    const prazoParaCriar = opcaoEscolhida ?? (diasPrazoManual
      ? { peca_necessaria: tipoPecaManual.trim() || 'outro', dias_prazo: diasPrazoManual, tipo_contagem: tipoContagemManual }
      : null)

    // Pergunta o responsável antes de registrar — não deixa criar prazo/tarefa órfã.
    if (prazoParaCriar && !responsavelPrazo.nome.trim()) {
      alert('Defina o responsável pelo prazo antes de aprovar.')
      return
    }
    const semResponsavel = tarefas.find((t) => t.marcada && !t.responsavel?.trim())
    if (semResponsavel) {
      alert(`Defina o responsável pela tarefa "${semResponsavel.titulo}" antes de aprovar.`)
      return
    }

    setAprovando(true)
    let erroPeca: string | null = null
    try {
      // Um clique só: gera a peça (se houver o que gerar) e cria prazo/tarefas —
      // mas uma falha na peça NUNCA pode impedir a criação de prazo/tarefas.
      if (opcaoParaPeca && !p.peca_doc_url) {
        try {
          await despachoApi.gerarPeca(p.id, opcaoParaPeca, promptExtra)
        } catch {
          // A chamada pode ter estourado o timeout no cliente mas concluído
          // no servidor (peça + Docs API somados são lentos) — antes de
          // avisar erro, confere o estado real pra não dar mensagem falsa.
          try {
            const atual = await despachoApi.obter(p.id)
            if (!atual.peca_doc_url) {
              erroPeca = 'Não foi possível gerar a peça — prazo e tarefas foram criados mesmo assim.'
            }
          } catch {
            erroPeca = 'Não foi possível gerar a peça — prazo e tarefas foram criados mesmo assim.'
          }
        }
      }
      // Se sobrou texto digitado no campo "+ adicionar tarefa" sem ter clicado
      // em Adicionar, inclui mesmo assim — não pode se perder silenciosamente.
      const tarefasParaEnviar = tarefas.filter((t) => t.marcada).map(({ titulo, responsavel, responsavel_id }) => ({ titulo, responsavel, responsavel_id }))
      if (novaTarefa.trim()) {
        tarefasParaEnviar.push({ titulo: novaTarefa.trim(), responsavel: responsavelPrazo.nome.trim() || null, responsavel_id: responsavelPrazo.id || null })
      }
      const resposta = await despachoApi.aprovar(p.id, {
        criar_prazo: !!prazoParaCriar,
        peca_necessaria: prazoParaCriar?.peca_necessaria ?? null,
        dias_prazo: prazoParaCriar?.dias_prazo ?? null,
        tipo_contagem: prazoParaCriar?.tipo_contagem ?? 'uteis',
        responsavel_prazo: responsavelPrazo.nome.trim() || null,
        responsavel_prazo_id: responsavelPrazo.id || null,
        tarefas: tarefasParaEnviar,
      })
      setNovaTarefa('')
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
      qc.invalidateQueries({ queryKey: ['despacho-tratadas'] })
      qc.invalidateQueries({ queryKey: ['prazos'] })
      const criados = [
        resposta.prazo_id ? '1 prazo' : null,
        resposta.tarefa_ids?.length ? `${resposta.tarefa_ids.length} tarefa(s)` : null,
      ].filter(Boolean).join(' + ')
      if (erroPeca) alert(erroPeca)
      else if (criados) alert(`Criado: ${criados}.`)
      else alert('Nada foi criado — confira se marcou alguma tarefa ou definiu um prazo.')
    } catch {
      alert('Erro ao aprovar. Prazo/tarefas podem não ter sido criados — confira em Prazos e Tarefas.')
    } finally {
      setAprovando(false)
    }
  }

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #f5f5f5', background: '#fafffe', maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
      <p style={{ fontSize: 13, color: 'var(--dark)', margin: '0 0 10px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{sugestao.resumo_raciocinio}</p>

      {opcoes.length > 0 ? (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', marginBottom: 4 }}>
            Caminho / prazo
          </div>
          {opcoes.map((o, i) => (
            <label key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 4, cursor: 'pointer' }}>
              <input type="radio" checked={opcaoIdx === i} onChange={() => setOpcaoIdx(i)} />
              📅 <strong>{o.label}</strong> — {o.dias_prazo} dias {o.tipo_contagem}
            </label>
          ))}
        </div>
      ) : (
        <div style={{ marginBottom: 10 }}>
          <p style={{ fontSize: 12, color: 'var(--gray-mid)', fontStyle: 'italic', margin: '0 0 6px' }}>
            A IA entendeu que esta publicação não exige prazo formal. Se discordar, defina um prazo
            manualmente (fica visível em Prazos) e/ou gere uma peça:
          </p>
          <input
            value={tipoPecaManual}
            onChange={(e) => setTipoPecaManual(e.target.value)}
            placeholder="Tipo de peça (ex: petição juntando documento, manifestação...)"
            style={{ width: '100%', fontSize: 12, padding: '6px 8px', border: '1px solid #ddd', borderRadius: 6, boxSizing: 'border-box', marginBottom: 6 }}
          />
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Prazo:</span>
            <input
              type="number"
              min={1}
              value={diasPrazoManual}
              onChange={(e) => setDiasPrazoManual(e.target.value ? Number(e.target.value) : '')}
              placeholder="dias"
              style={{ width: 70, fontSize: 12, padding: '5px 8px', border: '1px solid #ddd', borderRadius: 6 }}
            />
            <select
              value={tipoContagemManual}
              onChange={(e) => setTipoContagemManual(e.target.value as 'uteis' | 'corridos')}
              style={{ fontSize: 12, padding: '5px 8px', border: '1px solid #ddd', borderRadius: 6 }}
            >
              <option value="uteis">dias úteis</option>
              <option value="corridos">dias corridos</option>
            </select>
          </div>
        </div>
      )}

      {(opcaoEscolhida || diasPrazoManual) && (
        <div style={{ marginBottom: 10, display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Responsável pelo prazo:</span>
          <div style={{ width: 220 }}>
            <ResponsavelComboBox value={responsavelPrazo} onChange={setResponsavelPrazo} />
          </div>
        </div>
      )}

      {(tarefas.length > 0 || novaTarefa) && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', marginBottom: 4 }}>
            Tarefas sugeridas
          </div>
          {tarefas.map((t, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 4 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, cursor: 'pointer' }}>
                <input type="checkbox" checked={t.marcada} onChange={() => toggleTarefa(i)} />
                {t.titulo}
              </label>
              <div style={{ width: 180 }}>
                <ResponsavelComboBox
                  value={{ nome: t.responsavel ?? '', email: '', id: t.responsavel_id }}
                  onChange={(v) => atualizarResponsavelTarefa(i, v)}
                  disabled={!t.marcada}
                />
              </div>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
        <input
          value={novaTarefa}
          onChange={(e) => setNovaTarefa(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') adicionarTarefa() }}
          placeholder="+ adicionar outra tarefa..."
          style={{ flex: 1, fontSize: 12, padding: '5px 8px', border: '1px solid #ddd', borderRadius: 6 }}
        />
        <button onClick={adicionarTarefa} style={{ fontSize: 12, color: 'var(--teal)', background: 'none', border: '1px solid var(--teal)', borderRadius: 6, padding: '5px 10px', cursor: 'pointer' }}>
          Adicionar
        </button>
      </div>

      {opcaoParaPeca && (
        <div style={{ marginBottom: 10 }}>
          <textarea
            placeholder="Prompt extra pra guiar a IA na redação da peça (opcional)..."
            value={promptExtra}
            onChange={(e) => setPromptExtra(e.target.value)}
            rows={2}
            style={{ width: '100%', fontSize: 12, padding: 8, border: '1px solid #ddd', borderRadius: 6, boxSizing: 'border-box', marginBottom: 6 }}
          />
          <button
            onClick={gerarPeca}
            disabled={gerandoPeca}
            style={{ fontSize: 12, fontWeight: 600, color: 'var(--teal)', background: 'none', border: '1px solid var(--teal)', borderRadius: 6, padding: '6px 12px', cursor: 'pointer' }}
          >
            {gerandoPeca ? 'Redigindo e gerando o documento...' : p.peca_doc_url ? 'Gerar peça de novo' : 'Gerar peça no Google Docs'}
          </button>
        </div>
      )}

      {p.peca_gerada && (
        <div style={{ background: '#fff', border: '1px solid #eee', borderRadius: 6, padding: 12, marginBottom: 10, fontSize: 12, maxWidth: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
          {p.peca_doc_url && (
            <p style={{ margin: '0 0 8px' }}>
              📄 <a href={p.peca_doc_url} target="_blank" rel="noreferrer" style={{ color: 'var(--teal)', fontWeight: 600 }}>Abrir peça no Google Docs</a>
            </p>
          )}
          <div style={{ fontWeight: 700, marginBottom: 6, overflowWrap: 'anywhere' }}>{p.peca_gerada.titulo_peca}</div>
          <p style={{ margin: '0 0 6px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{p.peca_gerada.enderecamento}</p>
          <p style={{ margin: '0 0 6px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{p.peca_gerada.qualificacao}</p>
          {p.peca_gerada.paragrafos.map((par, i) => (
            <p key={i} style={{ margin: '0 0 6px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
              {i + 1}. <PecaTexto texto={par} />
            </p>
          ))}
          <p style={{ margin: '0 0 6px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{p.peca_gerada.fechamento}</p>
          {p.peca_gerada.itens_faltantes.length > 0 && (
            <p style={{ color: '#b91c1c', fontWeight: 600, marginTop: 8 }}>
              ⚠ Faltam: {p.peca_gerada.itens_faltantes.join('; ')}
            </p>
          )}
          <p style={{ color: 'var(--gray-mid)', fontSize: 11, marginTop: 8 }}>
            Prévia — revise no Google Docs antes de usar.
          </p>
        </div>
      )}

      <button
        onClick={aprovar}
        disabled={aprovando}
        style={{ fontSize: 12, fontWeight: 600, color: '#fff', background: 'var(--teal)', border: 'none', borderRadius: 6, padding: '6px 14px', cursor: 'pointer' }}
      >
        {aprovando ? 'Aplicando...' : 'Aprovar e criar prazo/tarefas'}
      </button>
    </div>
  )
}

function PecaTexto({ texto }: { texto: string }) {
  const partes = texto.split(/(\*\*[^*]+\*\*|XXX[^X]*XXX)/g)
  return (
    <>
      {partes.map((parte, i) => {
        if (parte.startsWith('**') && parte.endsWith('**')) {
          return <strong key={i}>{parte.slice(2, -2)}</strong>
        }
        if (parte.startsWith('XXX')) {
          return <span key={i} style={{ color: '#dc2626', fontWeight: 700 }}>{parte}</span>
        }
        return <span key={i}>{parte}</span>
      })}
    </>
  )
}
