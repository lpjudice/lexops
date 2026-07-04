import { useMemo, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import { conselhoJuridicoApi } from '../api/conselhoJuridico'
import type { RespostaEspecialista } from '../api/conselhoJuridico'
import styles from './Page.module.css'

const CORES: Record<string, string> = {
  tributario: '#b45309',
  sucessoes_familia: '#7c3aed',
  civel_contencioso: '#0369a1',
  recursal_processual: '#15803d',
}

export default function ConselhoJuridicoPage() {
  const [clienteId, setClienteId] = useState('')
  const [processoId, setProcessoId] = useState('')
  const [pergunta, setPergunta] = useState('')
  const [respostas, setRespostas] = useState<RespostaEspecialista[] | null>(null)

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

  const consultar = useMutation({
    mutationFn: () => conselhoJuridicoApi.consultar({
      cliente_id: clienteId || undefined,
      processo_id: processoId || undefined,
      pergunta,
    }),
    onSuccess: (data) => setRespostas(data.respostas),
  })

  const podeConsultar = pergunta.trim().length > 0 && (!!clienteId || !!processoId) && !consultar.isPending

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Conselho Jurídico</h1>
      </div>
      <p style={{ fontSize: 13, color: 'var(--gray-mid)', marginTop: -8, marginBottom: 16 }}>
        Pergunte sobre um cliente ou processo e receba a opinião independente de cada especialista do escritório,
        todos com o contexto real do caso.
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
          onClick={() => consultar.mutate()}
          disabled={!podeConsultar}
          style={{
            fontSize: 13, fontWeight: 600, color: '#fff', border: 'none', borderRadius: 6, padding: '8px 16px',
            cursor: podeConsultar ? 'pointer' : 'not-allowed', background: podeConsultar ? 'var(--teal)' : '#d1d5db',
          }}
        >
          {consultar.isPending ? 'Consultando o conselho...' : 'Consultar conselho'}
        </button>
      </div>

      {respostas && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
          {respostas.map((r) => (
            <div key={r.chave} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 14 }}>
              <div style={{
                fontSize: 12, fontWeight: 700, color: CORES[r.chave] || '#374151',
                marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.3,
              }}>
                {r.nome}
              </div>
              <p style={{ fontSize: 13, color: 'var(--dark)', margin: 0, whiteSpace: 'pre-wrap' }}>{r.resposta}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
