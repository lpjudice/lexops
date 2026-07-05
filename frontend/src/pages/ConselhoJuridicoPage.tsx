import { useMemo, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import { conselhoJuridicoApi } from '../api/conselhoJuridico'
import type { MensagemConselho } from '../api/conselhoJuridico'
import styles from './Page.module.css'

const CORES: Record<string, string> = {
  tributario: '#b45309',
  sucessoes_familia: '#7c3aed',
  civel_contencioso: '#0369a1',
  recursal_processual: '#15803d',
}

interface ThreadEspecialista {
  chave: string
  nome: string
  mensagens: MensagemConselho[]
  carregando: boolean
}

export default function ConselhoJuridicoPage() {
  const [clienteId, setClienteId] = useState('')
  const [processoId, setProcessoId] = useState('')
  const [pergunta, setPergunta] = useState('')
  const [threads, setThreads] = useState<ThreadEspecialista[] | null>(null)

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes-todos'],
    queryFn: () => clientesApi.listar(),
  })

  const { data: processos = [] } = useQuery({
    queryKey: ['processos-todos'],
    queryFn: () => processosApi.listar(),
  })

  const processosDoCliente = useMemo(
    () => processos.filter((p) => p.cliente_id === clienteId),
    [processos, clienteId]
  )

  const iniciar = useMutation({
    mutationFn: () => conselhoJuridicoApi.consultar({
      cliente_id: clienteId || undefined,
      processo_id: processoId || undefined,
      pergunta,
    }),
    onSuccess: (data) => {
      setThreads(data.respostas.map((r) => ({
        chave: r.chave,
        nome: r.nome,
        mensagens: [
          { role: 'user', content: pergunta },
          { role: 'model', content: r.resposta },
        ],
        carregando: false,
      })))
    },
  })

  const podeConsultar = pergunta.trim().length > 0 && (!!clienteId || !!processoId) && !iniciar.isPending

  const perguntarMais = async (chave: string, novaPergunta: string) => {
    if (!threads || !novaPergunta.trim()) return
    const thread = threads.find((t) => t.chave === chave)
    if (!thread) return

    const historicoAtual = thread.mensagens
    setThreads(threads.map((t) => t.chave === chave
      ? { ...t, carregando: true, mensagens: [...t.mensagens, { role: 'user', content: novaPergunta }] }
      : t))

    try {
      const resp = await conselhoJuridicoApi.perguntarUm({
        cliente_id: clienteId || undefined,
        processo_id: processoId || undefined,
        chave,
        pergunta: novaPergunta,
        historico: historicoAtual,
      })
      setThreads((prev) => prev && prev.map((t) => t.chave === chave
        ? { ...t, carregando: false, mensagens: [...t.mensagens, { role: 'model', content: resp.resposta }] }
        : t))
    } catch {
      setThreads((prev) => prev && prev.map((t) => t.chave === chave
        ? { ...t, carregando: false, mensagens: [...t.mensagens, { role: 'model', content: '❌ Erro ao consultar este especialista.' }] }
        : t))
    }
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Conselho Jurídico</h1>
      </div>
      <p style={{ fontSize: 13, color: 'var(--gray-mid)', marginTop: -8, marginBottom: 16 }}>
        Pergunte sobre um cliente ou processo e receba a opinião independente de cada especialista do escritório,
        todos com o contexto real do caso. Depois, aprofunde com cada um separadamente.
      </p>

      <div style={{ background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
          <select
            value={clienteId}
            onChange={(e) => { setClienteId(e.target.value); setProcessoId('') }}
            style={{ flex: 1, minWidth: 220, padding: 8, fontSize: 13, border: '1px solid #ddd', borderRadius: 6 }}
          >
            <option value="">Selecione o cliente...</option>
            {clientes.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </select>
          <select
            value={processoId}
            onChange={(e) => setProcessoId(e.target.value)}
            disabled={!clienteId}
            style={{ flex: 1, minWidth: 220, padding: 8, fontSize: 13, border: '1px solid #ddd', borderRadius: 6 }}
          >
            <option value="">(Cliente inteiro, sem processo específico)</option>
            {processosDoCliente.map((p) => <option key={p.id} value={p.id}>{p.numero_cnj}</option>)}
          </select>
        </div>
        <textarea
          placeholder="O que você quer perguntar ao conselho sobre esse caso?"
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          rows={3}
          style={{ width: '100%', padding: 10, fontSize: 13, border: '1px solid #ddd', borderRadius: 6, boxSizing: 'border-box', marginBottom: 10 }}
        />
        <button
          onClick={() => iniciar.mutate()}
          disabled={!podeConsultar}
          style={{
            fontSize: 13, fontWeight: 600, color: '#fff', border: 'none', borderRadius: 6, padding: '8px 16px',
            cursor: podeConsultar ? 'pointer' : 'not-allowed', background: podeConsultar ? 'var(--teal)' : '#d1d5db',
          }}
        >
          {iniciar.isPending ? 'Consultando o conselho...' : 'Consultar conselho'}
        </button>
      </div>

      {threads && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>
          {threads.map((t) => (
            <EspecialistaCard key={t.chave} thread={t} cor={CORES[t.chave] || '#374151'} onPerguntar={perguntarMais} />
          ))}
        </div>
      )}
    </div>
  )
}

function EspecialistaCard({
  thread, cor, onPerguntar,
}: {
  thread: ThreadEspecialista
  cor: string
  onPerguntar: (chave: string, pergunta: string) => Promise<void>
}) {
  const [followUp, setFollowUp] = useState('')

  const enviar = async () => {
    const texto = followUp.trim()
    if (!texto) return
    setFollowUp('')
    await onPerguntar(thread.chave, texto)
  }

  return (
    <div style={{ background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 14, display: 'flex', flexDirection: 'column' }}>
      <div style={{
        fontSize: 12, fontWeight: 700, color: cor,
        marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.3,
      }}>
        {thread.nome}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
        {thread.mensagens.map((m, i) => (
          <p key={i} style={{
            fontSize: 13, margin: 0, whiteSpace: 'pre-wrap',
            color: m.role === 'user' ? 'var(--gray-mid)' : 'var(--dark)',
            fontStyle: m.role === 'user' ? 'italic' : 'normal',
          }}>
            {m.role === 'user' ? `Você: ${m.content}` : m.content}
          </p>
        ))}
        {thread.carregando && (
          <p style={{ fontSize: 12, color: 'var(--gray-mid)', margin: 0 }}>⏳ pensando...</p>
        )}
      </div>

      <div style={{ display: 'flex', gap: 6, marginTop: 'auto' }}>
        <input
          value={followUp}
          onChange={(e) => setFollowUp(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') enviar() }}
          placeholder={`Aprofundar com ${thread.nome}...`}
          disabled={thread.carregando}
          style={{ flex: 1, padding: '6px 8px', fontSize: 12, border: '1px solid #ddd', borderRadius: 6 }}
        />
        <button
          onClick={enviar}
          disabled={thread.carregando || !followUp.trim()}
          style={{ fontSize: 12, fontWeight: 600, color: '#fff', background: cor, border: 'none', borderRadius: 6, padding: '6px 12px', cursor: 'pointer' }}
        >
          ↑
        </button>
      </div>
    </div>
  )
}
