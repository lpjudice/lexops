import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

const fmtBRL = (v: number | null | undefined) =>
  v == null ? '—' : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

export default function ReformaPublicaPage() {
  const { token } = useParams()
  const [data, setData] = useState<any>(null)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    fetch(`/api/publico/reforma/${token}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then(setData)
      .catch(() => setErro('Link inválido, revogado ou expirado.'))
  }, [token])

  if (erro) return <Centro>{erro}</Centro>
  if (!data) return <Centro>Carregando…</Centro>

  const r = data.reforma
  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '32px 20px', fontFamily: 'system-ui, sans-serif', color: '#1f2937' }}>
      <div style={{ borderBottom: '2px solid #0d9488', paddingBottom: 16, marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22, color: '#0f766e' }}>{data.escritorio}</h1>
        <div style={{ color: '#6b7280', fontSize: 14, marginTop: 4 }}>
          CNPJ {data.cnpj} · {data.municipio} · {data.regime} (Anexo {data.anexo})
        </div>
        <div style={{ color: '#6b7280', fontSize: 13, marginTop: 4 }}>
          Material de apoio à validação contábil — Reforma Tributária (IBS/CBS) · gerado em{' '}
          {new Date(data.gerado_em + 'T12:00:00').toLocaleDateString('pt-BR')}
        </div>
      </div>

      {/* Fase atual */}
      <section style={card}>
        <h2 style={h2}>Fase atual — {r.fase}</h2>
        <div style={grid3}>
          <Item label="ISS vigente" valor={`${r.iss_pct_vigente}% do valor cheio`} />
          <Item label={`CBS (${r.cbs_aliq}%)`} valor={fmtBRL(r.cbs_estimado)} />
          <Item label={`IBS (${r.ibs_aliq}%)`} valor={fmtBRL(r.ibs_estimado)} />
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          {r.cbs_destaque_obrigatorio && <Badge bg="#fee2e2" fg="#b91c1c">CBS: destaque obrigatório</Badge>}
          {r.compensavel_2026 && <Badge bg="#dcfce7" fg="#15803d">2026: compensável com PIS/COFINS</Badge>}
        </div>
        <p style={hint}>Alíquotas já com a redução de {r.reducao_advocacia_pct}% da advocacia. {r.nota}</p>
      </section>

      {/* Projeção plurianual */}
      <section style={card}>
        <h2 style={h2}>Projeção da transição 2026 → 2033</h2>
        <table style={tbl}>
          <thead><tr>
            <th style={th}>Ano</th><th style={th}>ISS vigente</th>
            <th style={{ ...th, textAlign: 'right' }}>CBS</th>
            <th style={{ ...th, textAlign: 'right' }}>IBS</th><th style={th}>Fase</th>
          </tr></thead>
          <tbody>
            {r.projecao.map((l: any) => (
              <tr key={l.ano} style={l.ano === r.ano ? { background: '#f0fdfa', fontWeight: 600 } : undefined}>
                <td style={td}>{l.ano}</td>
                <td style={td}>{l.iss_pct_vigente}%</td>
                <td style={{ ...td, textAlign: 'right' }}>{l.cbs_aliq}% · {fmtBRL(l.cbs_estimado)}</td>
                <td style={{ ...td, textAlign: 'right' }}>{l.ibs_aliq}% · {fmtBRL(l.ibs_estimado)}</td>
                <td style={{ ...td, fontSize: 12, color: '#6b7280' }}>{l.fase}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={hint}>Base: receita de {data.competencia_referencia} ({fmtBRL(data.receita_referencia)}). Alíquotas de 2027+ dependem de regulamentação.</p>
      </section>

      {/* Receita por competência */}
      <section style={card}>
        <h2 style={h2}>Receita por competência (últimos 12 meses no sistema)</h2>
        <table style={tbl}>
          <thead><tr>
            <th style={th}>Competência</th><th style={{ ...th, textAlign: 'right' }}>Notas</th>
            <th style={{ ...th, textAlign: 'right' }}>Receita</th>
            <th style={{ ...th, textAlign: 'right' }}>DAS estimado</th>
          </tr></thead>
          <tbody>
            {data.competencias.map((c: any) => (
              <tr key={c.competencia}>
                <td style={td}>{c.competencia}</td>
                <td style={{ ...td, textAlign: 'right' }}>{c.qtd_notas}</td>
                <td style={{ ...td, textAlign: 'right' }}>{fmtBRL(c.receita)}</td>
                <td style={{ ...td, textAlign: 'right' }}>{fmtBRL(c.das_estimado)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={hint}>Alíquota efetiva do Simples usada: {data.aliquota_efetiva_simples != null ? `${data.aliquota_efetiva_simples}%` : '— (informar RBT12)'}. Carga média informada na nota: {data.carga_media_pct}%.</p>
      </section>

      <p style={{ ...hint, textAlign: 'center', marginTop: 24 }}>{data.observacao}</p>
    </div>
  )
}

const card: React.CSSProperties = { border: '1px solid #e5e7eb', borderRadius: 10, padding: 20, marginBottom: 18, background: '#fff' }
const h2: React.CSSProperties = { fontSize: 16, margin: '0 0 14px', color: '#0f766e' }
const grid3: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }
const hint: React.CSSProperties = { fontSize: 12, color: '#6b7280', marginTop: 12, marginBottom: 0 }
const tbl: React.CSSProperties = { width: '100%', borderCollapse: 'collapse', fontSize: 13 }
const th: React.CSSProperties = { textAlign: 'left', padding: '8px 10px', borderBottom: '2px solid #e5e7eb', color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }
const td: React.CSSProperties = { padding: '8px 10px', borderBottom: '1px solid #f3f4f6' }

function Item({ label, valor }: { label: string; valor: string }) {
  return <div><div style={{ fontSize: 12, color: '#6b7280' }}>{label}</div><div style={{ fontWeight: 700 }}>{valor}</div></div>
}
function Badge({ children, bg, fg }: { children: React.ReactNode; bg: string; fg: string }) {
  return <span style={{ background: bg, color: fg, fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 999 }}>{children}</span>
}
function Centro({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'flex', minHeight: '60vh', alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontFamily: 'system-ui' }}>{children}</div>
}
