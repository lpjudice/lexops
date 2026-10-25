import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import Modal from './Modal'
import styles from '../pages/Page.module.css'

/** Clientes com celular cadastrado mas sem WhatsApp definido: o usuário confirma, um a um
 *  ou todos de uma vez. "É WhatsApp" copia o número pro campo WhatsApp (usado nos avisos de
 *  assinatura e nos atalhos de contrato); "Não é" guarda a resposta pra não perguntar de novo. */
export default function ConfirmarWhatsappModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const { data: pendentes = [], isLoading } = useQuery({
    queryKey: ['clientes-whatsapp-pendentes'],
    queryFn: clientesApi.whatsappPendentes,
  })

  const responder = useMutation({
    mutationFn: (respostas: { cliente_id: string; e_whatsapp: boolean }[]) => clientesApi.responderWhatsapp(respostas),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clientes-whatsapp-pendentes'] })
      qc.invalidateQueries({ queryKey: ['clientes'] })
    },
  })

  return (
    <Modal title="Confirmar WhatsApp dos clientes" onClose={onClose} width={620}>
      <p style={{ fontSize: 12.5, color: '#6b7280', marginTop: 0 }}>
        Estes clientes têm celular cadastrado, mas ninguém marcou se o número é WhatsApp. Confirme para que ele
        seja usado nos avisos de assinatura e nos atalhos de contrato.
      </p>
      {isLoading && <p style={{ fontSize: 13 }}>Carregando…</p>}
      {!isLoading && pendentes.length === 0 && <p style={{ fontSize: 13 }}>Nada pendente.</p>}
      {pendentes.length > 0 && (
        <>
          <button
            className={styles.btnSmall}
            style={{ marginBottom: 8 }}
            disabled={responder.isPending}
            onClick={() => {
              if (window.confirm(`Marcar os ${pendentes.length} números abaixo como WhatsApp?`)) {
                responder.mutate(pendentes.map((c) => ({ cliente_id: c.id, e_whatsapp: true })))
              }
            }}
          >
            Todos os {pendentes.length} são WhatsApp
          </button>
          <div style={{ maxHeight: 360, overflowY: 'auto', border: '1px solid #e5e7eb', borderRadius: 8 }}>
            {pendentes.map((c) => (
              <div key={c.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 10px', borderBottom: '1px solid #f3f4f6', fontSize: 13 }}>
                <span style={{ flex: 1 }}>{c.nome}</span>
                <span style={{ color: '#6b7280' }}>{c.telefone}</span>
                <button className={styles.btnSmall} disabled={responder.isPending}
                  onClick={() => responder.mutate([{ cliente_id: c.id, e_whatsapp: true }])}>É WhatsApp</button>
                <button className={styles.btnSmall} disabled={responder.isPending}
                  onClick={() => responder.mutate([{ cliente_id: c.id, e_whatsapp: false }])}>Não é</button>
              </div>
            ))}
          </div>
        </>
      )}
    </Modal>
  )
}
