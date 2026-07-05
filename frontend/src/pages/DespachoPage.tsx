import { useMemo, useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { despachoApi } from '../api/despacho'
import type { PublicacaoPendente, TarefaSugerida } from '../api/despacho'
import { processosApi } from '../api/processos'
import { clientesApi } from '../api/clientes'
import styles from './Page.module.css'

const CONFIANCA_LABEL: Record<string, { texto: string; cor: string; bg: string }> = {
  alta: { texto: 'CNJ exato', cor: '#15803d', bg: '#dcfce7' },
  media: { texto: 'OAB', cor: '#92400e', bg: '#fef3c7' },
  baixa: { texto: 'só por nome', cor: '#b91c1c', bg: '#fee2e2' },
  sem_vinculo: { texto: 'sem vínculo', cor: '#6b7280', bg: '#f3f4f6' },
}

export default function DespachoPage() {
  const qc = useQueryClient()
  const [corrigindoId, setCorrigindoId] = useState<string | null>(null)
  const [buscaProcesso, setBuscaProcesso] = useState('')
  const [gerandoId, setGerandoId] = useState<string | null>(null)
  const [aba, setAba] = useState<'pendentes' | 'tratadas'>('pendentes')

  const { data: pendentesRaw = [], isLoading: carregandoPendentes } = useQuery({
    queryKey: ['despacho-pendentes'],
    queryFn: () => despachoApi.listarPendentes(),
    enabled: aba === 'pendentes',
  })

  const { data: tratadas = [], isLoading: carregandoTratadas } = useQuery({
    queryKey: ['despacho-tratadas'],
    queryFn: () => despachoApi.listarTratadas(),
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
          {!isLoading && tratadas.length === 0 && (
            <p style={{ color: 'var(--gray-mid)' }}>Nenhuma publicação tratada ainda.</p>
          )}
          {tratadas.map((p) => (
            <div key={p.id} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 16, marginBottom: 14 }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--dark)', marginBottom: 4 }}>
                {p.cliente_nome || p.cliente_nome_pub || 'Cliente não identificado'}
                {(p.processo_numero_cnj || p.numero_cnj) && (
                  <span style={{ fontWeight: 500, color: 'var(--teal)', marginLeft: 8 }}>
                    {p.processo_numero_cnj || p.numero_cnj}
                  </span>
                )}
              </div>
              <p style={{ fontSize: 12, color: 'var(--gray-mid)', margin: '0 0 8px' }}>
                {p.data_publicacao} · {p.tribunal || '?'} · {p.tipo_ato || 'ato n/d'}
              </p>
              <p style={{ fontSize: 13, color: 'var(--dark)', margin: '0 0 8px' }}>{p.texto_resumo}</p>
              {p.rejeitada ? (
                <p style={{ fontSize: 12, color: '#b91c1c', margin: '0 0 8px' }}>✕ Descartada (não era do escritório)</p>
              ) : (
                <>
                  {p.sugestao_acao && (
                    <p style={{ fontSize: 12, color: 'var(--dark)', margin: '0 0 6px' }}>{p.sugestao_acao.resumo_raciocinio}</p>
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
          <div key={p.id} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 16, marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--dark)', marginBottom: 4 }}>
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
                  <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>
                    {p.data_publicacao} · {p.tribunal || '?'} · {p.tipo_ato || 'ato n/d'}
                  </span>
                </div>
                <p style={{ fontSize: 13, color: 'var(--dark)', margin: '0 0 8px' }}>{p.texto_resumo}</p>
                <p style={{ fontSize: 12, color: 'var(--gray-mid)', margin: 0 }}>
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
  const [gerandoPeca, setGerandoPeca] = useState(false)
  const [aprovando, setAprovando] = useState(false)

  const opcaoEscolhida = opcoes[opcaoIdx]

  const toggleTarefa = (i: number) =>
    setTarefas((prev) => prev.map((t, idx) => idx === i ? { ...t, marcada: !t.marcada } : t))

  const adicionarTarefa = () => {
    if (!novaTarefa.trim()) return
    setTarefas((prev) => [...prev, { titulo: novaTarefa.trim(), responsavel: null, marcada: true }])
    setNovaTarefa('')
  }

  const gerarPeca = async () => {
    if (!opcaoEscolhida) return
    setGerandoPeca(true)
    try {
      await despachoApi.gerarPeca(p.id, opcaoEscolhida, promptExtra)
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
    } finally {
      setGerandoPeca(false)
    }
  }

  const aprovar = async () => {
    setAprovando(true)
    try {
      // Um clique só: se ainda não gerou a peça e há um caminho escolhido, gera agora.
      if (opcaoEscolhida && !p.peca_doc_url) {
        await despachoApi.gerarPeca(p.id, opcaoEscolhida, promptExtra)
      }
      await despachoApi.aprovar(p.id, {
        criar_prazo: sugestao.requer_prazo && !!opcaoEscolhida,
        peca_necessaria: opcaoEscolhida?.peca_necessaria ?? null,
        dias_prazo: opcaoEscolhida?.dias_prazo ?? null,
        tipo_contagem: opcaoEscolhida?.tipo_contagem ?? 'uteis',
        tarefas: tarefas.filter((t) => t.marcada).map(({ titulo, responsavel }) => ({ titulo, responsavel })),
      })
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
      qc.invalidateQueries({ queryKey: ['despacho-tratadas'] })
    } finally {
      setAprovando(false)
    }
  }

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #f5f5f5', background: '#fafffe' }}>
      <p style={{ fontSize: 13, color: 'var(--dark)', margin: '0 0 10px' }}>{sugestao.resumo_raciocinio}</p>

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
        <p style={{ fontSize: 12, color: 'var(--gray-mid)', fontStyle: 'italic', margin: '0 0 10px' }}>
          A IA entendeu que esta publicação não exige prazo/peça — por isso não há campo de instrução
          nem botão de gerar peça aqui. Se achar que devia ter, use "Descartar" acima e trate manualmente,
          ou peça sugestão de novo.
        </p>
      )}

      {(tarefas.length > 0 || novaTarefa) && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', marginBottom: 4 }}>
            Tarefas sugeridas
          </div>
          {tarefas.map((t, i) => (
            <label key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 4, cursor: 'pointer' }}>
              <input type="checkbox" checked={t.marcada} onChange={() => toggleTarefa(i)} />
              {t.titulo} {t.responsavel ? <span style={{ color: 'var(--gray-mid)' }}>({t.responsavel})</span> : null}
            </label>
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

      {opcaoEscolhida && (
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
        <div style={{ background: '#fff', border: '1px solid #eee', borderRadius: 6, padding: 12, marginBottom: 10, fontSize: 12 }}>
          {p.peca_doc_url && (
            <p style={{ margin: '0 0 8px' }}>
              📄 <a href={p.peca_doc_url} target="_blank" rel="noreferrer" style={{ color: 'var(--teal)', fontWeight: 600 }}>Abrir peça no Google Docs</a>
            </p>
          )}
          <div style={{ fontWeight: 700, marginBottom: 6 }}>{p.peca_gerada.titulo_peca}</div>
          <p style={{ margin: '0 0 6px' }}>{p.peca_gerada.enderecamento}</p>
          <p style={{ margin: '0 0 6px' }}>{p.peca_gerada.qualificacao}</p>
          {p.peca_gerada.paragrafos.map((par, i) => (
            <p key={i} style={{ margin: '0 0 6px' }}>
              {i + 1}. <PecaTexto texto={par} />
            </p>
          ))}
          <p style={{ margin: '0 0 6px' }}>{p.peca_gerada.fechamento}</p>
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
