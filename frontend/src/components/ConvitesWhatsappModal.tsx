import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conselhoApi } from '../api/conselho'
import type { ConviteWhatsappItem } from '../api/conselho'
import Modal from './Modal'
import styles from '../pages/Page.module.css'

const brl = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

function Lista({ titulo, itens, cor }: { titulo: string; itens: ConviteWhatsappItem[]; cor?: string }) {
  if (itens.length === 0) return null
  return (
    <div style={{ marginBottom: 8, fontSize: 12.5 }}>
      <strong style={{ color: cor }}>{titulo} ({itens.length})</strong>
      <div style={{ color: '#6b7280' }}>{itens.map((i) => i.nome).join(', ')}</div>
    </div>
  )
}

/** Convite de evento pela API do WhatsApp (template de marketing — cobrado pela Meta).
 *  Só vai quem autorizou; o botão "Parar de receber" do convite cancela a autorização. */
export default function ConvitesWhatsappModal({ eventoId, eventoNome, onClose }: { eventoId: string; eventoNome: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [reenviar, setReenviar] = useState(false)
  const [atesto, setAtesto] = useState(false)
  const [telefoneTeste, setTelefoneTeste] = useState('')
  const [msg, setMsg] = useState<string | null>(null)

  const { data: prev, isLoading, refetch } = useQuery({
    queryKey: ['convites-whatsapp-preview', eventoId, reenviar],
    queryFn: () => conselhoApi.previewConvitesWhatsapp(eventoId, reenviar),
  })

  const erroApi = (e: any) => e?.response?.data?.detail || e?.message || 'Erro desconhecido'

  const teste = useMutation({
    mutationFn: () => conselhoApi.enviarConvitesWhatsapp(eventoId, { modo: 'teste', telefone_teste: telefoneTeste }),
    onSuccess: () => setMsg('Convite de teste enviado. Confira o texto e os botões no seu WhatsApp (nada foi gravado no evento).'),
    onError: (e) => setMsg(`Falha no teste: ${erroApi(e)}`),
  })

  const semOptinComNumero = prev?.sem_optin ?? []
  const enviar = useMutation({
    mutationFn: () => conselhoApi.enviarConvitesWhatsapp(eventoId, {
      modo: 'real',
      reenviar,
      marcar_optin_ids: atesto ? semOptinComNumero.map((i) => i.id) : [],
      atesto_autorizacao: atesto,
    }),
    onSuccess: (r) => {
      setMsg(`Disparo iniciado para ${r.agendados} convidado(s) (≈ ${brl(r.custo_total_estimado ?? 0)}). Os status aparecem nos cards em instantes.`)
      qc.invalidateQueries({ queryKey: ['conselho-eventos'] })
      refetch()
    },
    onError: (e) => setMsg(`Não enviou: ${erroApi(e)}`),
  })

  const totalAEnviar = (prev?.enviar.length ?? 0) + (atesto ? semOptinComNumero.length : 0)
  const custo = totalAEnviar * (prev?.custo_unitario_estimado ?? 0)

  return (
    <Modal title={`Convidar por WhatsApp — ${eventoNome}`} onClose={onClose} width={560}>
      <p style={{ fontSize: 12.5, color: '#6b7280', marginTop: 0 }}>
        Mensagem de <b>marketing</b> pela API oficial: cobrada pela Meta por mensagem entregue (estimativa {brl(prev?.custo_unitario_estimado ?? 0.3217)} cada).
        O convite traz os botões “Vou participar”, “Não poderei” e “Parar de receber”; a resposta atualiza o convidado sozinha.
      </p>

      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 10, marginBottom: 12 }}>
        <label className={styles.formLabel}>1. Teste primeiro (só para o seu número)</label>
        <div style={{ display: 'flex', gap: 6 }}>
          <input className={styles.input} placeholder="(27) 9XXXX-XXXX" value={telefoneTeste} onChange={(e) => setTelefoneTeste(e.target.value)} />
          <button className={styles.btnSmall} disabled={teste.isPending || telefoneTeste.replace(/\D/g, '').length < 10} onClick={() => teste.mutate()}>
            {teste.isPending ? 'Enviando…' : 'Enviar teste'}
          </button>
        </div>
      </div>

      <label className={styles.formLabel}>2. Disparo real</label>
      {isLoading && <p style={{ fontSize: 13 }}>Carregando…</p>}
      {prev && (
        <>
          <Lista titulo="Receberão" itens={prev.enviar} cor="#15803d" />
          <Lista titulo="Sem autorização de WhatsApp (ficam de fora, a menos que você ateste abaixo)" itens={prev.sem_optin} cor="#b45309" />
          <Lista titulo="Pediram para parar (nunca recebem)" itens={prev.optout} cor="#b91c1c" />
          <Lista titulo="Sem número de WhatsApp" itens={prev.sem_whatsapp} />
          <Lista titulo="Já receberam este convite" itens={prev.ja_enviado} />

          {semOptinComNumero.length > 0 && (
            <label style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 12.5, margin: '8px 0' }}>
              <input type="checkbox" style={{ marginTop: 3 }} checked={atesto} onChange={(e) => setAtesto(e.target.checked)} />
              Atesto que os {semOptinComNumero.length} contato(s) sem autorização acima concordaram em receber mensagens do escritório por WhatsApp (será gravado como autorização).
            </label>
          )}
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12.5, marginBottom: 8 }}>
            <input type="checkbox" checked={reenviar} onChange={(e) => setReenviar(e.target.checked)} />
            Reenviar também a quem já recebeu
          </label>

          <button
            className={styles.btnPrimary}
            disabled={enviar.isPending || totalAEnviar === 0}
            onClick={() => {
              if (window.confirm(`Enviar o convite a ${totalAEnviar} pessoa(s) por WhatsApp?\n\nCusto estimado: ${brl(custo)} (cobrado pela Meta). Não dá para desfazer.`)) enviar.mutate()
            }}
          >
            {enviar.isPending ? 'Disparando…' : `Enviar a ${totalAEnviar} pessoa(s) — ≈ ${brl(custo)}`}
          </button>
        </>
      )}
      {msg && <p style={{ fontSize: 13, marginTop: 10 }}>{msg}</p>}
    </Modal>
  )
}
