/**
 * Quadro de recebimentos cliente × mês: programados (próximos 3/6/9/12 meses) ou
 * realizados (últimos 3/6/9/12), com o consolidado e o extrato em PDF (geral ou de um
 * cliente). Os números vêm de /financeiro/quadro/ (mesma regra do PDF).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { financeiroApi } from '../api/financeiro'
import type { SentidoQuadro } from '../api/financeiro'
import styles from '../pages/Page.module.css'
import cs from '../pages/FinanceiroPage.module.css'

const MESES_PT = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
const HORIZONTES = [3, 6, 9, 12]

const num = (v: number) =>
  v ? v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'
const brl = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const chip = (ativo: boolean): React.CSSProperties => ({
  padding: '4px 12px', fontSize: 12, borderRadius: 999, cursor: 'pointer', fontWeight: 600,
  border: `1px solid ${ativo ? '#0f766e' : '#e5e7eb'}`,
  background: ativo ? '#ecfdf5' : '#fff', color: ativo ? '#0f766e' : '#6b7280',
})

export default function QuadroRecebimentos() {
  const [sentido, setSentido] = useState<SentidoQuadro>('futuro')
  const [meses, setMeses] = useState(6)
  const [baixando, setBaixando] = useState<string | null>(null)
  // Fechado por padrão: a tabela cliente×mês pode ficar bem longa e essa seção vem
  // depois de vários outros cards na mesma página.
  const [aberto, setAberto] = useState(false)

  const { data: q, isLoading } = useQuery({
    queryKey: ['financeiro-quadro', sentido, meses],
    queryFn: () => financeiroApi.quadro(sentido, meses),
  })

  const futuro = sentido === 'futuro'

  const baixarPdf = async (clienteId?: string) => {
    setBaixando(clienteId ?? 'todos')
    try {
      const blob = await financeiroApi.quadroPdf(sentido, meses, clienteId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `extrato_${futuro ? 'proximos' : 'ultimos'}_${meses}_meses.pdf`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 10_000)
    } catch (e: any) {
      alert(`Erro ao gerar o PDF:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`)
    } finally {
      setBaixando(null)
    }
  }

  const th: React.CSSProperties = { textAlign: 'right', whiteSpace: 'nowrap' }
  const tdNum: React.CSSProperties = { textAlign: 'right', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }

  return (
    <div className={styles.form} style={{ marginBottom: 24, maxWidth: 'none' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        <div className={cs.sectionTitle} style={{ margin: 0, cursor: 'pointer' }} onClick={() => setAberto((v) => !v)}>
          {futuro ? 'Recebimentos programados' : 'Recebimentos realizados'} {aberto ? '▲' : '▼'}
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="button" style={chip(futuro)} onClick={() => setSentido('futuro')}>Próximos</button>
            <button type="button" style={chip(!futuro)} onClick={() => setSentido('passado')}>Últimos</button>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {HORIZONTES.map((n) => (
              <button key={n} type="button" style={chip(meses === n)} onClick={() => setMeses(n)}>{n} meses</button>
            ))}
          </div>
          <button type="button" className={styles.btnTable} disabled={baixando !== null}
            title="Baixar o extrato em PDF (todos os clientes)" onClick={() => baixarPdf()}>
            {baixando === 'todos' ? '⏳ Gerando...' : '⬇ PDF'}
          </button>
        </div>
      </div>

      {!aberto ? null : isLoading || !q ? (
        <div style={{ fontSize: 13, color: '#6b7280' }}>Carregando…</div>
      ) : q.clientes.length === 0 ? (
        <div style={{ fontSize: 13, color: '#6b7280' }}>
          {futuro ? 'Nada programado nesse período.' : 'Nenhum recebimento nesse período.'}
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 22, flexWrap: 'wrap', fontSize: 13, marginBottom: 10 }}>
            <span>{futuro ? 'Programado' : 'Recebido'} no período: <b>{brl(q.consolidado.valores.reduce((s, v) => s + v, 0))}</b></span>
            {futuro && q.consolidado.atrasado > 0 && (
              <span style={{ color: '#a2585e' }}>Em atraso: <b>{brl(q.consolidado.atrasado)}</b></span>
            )}
            {futuro && q.alem_do_periodo > 0 && (
              <span style={{ color: '#6b7280' }}>Depois do período: {brl(q.alem_do_periodo)}</span>
            )}
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className={cs.recTable}>
              <thead>
                <tr>
                  <th style={{ position: 'sticky', left: 0, background: '#fff' }}>Cliente</th>
                  {futuro && <th style={{ ...th, color: '#a2585e' }}>Em atraso</th>}
                  {q.colunas.map((c) => <th key={`${c.ano}-${c.mes}`} style={th}>{MESES_PT[c.mes - 1]}/{String(c.ano).slice(2)}</th>)}
                  <th style={th}>Total</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {q.clientes.map((c) => (
                  <tr key={c.cliente_id}>
                    <td style={{ position: 'sticky', left: 0, background: '#fff', whiteSpace: 'nowrap' }}>{c.cliente_nome}</td>
                    {futuro && <td style={{ ...tdNum, color: '#a2585e' }}>{num(c.atrasado)}</td>}
                    {c.valores.map((v, i) => <td key={i} style={{ ...tdNum, color: v ? undefined : '#c4c7cc' }}>{num(v)}</td>)}
                    <td style={{ ...tdNum, fontWeight: 700 }}>{num(c.total)}</td>
                    <td>
                      <button type="button" className={styles.btnTable} style={{ padding: '2px 8px', fontSize: 11 }}
                        title={`Extrato em PDF de ${c.cliente_nome}`} disabled={baixando !== null}
                        onClick={() => baixarPdf(c.cliente_id)}>
                        {baixando === c.cliente_id ? '⏳' : 'PDF'}
                      </button>
                    </td>
                  </tr>
                ))}
                <tr style={{ background: '#ecf3f1', fontWeight: 700 }}>
                  <td style={{ position: 'sticky', left: 0, background: '#ecf3f1' }}>Consolidado</td>
                  {futuro && <td style={{ ...tdNum, color: '#a2585e' }}>{num(q.consolidado.atrasado)}</td>}
                  {q.consolidado.valores.map((v, i) => <td key={i} style={tdNum}>{num(v)}</td>)}
                  <td style={tdNum}>{num(q.consolidado.total)}</td>
                  <td></td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
