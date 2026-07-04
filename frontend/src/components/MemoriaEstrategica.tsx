import { useEffect, useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { memoriaEstrategicaApi } from '../api/memoriaEstrategica'

interface Props {
  clienteId?: string
  processoId?: string
}

export default function MemoriaEstrategica({ clienteId, processoId }: Props) {
  const qc = useQueryClient()
  const queryKey = ['memoria-estrategica', clienteId, processoId]
  const [texto, setTexto] = useState('')
  const [mostrarHistorico, setMostrarHistorico] = useState(false)

  const { data: versoes = [] } = useQuery({
    queryKey,
    queryFn: () => memoriaEstrategicaApi.listar({ cliente_id: clienteId, processo_id: processoId }),
  })

  const atual = versoes[0]

  useEffect(() => {
    setTexto(atual?.texto ?? '')
  }, [atual?.id])

  const salvar = useMutation({
    mutationFn: () => memoriaEstrategicaApi.criar({ cliente_id: clienteId, processo_id: processoId, texto }),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const alterado = texto.trim() !== (atual?.texto ?? '').trim()

  return (
    <div style={{
      background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 16, marginBottom: 20,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--dark)', margin: 0 }}>
          Memória Estratégica
        </h3>
        {versoes.length > 1 && (
          <button
            onClick={() => setMostrarHistorico(!mostrarHistorico)}
            style={{ fontSize: 12, color: 'var(--teal)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 }}
          >
            {mostrarHistorico ? 'Ocultar histórico' : `Ver histórico (${versoes.length})`}
          </button>
        )}
      </div>

      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder="O que buscamos com este cliente/processo? Objetivo, estratégia, preferências..."
        rows={4}
        style={{
          width: '100%', fontSize: 13, padding: 10, border: '1px solid #ddd', borderRadius: 6,
          fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box',
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
        <span style={{ fontSize: 11, color: 'var(--gray-mid)' }}>
          {atual ? `Última atualização: ${new Date(atual.created_at).toLocaleString('pt-BR')}` : 'Ainda sem estratégia registrada'}
        </span>
        <button
          onClick={() => salvar.mutate()}
          disabled={!alterado || !texto.trim() || salvar.isPending}
          style={{
            fontSize: 12, fontWeight: 600, padding: '6px 14px', borderRadius: 6, border: 'none',
            background: alterado && texto.trim() ? 'var(--teal)' : '#e5e7eb',
            color: alterado && texto.trim() ? '#fff' : '#9ca3af',
            cursor: alterado && texto.trim() ? 'pointer' : 'not-allowed',
          }}
        >
          {salvar.isPending ? 'Salvando...' : 'Salvar nova versão'}
        </button>
      </div>

      {mostrarHistorico && versoes.length > 1 && (
        <div style={{ marginTop: 12, borderTop: '1px solid #f0f0f0', paddingTop: 10 }}>
          {versoes.slice(1).map((v) => (
            <div key={v.id} style={{ marginBottom: 8, fontSize: 12 }}>
              <div style={{ color: 'var(--gray-mid)', fontSize: 11, marginBottom: 2 }}>
                {new Date(v.created_at).toLocaleString('pt-BR')}
              </div>
              <div style={{ color: 'var(--dark)', whiteSpace: 'pre-wrap' }}>{v.texto}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
