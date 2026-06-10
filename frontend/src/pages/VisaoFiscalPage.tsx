import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fiscalApi } from '../api/fiscal'
import styles from './Page.module.css'
import cs from './FiscalPage.module.css'

function fmtBRL(v: number) {
  return (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function mesAtual() { return new Date().toISOString().slice(0, 7) }

const TRIB_LABEL: Record<string, string> = {
  IRPJ: 'IRPJ', CSLL: 'CSLL', COFINS: 'COFINS', PIS: 'PIS', ISS: 'ISS',
}

function Card({ titulo, valor, cor, sub }: { titulo: string; valor: string; cor?: string; sub?: string }) {
  return (
    <div className={styles.tableCard} style={{ padding: '14px 18px', flex: 1, minWidth: 150 }}>
      <div style={{ fontSize: 11, color: 'var(--gray-mid)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '.05em' }}>{titulo}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: cor || 'var(--dark)', marginTop: 4 }}>{valor}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--gray-mid)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

export default function VisaoFiscalPage() {
  const [mes, setMes] = useState(mesAtual())
  const { data: v, isLoading } = useQuery({
    queryKey: ['visao-fiscal', mes],
    queryFn: () => fiscalApi.visao(mes),
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Visão <strong>Fiscal</strong></h1>
        <input type="month" className={cs.input} style={{ width: 170 }}
          value={mes} onChange={(e) => setMes(e.target.value)} />
      </div>

      {isLoading || !v ? (
        <div className={styles.empty}>Carregando…</div>
      ) : (
        <>
          {/* Alertas */}
          {v.alertas?.length > 0 && (
            <div style={{ marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {v.alertas.map((a: any, i: number) => (
                <div key={i} style={{
                  background: a.nivel === 'alerta' ? '#fef2f2' : '#fffbeb',
                  border: `1px solid ${a.nivel === 'alerta' ? '#fecaca' : '#fde68a'}`,
                  borderRadius: 8, padding: '10px 14px',
                }}>
                  <strong style={{ color: a.nivel === 'alerta' ? '#b91c1c' : '#92400e', fontSize: 13 }}>
                    {a.nivel === 'alerta' ? '🚨' : '⚠️'} {a.titulo}
                  </strong>
                  <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{a.detalhe}</div>
                </div>
              ))}
            </div>
          )}

          {/* Cards principais */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            <Card titulo="Receita do mês" valor={fmtBRL(v.receita_mes)} sub={`${v.qtd_notas} nota(s)`} />
            <Card titulo="DAS estimado" valor={fmtBRL(v.das_estimado)} cor="#b45309" sub={`alíquota ${v.aliquota_efetiva}%`} />
            <Card titulo="Retenções sofridas" valor={fmtBRL(v.retencoes_sofridas)} cor="#15803d" />
            <Card titulo="DAS líquido estim." valor={fmtBRL(v.das_liquido_estimado)} cor="#b45309" sub="após retenções" />
            <Card titulo="Carga tributária" valor={`${v.carga_tributaria_pct}%`} />
          </div>

          {/* Quebra de tributos com % */}
          {v.quebra_tributos && Object.keys(v.quebra_tributos).length > 0 && (
            <div className={styles.tableCard} style={{ marginBottom: 16 }}>
              <table className={styles.table}>
                <thead><tr>
                  <th>Tributo</th>
                  <th style={{ textAlign: 'right' }}>Carga efetiva</th>
                  <th style={{ textAlign: 'right' }}>Valor estimado</th>
                </tr></thead>
                <tbody>
                  {Object.entries(v.quebra_tributos).map(([k, val]: any) => (
                    <tr key={k}>
                      <td>{TRIB_LABEL[k] || k}</td>
                      <td style={{ textAlign: 'right', color: 'var(--gray-mid)' }}>
                        {v.quebra_tributos_pct?.[k] != null ? `${v.quebra_tributos_pct[k]}%` : '—'}
                      </td>
                      <td style={{ textAlign: 'right' }}>{fmtBRL(val)}</td>
                    </tr>
                  ))}
                  <tr style={{ fontWeight: 700 }}>
                    <td>Total DAS (Simples)</td>
                    <td style={{ textAlign: 'right' }}>{v.carga_tributaria_pct}%</td>
                    <td style={{ textAlign: 'right', color: '#b45309' }}>{fmtBRL(v.das_estimado)}</td>
                  </tr>
                  {v.carga_media_pct != null && (
                    <tr style={{ fontWeight: 700, background: '#fffbeb' }}>
                      <td>Carga tributária média (Lei 12.741 / IBPT)</td>
                      <td style={{ textAlign: 'right', color: '#b45309' }}>{v.carga_media_pct}%</td>
                      <td style={{ textAlign: 'right', color: '#b45309' }}>{fmtBRL(v.carga_media_valor)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
              <p className={cs.fieldHint} style={{ marginTop: 6 }}>
                ISS pela alíquota do município; federais rateados pelo Anexo IV. A carga média (16,33%) é a referência IBPT que vai na nota.
              </p>
            </div>
          )}

          {/* Reforma Tributária IBS/CBS */}
          {v.reforma && (
            <div className={styles.tableCard} style={{ padding: 16, marginBottom: 16,
              borderLeft: '3px solid var(--teal)' }}>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>🆕 Reforma Tributária — {v.reforma.fase}</div>
              <div style={{ fontSize: 13, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                <span>ISS vigente: <b>{v.reforma.iss_pct_vigente}%</b> do valor cheio</span>
                <span>IBS estimado: <b>{fmtBRL(v.reforma.ibs_estimado)}</b></span>
                <span>CBS estimado: <b>{fmtBRL(v.reforma.cbs_estimado)}</b></span>
              </div>
              {!v.reforma.ativo && (
                <p className={cs.fieldHint} style={{ marginTop: 8 }}>
                  Configure os % de IBS/CBS e ative o piloto no Config Fiscal para projetar os valores.
                </p>
              )}
            </div>
          )}

          {/* Simples Nacional */}
          <div className={styles.tableCard} style={{ padding: 16 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Simples Nacional</div>
            <div style={{ fontSize: 13, color: 'var(--dark)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              <span>RBT12: <b>{v.rbt12 != null ? fmtBRL(v.rbt12) : '— (informe no Config Fiscal)'}</b></span>
              <span>Faixa atual: <b>{v.faixa_simples ?? '—'}</b></span>
              <span>Alíquota efetiva: <b>{v.aliquota_efetiva}%</b></span>
              <span>Limite da faixa: <b>{v.limite_faixa != null ? fmtBRL(v.limite_faixa) : '—'}</b></span>
            </div>
            {/* Barra de progresso até a próxima faixa */}
            {v.progresso_faixa_pct != null && (
              <div style={{ marginTop: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--gray-mid)', marginBottom: 4 }}>
                  <span>Progresso na Faixa {v.faixa_simples}</span>
                  <span><b>{v.progresso_faixa_pct}%</b> → limite {fmtBRL(v.limite_faixa)}</span>
                </div>
                <div style={{ height: 10, background: '#e5e7eb', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{
                    width: `${Math.min(v.progresso_faixa_pct, 100)}%`, height: '100%',
                    background: v.progresso_faixa_pct >= 95 ? '#dc2626'
                      : v.progresso_faixa_pct >= 80 ? '#f59e0b' : 'var(--teal)',
                    transition: 'width .3s',
                  }} />
                </div>
              </div>
            )}
            <p className={cs.fieldHint} style={{ marginTop: 10 }}>{v.obs}</p>
            <p className={cs.fieldHint}>Valores estimados para conferência — confirme sempre com o contador.</p>
          </div>
        </>
      )}
    </div>
  )
}
