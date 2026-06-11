import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { configFiscalApi } from '../api/configFiscal'
import type { ConfigFiscal } from '../api/configFiscal'
import { fiscalApi } from '../api/fiscal'
import styles from './Page.module.css'
import cs from './FiscalPage.module.css'

// ─── Popup: Tabela do Simples + ISS Vitória/ES ────────────────────────────────

const FAIXAS_SN_IV = [
  { faixa: 'Até R$ 180 mil',        aliq: 4.50, ded: 0,          issComp: 2.00 },
  { faixa: 'De R$ 180k a R$ 360k',  aliq: 9.00, ded: 8_100,      issComp: 3.00 },
  { faixa: 'De R$ 360k a R$ 720k',  aliq: 10.20, ded: 12_420,    issComp: 3.50 },
  { faixa: 'De R$ 720k a R$ 1,8M',  aliq: 14.00, ded: 39_780,    issComp: 4.00 },
  { faixa: 'De R$ 1,8M a R$ 3,6M',  aliq: 22.00, ded: 183_780,   issComp: 5.00 },
  { faixa: 'De R$ 3,6M a R$ 4,8M',  aliq: 33.00, ded: 828_000,   issComp: 5.00 },
]

function calcAliqEfetiva(rbt12: number, aliq: number, ded: number) {
  if (!rbt12) return null
  return ((rbt12 * aliq / 100) - ded) / rbt12 * 100
}

function PopupSimples({ onClose, rbt12 }: { onClose: () => void; rbt12?: number }) {
  const fmtR = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{ background: '#fff', borderRadius: 12, width: '100%', maxWidth: 680, maxHeight: '90vh', overflow: 'auto', padding: 28, position: 'relative' }}>
        <button onClick={onClose} style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--gray-mid)' }}>✕</button>

        <h2 style={{ fontFamily: 'Archivo, sans-serif', fontSize: 16, fontWeight: 800, marginBottom: 4, color: 'var(--dark)' }}>
          Simples Nacional — Anexo IV (Serviços Advocatícios)
        </h2>
        <p style={{ fontSize: 12, color: 'var(--gray-mid)', marginBottom: 16 }}>
          LC 123/2006, Anexo IV. CPP (INSS patronal) pago separadamente, fora do DAS.
          {rbt12 ? ` RBT12 informado: ${fmtR(rbt12)}.` : ''}
        </p>
        <div style={{ overflowX: 'auto', marginBottom: 24 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f3f4f6' }}>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', fontSize: 10, letterSpacing: '.05em' }}>Faixa (RBT12)</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', fontSize: 10, letterSpacing: '.05em' }}>Alíq. nominal</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', fontSize: 10, letterSpacing: '.05em' }}>Dedução (R$)</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', fontSize: 10, letterSpacing: '.05em' }}>ISS no DAS</th>
                {rbt12 && <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', fontSize: 10, letterSpacing: '.05em' }}>Alíq. efetiva</th>}
              </tr>
            </thead>
            <tbody>
              {FAIXAS_SN_IV.map((f, i) => {
                const ef = rbt12 ? calcAliqEfetiva(rbt12, f.aliq, f.ded) : null
                const faixaAtual = rbt12 && (
                  (i === 0 && rbt12 <= 180_000) ||
                  (i === 1 && rbt12 > 180_000 && rbt12 <= 360_000) ||
                  (i === 2 && rbt12 > 360_000 && rbt12 <= 720_000) ||
                  (i === 3 && rbt12 > 720_000 && rbt12 <= 1_800_000) ||
                  (i === 4 && rbt12 > 1_800_000 && rbt12 <= 3_600_000) ||
                  (i === 5 && rbt12 > 3_600_000)
                )
                return (
                  <tr key={i} style={{ background: faixaAtual ? '#f0fdf4' : 'transparent', borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '8px 10px', fontWeight: faixaAtual ? 700 : 400 }}>
                      {f.faixa}
                      {faixaAtual && <span style={{ marginLeft: 6, fontSize: 10, background: '#dcfce7', color: '#15803d', padding: '1px 6px', borderRadius: 999, fontWeight: 600 }}>← você</span>}
                    </td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }}>{f.aliq.toFixed(2).replace('.', ',')}%</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right', color: 'var(--gray-mid)' }}>{f.ded ? fmtR(f.ded) : '—'}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }}>{f.issComp.toFixed(2).replace('.', ',')}%</td>
                    {rbt12 && (
                      <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, color: faixaAtual ? 'var(--teal)' : 'var(--dark)' }}>
                        {ef != null ? `${ef.toFixed(2).replace('.', ',')}%` : '—'}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <h3 style={{ fontFamily: 'Archivo, sans-serif', fontSize: 14, fontWeight: 800, marginBottom: 4, color: 'var(--dark)' }}>
          ISS Municipal — Vitória/ES (Advocacia)
        </h3>
        <p style={{ fontSize: 12, color: 'var(--gray-mid)', marginBottom: 12 }}>
          Para optantes do Lucro Presumido ou Lucro Real, o ISS é pago diretamente ao município.
          LC 116/2003 define alíquota mínima 2% e máxima 5%. Vitória/ES aplica:
        </p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#f3f4f6' }}>
              <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', fontSize: 10 }}>Situação</th>
              <th style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', fontSize: 10 }}>Alíquota</th>
              <th style={{ padding: '7px 10px', textAlign: 'left', fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', fontSize: 10 }}>Observação</th>
            </tr>
          </thead>
          <tbody>
            {[
              { sit: 'Simples Nacional', aliq: 'incluso no DAS', obs: 'ISS faz parte da guia única (2% a 5% conforme faixa acima)' },
              { sit: 'LP / LR — serviços advocatícios', aliq: '2,00%', obs: 'Alíquota mínima LC 116/2003, aplicada em Vitória — Dec. Municipal' },
              { sit: 'LP / LR — sociedade de profissionais', aliq: '2,00%', obs: 'Regime especial: recolhimento por profissional habilitado (não por receita)' },
            ].map((r, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '7px 10px', fontWeight: 600 }}>{r.sit}</td>
                <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 700, color: 'var(--teal)' }}>{r.aliq}</td>
                <td style={{ padding: '7px 10px', color: 'var(--gray-mid)' }}>{r.obs}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={{ fontSize: 11, color: '#9ca3af', marginTop: 12 }}>
          ⚠ O contador informou 2,88% — isso é a <strong>alíquota efetiva do Simples</strong> (pTotTribSN), não o ISS isolado.
          Confirme com ele a faixa de RBT12 para validar o cálculo acima.
        </p>
      </div>
    </div>
  )
}

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  const [aberta, setAberta] = useState(true)
  return (
    <div className={styles.tableCard} style={{ marginBottom: 14, padding: 0 }}>
      <button onClick={() => setAberta((v) => !v)}
        style={{ width: '100%', textAlign: 'left', background: 'var(--light)', border: 'none',
          padding: '12px 16px', fontWeight: 700, fontSize: 13, color: 'var(--dark)',
          cursor: 'pointer', fontFamily: 'Archivo, sans-serif' }}>
        {aberta ? '▾' : '▸'} {titulo}
      </button>
      {aberta && <div style={{ padding: '16px' }}>{children}</div>}
    </div>
  )
}

function Campo({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label className={cs.formLabel}>{label}</label>
      {children}
      {hint && <p className={cs.fieldHint}>{hint}</p>}
    </div>
  )
}

const GRID2: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }

export default function ConfigFiscalPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['config-fiscal'], queryFn: configFiscalApi.obter })
  const [form, setForm] = useState<ConfigFiscal | null>(null)
  const [salvou, setSalvou] = useState(false)
  const [showSimples, setShowSimples] = useState(false)
  const [enviandoRel, setEnviandoRel] = useState(false)
  const [relMsg, setRelMsg] = useState<string | null>(null)
  const [showHist, setShowHist] = useState(false)
  const [linkPub, setLinkPub] = useState<string | null>(null)
  const [copiado, setCopiado] = useState(false)
  const { data: hist } = useQuery({
    queryKey: ['relatorio-historico', showHist],
    queryFn: fiscalApi.historicoRelatorios,
    enabled: showHist,
  })

  useEffect(() => { if (data) setForm(data) }, [data])

  const mut = useMutation({
    mutationFn: (c: ConfigFiscal) => configFiscalApi.salvar(c),
    onSuccess: (c) => {
      qc.setQueryData(['config-fiscal'], c); setForm(c)
      setSalvou(true); setTimeout(() => setSalvou(false), 2500)
    },
  })

  if (isLoading || !form) return <div className={styles.empty}>Carregando…</div>

  function set<K extends keyof ConfigFiscal>(k: K, v: ConfigFiscal[K]) {
    setForm((f) => f ? { ...f, [k]: v } : f)
  }
  const f = form
  const inp = cs.input

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Configurações <strong>Fiscais</strong></h1>
        <button className={styles.btnPrimary} disabled={mut.isPending}
          onClick={() => mut.mutate(f)}>
          {mut.isPending ? 'Salvando…' : salvou ? '✓ Salvo' : 'Salvar alterações'}
        </button>
      </div>

      {/* A. Emitente */}
      <Secao titulo="🏢 Dados do Emitente">
        <div style={GRID2}>
          <Campo label="Razão Social"><input className={inp} value={f.razao_social} onChange={(e) => set('razao_social', e.target.value)} /></Campo>
          <Campo label="CNPJ"><input className={inp} value={f.cnpj} onChange={(e) => set('cnpj', e.target.value.replace(/\D/g, ''))} /></Campo>
          <Campo label="Inscrição Municipal"><input className={inp} value={f.inscricao_municipal ?? ''} onChange={(e) => set('inscricao_municipal', e.target.value)} /></Campo>
          <Campo label="CNAE"><input className={inp} value={f.cnae ?? ''} onChange={(e) => set('cnae', e.target.value)} /></Campo>
          <Campo label="Município"><input className={inp} value={f.municipio_nome} onChange={(e) => set('municipio_nome', e.target.value)} /></Campo>
          <Campo label="Cód. IBGE / UF">
            <div style={{ display: 'flex', gap: 8 }}>
              <input className={inp} value={f.municipio_ibge} onChange={(e) => set('municipio_ibge', e.target.value)} />
              <input className={inp} style={{ width: 60 }} value={f.uf} onChange={(e) => set('uf', e.target.value)} />
            </div>
          </Campo>
          <Campo label="E-mail fiscal"><input className={inp} value={f.email_fiscal ?? ''} onChange={(e) => set('email_fiscal', e.target.value)} /></Campo>
          <Campo label="Telefone fiscal"><input className={inp} value={f.telefone_fiscal ?? ''} onChange={(e) => set('telefone_fiscal', e.target.value)} /></Campo>
        </div>
        <Campo label="Endereço completo"><input className={inp} value={f.endereco ?? ''} onChange={(e) => set('endereco', e.target.value)} /></Campo>
        <Campo label="Regime tributário">
          <select className={inp} value={f.regime_tributario} onChange={(e) => set('regime_tributario', e.target.value)}>
            <option value="simples">Simples Nacional</option>
            <option value="presumido">Lucro Presumido</option>
            <option value="real">Lucro Real</option>
          </select>
        </Campo>
      </Secao>

      {/* B. Bases de tributação */}
      <Secao titulo="⚖️ Bases de Tributação">
        <div style={GRID2}>
          <Campo label="Alíquota ISS (%)"><input className={inp} type="number" step="0.01" value={f.aliquota_iss} onChange={(e) => set('aliquota_iss', parseFloat(e.target.value) || 0)} /></Campo>
          <Campo label="Regime especial">
            <select className={inp} value={f.regime_especial} onChange={(e) => set('regime_especial', e.target.value)}>
              <option value="0">Nenhum</option>
              <option value="6">Sociedade de Profissionais</option>
            </select>
          </Campo>
          <Campo label="Anexo do Simples">
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input className={inp} value={f.anexo_simples} onChange={(e) => set('anexo_simples', e.target.value)} style={{ flex: 1 }} />
              <button type="button" className={cs.templateBtn} onClick={() => setShowSimples(true)}>
                Ver tabela
              </button>
            </div>
          </Campo>
          <Campo label="RBT12 — receita bruta 12 meses (R$)"
            hint={f.rbt12_acumulado_12m != null
              ? `Checagem pelas NFs do sistema (12 meses anteriores, regra legal): R$ ${f.rbt12_acumulado_12m.toLocaleString('pt-BR', {minimumFractionDigits:2})}${f.aliquota_pelo_acumulado ? ` → alíquota ${f.aliquota_pelo_acumulado}%` : ''}. Pode estar abaixo do real se há notas anteriores à integração — use o RBT12 oficial da contabilidade.`
              : 'Informe o RBT12 da contabilidade para o sistema sugerir a alíquota'}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input className={inp} type="number" step="0.01" value={f.rbt12 ?? ''} onChange={(e) => set('rbt12', e.target.value ? parseFloat(e.target.value) : undefined)} />
              {f.rbt12_acumulado_12m != null && (
                <button type="button" className={cs.templateBtn}
                  onClick={() => set('rbt12', f.rbt12_acumulado_12m!)}>usar acumulado</button>
              )}
            </div>
          </Campo>
          <Campo label="Alíquota efetiva do Simples (%) — pTotTribSN" hint="Confirme com o contador. O sistema sugere pela RBT12.">
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input className={inp} type="number" step="0.01" value={f.aliquota_efetiva_simples} onChange={(e) => set('aliquota_efetiva_simples', parseFloat(e.target.value) || 0)} />
              {f.aliquota_simples_sugerida != null && (
                <button type="button" className={cs.templateBtn}
                  onClick={() => set('aliquota_efetiva_simples', f.aliquota_simples_sugerida!)}>
                  usar {f.aliquota_simples_sugerida}%
                </button>
              )}
            </div>
          </Campo>
          <Campo label="ISS retido por padrão?">
            <label className={cs.checkboxLabel}>
              <input type="checkbox" checked={f.iss_retido_padrao} onChange={(e) => set('iss_retido_padrao', e.target.checked)} /> Sim
            </label>
          </Campo>
        </div>
        <p className={cs.fieldHint} style={{ marginTop: 8, fontWeight: 600 }}>Retenções padrão (tomador PJ) — %</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
          {([['ret_ir_pct','IR'],['ret_inss_pct','INSS'],['ret_csll_pct','CSLL'],['ret_pis_pct','PIS'],['ret_cofins_pct','COFINS']] as const).map(([k,l]) => (
            <Campo key={k} label={l}><input className={inp} type="number" step="0.01" value={f[k] as number} onChange={(e) => set(k, parseFloat(e.target.value) || 0 as any)} /></Campo>
          ))}
        </div>
      </Secao>

      {/* D. IBS/CBS */}
      <Secao titulo="🆕 Reforma Tributária (IBS / CBS)">
        <p className={cs.fieldHint} style={{ marginBottom: 10 }}>Entra em teste a partir de ago/2026. Deixe configurado para quando ativar.</p>
        <div style={GRID2}>
          <Campo label="IBS (%)"><input className={inp} type="number" step="0.01" value={f.ibs_pct} onChange={(e) => set('ibs_pct', parseFloat(e.target.value) || 0)} /></Campo>
          <Campo label="CBS (%)"><input className={inp} type="number" step="0.01" value={f.cbs_pct} onChange={(e) => set('cbs_pct', parseFloat(e.target.value) || 0)} /></Campo>
        </div>
        <label className={cs.checkboxLabel}>
          <input type="checkbox" checked={f.piloto_ibscbs} onChange={(e) => set('piloto_ibscbs', e.target.checked)} /> Operação no piloto IBS/CBS
        </label>

        {/* Link público para o contador validar a transição */}
        <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #eee' }}>
          <label className={cs.formLabel}>Link público para o contador (somente leitura)</label>
          <p className={cs.fieldHint} style={{ marginTop: 0 }}>
            Compartilha apenas a projeção da transição IBS/CBS e a receita por competência. Sem login, sem dados de clientes/processos. Pode revogar a qualquer momento.
          </p>
          {(() => {
            const path = linkPub ?? (f.link_publico_token ? `/p/reforma/${f.link_publico_token}` : null)
            const full = path ? `${window.location.origin}${path}` : null
            return (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                {full && (
                  <input className={inp} readOnly value={full} style={{ flex: 1, minWidth: 280 }}
                    onFocus={(e) => e.currentTarget.select()} />
                )}
                {full && (
                  <button type="button" className={cs.btnSecondary}
                    onClick={() => { navigator.clipboard.writeText(full); setCopiado(true); setTimeout(() => setCopiado(false), 1500) }}>
                    {copiado ? 'Copiado!' : 'Copiar'}
                  </button>
                )}
                <button type="button" className={cs.btnSecondary}
                  onClick={async () => { const r = await configFiscalApi.gerarLinkPublico(); setLinkPub(r.url) }}>
                  {full ? 'Gerar novo' : 'Gerar link'}
                </button>
                {full && (
                  <button type="button" className={cs.btnSecondary}
                    onClick={async () => { await configFiscalApi.revogarLinkPublico(); setLinkPub(null); set('link_publico_token', null as any) }}>
                    Revogar
                  </button>
                )}
              </div>
            )
          })()}
        </div>
      </Secao>

      {/* E. Contabilidade */}
      <Secao titulo="📧 Contabilidade & Relatórios">
        <Campo label="E-mails do contador (separados por vírgula)">
          <input className={inp} value={f.emails_contador.join(', ')}
            onChange={(e) => set('emails_contador', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))} />
        </Campo>
        <div style={GRID2}>
          <Campo label="Cópia para (master)"><input className={inp} value={f.email_master ?? ''} onChange={(e) => set('email_master', e.target.value)} /></Campo>
          <Campo label="Dia de envio do relatório"><input className={inp} type="number" min={1} max={28} value={f.dia_envio_relatorio} onChange={(e) => set('dia_envio_relatorio', parseInt(e.target.value) || 1)} /></Campo>
        </div>
        <label className={cs.checkboxLabel}>
          <input type="checkbox" checked={f.enviar_relatorio_auto} onChange={(e) => set('enviar_relatorio_auto', e.target.checked)} /> Enviar relatório mensal automaticamente
        </label>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
          <button type="button" className={cs.btnSecondary} disabled={enviandoRel}
            onClick={async () => {
              setEnviandoRel(true); setRelMsg(null)
              try {
                const r = await fiscalApi.enviarRelatorio()
                setRelMsg(`✓ Enviado (${r.nf_qtd} NF, ${r.anexos} anexo(s)) para ${r.destinatarios?.join(', ')}`)
              } catch (e: any) {
                setRelMsg('⚠️ ' + (e?.response?.data?.detail || 'Falha ao enviar'))
              } finally { setEnviandoRel(false) }
            }}>
            {enviandoRel ? 'Enviando…' : '📧 Enviar relatório agora (mês anterior)'}
          </button>
          {relMsg && <span className={cs.fieldHint}>{relMsg}</span>}
        </div>
        <div style={{ marginTop: 10 }}>
          <button type="button" className={cs.colapsarBtn} onClick={() => setShowHist(true)}>
            📜 Ver relatórios já enviados
          </button>
        </div>
      </Secao>

      {showSimples && (
        <PopupSimples onClose={() => setShowSimples(false)} rbt12={f.rbt12 ?? f.rbt12_acumulado_12m ?? undefined} />
      )}

      {showHist && (
        <div className={cs.overlay} onClick={(e) => e.target === e.currentTarget && setShowHist(false)}>
          <div className={cs.modal} style={{ maxWidth: 720 }}>
            <button className={cs.closeBtn} onClick={() => setShowHist(false)}>✕</button>
            <div className={cs.modalTitle}>📜 Relatórios enviados ao contador</div>
            {hist?.proximo_envio ? (
              <div className={cs.prefillBanner}>
                📅 Próximo envio automático: <b>{hist.proximo_envio.data}</b> (ref. {hist.proximo_envio.competencia_ref})
                {hist.proximo_envio.destinatarios?.length ? ` → ${hist.proximo_envio.destinatarios.join(', ')}` : ''}
              </div>
            ) : (
              <div className={cs.erroBox} style={{ marginBottom: 12 }}>Envio automático desligado ou sem dia configurado.</div>
            )}
            {!hist?.historico?.length ? (
              <p className={cs.fieldHint}>Nenhum relatório enviado ainda.</p>
            ) : (
              <table className={styles.table}>
                <thead><tr><th>Competência</th><th>Enviado em</th><th>Destinatários</th><th>NFs</th><th>Links</th></tr></thead>
                <tbody>
                  {hist.historico.map((r: any) => (
                    <tr key={r.id}>
                      <td>{r.competencia}</td>
                      <td>{r.enviado_em ? new Date(r.enviado_em).toLocaleString('pt-BR') : '—'}</td>
                      <td style={{ fontSize: 12 }}>{(r.destinatarios || []).join(', ')}{r.cc ? ` (cc ${r.cc})` : ''}</td>
                      <td>{r.nf_qtd} · {r.anexos} anexo(s)</td>
                      <td style={{ display: 'flex', gap: 8 }}>
                        {r.gmail_link && <a href={r.gmail_link} target="_blank" rel="noreferrer" style={{ color: '#b45309' }}>✉️ E-mail</a>}
                        {r.drive_pasta_link && <a href={r.drive_pasta_link} target="_blank" rel="noreferrer" style={{ color: 'var(--teal)' }}>📁 Pasta</a>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className={cs.modalFooter}>
              <button className={cs.btnSecondary} onClick={() => setShowHist(false)}>Fechar</button>
            </div>
          </div>
        </div>
      )}

      {/* G. Templates & Códigos */}
      <Secao titulo="📝 Templates de Descrição & Códigos de Serviço">
        <div className={cs.formLabel}>Templates de descrição (chips no formulário de emissão)</div>
        {(f.templates_descricao || []).map((t, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
            <input className={inp} style={{ flex: '0 0 160px' }} placeholder="Rótulo" value={t.label}
              onChange={(e) => { const a = [...f.templates_descricao]; a[i] = { ...a[i], label: e.target.value }; set('templates_descricao', a) }} />
            <input className={inp} placeholder="Texto (use {cliente})" value={t.texto}
              onChange={(e) => { const a = [...f.templates_descricao]; a[i] = { ...a[i], texto: e.target.value }; set('templates_descricao', a) }} />
            <button className={cs.btnSecondary} onClick={() => set('templates_descricao', f.templates_descricao.filter((_, j) => j !== i))}>×</button>
          </div>
        ))}
        <button className={cs.templateBtn} onClick={() => set('templates_descricao', [...(f.templates_descricao || []), { tipo: 'custom' + Date.now(), label: '', texto: '' }])}>+ Adicionar template</button>

        <div className={cs.formLabel} style={{ marginTop: 16 }}>Códigos de tributação favoritos (dropdown da emissão)</div>
        {(f.codigos_favoritos || []).map((c, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
            <input className={inp} style={{ flex: '0 0 120px' }} placeholder="Código" value={c.codigo}
              onChange={(e) => { const a = [...f.codigos_favoritos]; a[i] = { ...a[i], codigo: e.target.value }; set('codigos_favoritos', a) }} />
            <input className={inp} style={{ flex: '0 0 180px' }} placeholder="Rótulo" value={c.label}
              onChange={(e) => { const a = [...f.codigos_favoritos]; a[i] = { ...a[i], label: e.target.value }; set('codigos_favoritos', a) }} />
            <input className={inp} placeholder="Descrição" value={c.descricao ?? ''}
              onChange={(e) => { const a = [...f.codigos_favoritos]; a[i] = { ...a[i], descricao: e.target.value }; set('codigos_favoritos', a) }} />
            <button className={cs.btnSecondary} onClick={() => set('codigos_favoritos', f.codigos_favoritos.filter((_, j) => j !== i))}>×</button>
          </div>
        ))}
        <button className={cs.templateBtn} onClick={() => set('codigos_favoritos', [...(f.codigos_favoritos || []), { codigo: '', label: '', descricao: '' }])}>+ Adicionar código</button>
        <p className={cs.fieldHint} style={{ marginTop: 8 }}>Se vazios, o sistema usa os padrões (advocacia 171401 etc.).</p>
      </Secao>

      {/* F. Numeração + DANFSe */}
      <Secao titulo="🔢 Numeração & DANFSe">
        <div style={GRID2}>
          <Campo label="Série padrão da DPS"><input className={inp} value={f.serie_padrao} onChange={(e) => set('serie_padrao', e.target.value)} /></Campo>
          <Campo label="Prefixo do nº na DANFSe" hint="Ex.: PJ150 → a nota 17 aparece como PJ150017 (cosmético, não altera o nº oficial)">
            <input className={inp} value={f.danfse_prefixo_numero ?? ''} onChange={(e) => set('danfse_prefixo_numero', e.target.value)} placeholder="PJ150" />
          </Campo>
          <Campo label="Carga tributária média % (Lei 12.741 / IBPT)" hint="Advocacia ≈ 16,33%. Aparece na DANFSe e na Visão Fiscal.">
            <input className={inp} type="number" step="0.01" value={f.carga_media_pct ?? 16.33} onChange={(e) => set('carga_media_pct', parseFloat(e.target.value) || 0)} />
          </Campo>
        </div>
        <Campo label="Texto de rodapé da DANFSe"><input className={inp} value={f.rodape_danfse ?? ''} onChange={(e) => set('rodape_danfse', e.target.value)} /></Campo>
      </Secao>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
        <button className={styles.btnPrimary} disabled={mut.isPending} onClick={() => mut.mutate(f)}>
          {mut.isPending ? 'Salvando…' : salvou ? '✓ Salvo' : 'Salvar alterações'}
        </button>
      </div>
    </div>
  )
}
