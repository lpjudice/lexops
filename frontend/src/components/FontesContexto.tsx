import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'

interface Props {
  clienteId?: string
  processoId?: string
}

export default function FontesContexto({ clienteId, processoId }: Props) {
  const [aberto, setAberto] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['contexto-ia', clienteId, processoId],
    queryFn: () => (processoId ? processosApi.obterContexto(processoId) : clientesApi.obterContexto(clienteId!)),
    enabled: aberto,
  })

  const classificar = useMutation({
    mutationFn: () => clientesApi.classificarEmailsPendentes(clienteId!),
    onSuccess: () => refetch(),
  })

  return (
    <div style={{
      background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 12, marginBottom: 20,
    }}>
      <button
        onClick={() => { setAberto(!aberto); if (!aberto) refetch() }}
        style={{
          fontSize: 12, fontWeight: 600, color: 'var(--teal)', background: 'none', border: 'none',
          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, padding: 0,
        }}
      >
        {aberto ? '▾' : '▸'} O que a IA sabe sobre {processoId ? 'este processo' : 'este cliente'}
      </button>

      {aberto && (
        <div style={{ marginTop: 10 }}>
          {isLoading ? (
            <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Carregando...</span>
          ) : (
            <pre style={{
              whiteSpace: 'pre-wrap', fontSize: 12, fontFamily: 'inherit', color: 'var(--dark)',
              margin: 0, maxHeight: 400, overflowY: 'auto', lineHeight: 1.5,
            }}>
              {data?.contexto || 'Sem contexto disponível ainda.'}
            </pre>
          )}
          <p style={{ fontSize: 11, color: 'var(--gray-mid)', marginTop: 8, marginBottom: 0 }}>
            Este é exatamente o texto enviado ao modelo em cada pergunta do chat — inclui só o que
            você tem permissão de ver (ex: financeiro some se você não tiver acesso), e só e-mails
            já classificados como relevantes (processual/comercial) — ruído pessoal é filtrado.
          </p>
          {clienteId && !processoId && (
            <button
              onClick={() => classificar.mutate()}
              disabled={classificar.isPending}
              style={{
                marginTop: 8, fontSize: 11, fontWeight: 600, color: 'var(--teal)', background: 'none',
                border: '1px solid var(--teal)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer',
              }}
            >
              {classificar.isPending
                ? 'Classificando...'
                : classificar.data
                  ? `${classificar.data.classificados} e-mail(s) classificado(s)`
                  : 'Classificar e-mails pendentes'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
