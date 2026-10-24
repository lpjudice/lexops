import { useMutation, useQueryClient } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import type { Cliente } from '../api/clientes'
import { ehCelular } from '../utils/masks'

type Estado = 'confirmado' | 'nao' | 'pendente' | null

/** Situação do telefone do cliente quanto a ser WhatsApp:
 *  confirmado = há número no campo WhatsApp; nao = alguém respondeu "não é";
 *  pendente = celular que ainda ninguém confirmou; null = fixo/sem telefone (não se aplica). */
export function estadoWhatsapp(c: Pick<Cliente, 'telefone' | 'whatsapp' | 'telefone_whatsapp'>): Estado {
  if ((c.whatsapp || '').trim()) return 'confirmado'
  if (c.telefone_whatsapp === false) return 'nao'
  if (ehCelular(c.telefone) && c.telefone_whatsapp == null) return 'pendente'
  return null
}

const ESTILO: Record<Exclude<Estado, null>, { txt: string; cor: string; bg: string }> = {
  confirmado: { txt: 'WhatsApp ✓', cor: '#15803d', bg: '#dcfce7' },
  nao: { txt: 'não é WhatsApp', cor: '#6b7280', bg: '#f3f4f6' },
  pendente: { txt: 'WhatsApp: confirmar', cor: '#b45309', bg: '#fef3c7' },
}

/** Selo na lista (só mostra) e, com `interativo`, botões Sim/Não pra responder na hora. */
export default function WhatsappBadge({ cliente, interativo = false }: { cliente: Cliente; interativo?: boolean }) {
  const qc = useQueryClient()
  const responder = useMutation({
    mutationFn: (e_whatsapp: boolean) => clientesApi.responderWhatsapp([{ cliente_id: cliente.id, e_whatsapp }]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clientes'] })
      qc.invalidateQueries({ queryKey: ['cliente', cliente.id] })
      qc.invalidateQueries({ queryKey: ['clientes-whatsapp-pendentes'] })
    },
  })

  const estado = estadoWhatsapp(cliente)
  if (!estado) return null
  const s = ESTILO[estado]
  return (
    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }} onClick={(e) => e.stopPropagation()}>
      <span style={{ fontSize: 10.5, padding: '1px 7px', borderRadius: 10, color: s.cor, background: s.bg, whiteSpace: 'nowrap' }}
        title={estado === 'pendente' ? 'Ninguém confirmou ainda se este celular é WhatsApp' : undefined}>
        {s.txt}
      </span>
      {interativo && estado === 'pendente' && (
        <>
          <button type="button" style={{ fontSize: 11, cursor: 'pointer' }} disabled={responder.isPending} onClick={() => responder.mutate(true)}>É WhatsApp</button>
          <button type="button" style={{ fontSize: 11, cursor: 'pointer' }} disabled={responder.isPending} onClick={() => responder.mutate(false)}>Não é</button>
        </>
      )}
    </span>
  )
}
