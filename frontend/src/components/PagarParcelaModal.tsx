import { useState } from 'react'
import { financeiroApi } from '../api/financeiro'
import type { FormaPagamento } from '../api/financeiro'

const FORMAS: FormaPagamento[] = ['pix', 'ted', 'boleto', 'cheque', 'dinheiro', 'outro']

interface Props {
  parcelaId: string
  numero: number
  valor: number
  onClose: () => void
  onConfirmed: () => void
}

function fmtVal(v: number) {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

export default function PagarParcelaModal({ parcelaId, numero, valor, onClose, onConfirmed }: Props) {
  const [dataRecebimento, setDataRecebimento] = useState(new Date().toISOString().slice(0, 10))
  const [forma, setForma] = useState<FormaPagamento>('pix')
  const [comentario, setComentario] = useState('')
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const confirmar = async () => {
    setSalvando(true)
    setErro(null)
    try {
      const resultado = await financeiroApi.pagarParcela(parcelaId, {
        data_recebimento: dataRecebimento,
        forma_pagamento: forma,
        observacao: comentario.trim(),
      })
      if (arquivo) {
        try {
          await financeiroApi.uploadComprovante(resultado.recebimento_id, arquivo)
        } catch {
          // Pagamento já confirmado; só o anexo falhou — não bloqueia o fluxo.
        }
      }
      onConfirmed()
      onClose()
    } catch (e: any) {
      setErro(e?.response?.data?.detail || e?.message || 'Falha ao confirmar o pagamento.')
    } finally {
      setSalvando(false)
    }
  }

  return (
    <div style={overlay} onMouseDown={onClose}>
      <div style={card} onMouseDown={(e) => e.stopPropagation()}>
        <div style={header}>
          <strong>✓ Confirmar pagamento — Parcela {numero}</strong>
          <button style={xBtn} onClick={onClose}>×</button>
        </div>
        <div style={{ padding: '16px 20px' }}>
          <p style={{ margin: '0 0 16px', fontSize: 13, color: '#6b7280' }}>
            Valor: <b style={{ color: '#111827' }}>{fmtVal(valor)}</b>
          </p>

          <div style={row}>
            <label style={label}>Data do recebimento</label>
            <input type="date" style={inp} value={dataRecebimento}
              onChange={(e) => setDataRecebimento(e.target.value)} />
          </div>
          <div style={row}>
            <label style={label}>Forma de pagamento</label>
            <select style={inp} value={forma} onChange={(e) => setForma(e.target.value as FormaPagamento)}>
              {FORMAS.map((f) => <option key={f} value={f}>{f.toUpperCase()}</option>)}
            </select>
          </div>
          <div style={row}>
            <label style={label}>Como você confirmou o pagamento? *</label>
            <textarea style={{ ...inp, resize: 'vertical' }} rows={3}
              placeholder="Ex.: extrato bancário, cliente avisou por WhatsApp, comprovante recebido por e-mail..."
              value={comentario}
              onChange={(e) => setComentario(e.target.value)} />
          </div>
          <div style={row}>
            <label style={label}>Anexo (opcional)</label>
            <input type="file" accept="image/*,.pdf"
              onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
          </div>

          {erro && <div style={erroBox}>❌ {erro}</div>}

          <div style={footer}>
            <button style={btnGhost} onClick={onClose} disabled={salvando}>Cancelar</button>
            <button style={btnPrimary}
              disabled={salvando || !comentario.trim()}
              onClick={confirmar}>
              {salvando ? '⏳ Confirmando…' : 'Confirmar pagamento'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
  display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '8vh 16px', overflowY: 'auto',
}
const card: React.CSSProperties = {
  background: '#fff', borderRadius: 12, width: 'min(440px, 100%)', boxShadow: '0 10px 40px rgba(0,0,0,.25)',
}
const header: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  padding: '14px 20px', borderBottom: '1px solid #eee',
}
const xBtn: React.CSSProperties = { border: 'none', background: 'none', fontSize: 22, cursor: 'pointer', color: '#9ca3af' }
const row: React.CSSProperties = { marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 4 }
const label: React.CSSProperties = { fontSize: 12, fontWeight: 600, color: '#374151' }
const inp: React.CSSProperties = { padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, fontFamily: 'inherit' }
const footer: React.CSSProperties = { display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }
const erroBox: React.CSSProperties = { padding: 10, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, color: '#b91c1c', fontSize: 12, marginBottom: 12 }
const btnPrimary: React.CSSProperties = { padding: '8px 16px', border: 'none', borderRadius: 8, background: '#2563eb', color: '#fff', fontWeight: 600, cursor: 'pointer' }
const btnGhost: React.CSSProperties = { padding: '8px 16px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', cursor: 'pointer' }
