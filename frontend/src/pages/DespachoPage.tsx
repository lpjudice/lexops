import { useMemo, useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { despachoApi } from '../api/despacho'
import type { PublicacaoPendente } from '../api/despacho'
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
  const [corrigindoId, setCorrigindoId] = useState<string | null>(null);
  const [buscaProcesso, setBuscaProcesso] = useState('')
  const [gerandoId, setGerandoId] = useState<string | null>(null)
  const [aprovandoId, setAprovandoId] = useState<string | null>(null)

  const { data: pendentes = [], isLoading } = useQuery({
    queryKey: ['despacho-pendentes'],
    queryFn: () => despachoApi.listarPendentes(),
  })

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

  const gerarSugestao = async (id: string) => {
    setGerandoId(id)
    try {
      await despachoApi.sugerir(id)
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
    } finally {
      setGerandoId(null)
    }
  }

  const aprovar = async (p: PublicacaoPendente) => {
    if (!p.sugestao_acao) return
    setAprovandoId(p.id)
    try {
      await despachoApi.aprovar(p.id, {
        criar_prazo: p.sugestao_acao.requer_prazo,
        criar_tarefa: !!p.sugestao_acao.tarefa_titulo,
        peca_necessaria: p.sugestao_acao.peca_necessaria,
        dias_prazo: p.sugestao_acao.dias_prazo,
        tipo_contagem: p.sugestao_acao.tipo_contagem,
        tarefa_titulo: p.sugestao_acao.tarefa_titulo,
        tarefa_responsavel: p.sugestao_acao.tarefa_responsavel,
      })
      qc.invalidateQueries({ queryKey: ['despacho-pendentes'] })
    } finally {
      setAprovandoId(null)
    }
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Despacho</h1>
      </div>
      <p style={{ fontSize: 13, color: 'var(--gray-mid)', marginTop: -8, marginBottom: 16 }}>
        Publicações novas do Diário aguardando confirmação de vínculo e sugestão de ação do gestor jurídico.
      </p>

      {isLoading && <p>Carregando...</p>}
      {!isLoading && pendentes.length === 0 && (
        <p style={{ color: 'var(--gray-mid)' }}>Nenhuma publicação pendente.</p>
      )}

      {pendentes.map((p) => {
        const conf = CONFIANCA_LABEL[p.confianca]
        return (
          <div key={p.id} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 16, marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flex: 1 }}>
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
                  {!p.sugestao_acao && (
                    <button
                      onClick={() => gerarSugestao(p.id)}
                      disabled={gerandoId === p.id}
                      style={{ fontSize: 12, fontWeight: 600, color: '#fff', background: 'var(--teal)', border: 'none', borderRadius: 6, padding: '6px 12px', cursor: 'pointer' }}
                    >
                      {gerandoId === p.id ? 'Analisando...' : 'Pedir sugestão de ação'}
                    </button>
                  )}
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

            {/* Sugestão de ação */}
            {p.sugestao_acao && (
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #f5f5f5', background: '#fafffe' }}>
                <p style={{ fontSize: 13, color: 'var(--dark)', margin: '0 0 8px' }}>{p.sugestao_acao.resumo_raciocinio}</p>
                {p.sugestao_acao.requer_prazo && (
                  <p style={{ fontSize: 12, margin: '0 0 4px' }}>
                    📅 Prazo sugerido: <strong>{p.sugestao_acao.peca_necessaria}</strong> — {p.sugestao_acao.dias_prazo} dias {p.sugestao_acao.tipo_contagem}
                  </p>
                )}
                {p.sugestao_acao.tarefa_titulo && (
                  <p style={{ fontSize: 12, margin: '0 0 4px' }}>
                    ✅ Tarefa sugerida: {p.sugestao_acao.tarefa_titulo} {p.sugestao_acao.tarefa_responsavel ? `(${p.sugestao_acao.tarefa_responsavel})` : ''}
                  </p>
                )}
                {p.sugestao_acao.rascunho_sugerido && (
                  <p style={{ fontSize: 12, margin: '0 0 8px', fontStyle: 'italic', color: 'var(--gray-mid)' }}>
                    "{p.sugestao_acao.rascunho_sugerido}"
                  </p>
                )}
                <button
                  onClick={() => aprovar(p)}
                  disabled={aprovandoId === p.id}
                  style={{ fontSize: 12, fontWeight: 600, color: '#fff', background: 'var(--teal)', border: 'none', borderRadius: 6, padding: '6px 14px', cursor: 'pointer' }}
                >
                  {aprovandoId === p.id ? 'Aplicando...' : 'Aprovar e criar prazo/tarefa'}
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
