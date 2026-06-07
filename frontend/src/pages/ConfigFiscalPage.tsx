import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { configFiscalApi } from '../api/configFiscal'
import type { ConfigFiscal } from '../api/configFiscal'
import styles from './Page.module.css'
import cs from './FiscalPage.module.css'

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
          <Campo label="Anexo do Simples"><input className={inp} value={f.anexo_simples} onChange={(e) => set('anexo_simples', e.target.value)} /></Campo>
          <Campo label="RBT12 — receita bruta 12 meses (R$)" hint={f.aliquota_simples_sugerida ? `Sugerido: ${f.aliquota_simples_sugerida}% — ${f.faixa_simples}` : 'Informe para o sistema sugerir a alíquota'}>
            <input className={inp} type="number" step="0.01" value={f.rbt12 ?? ''} onChange={(e) => set('rbt12', e.target.value ? parseFloat(e.target.value) : undefined)} />
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
      </Secao>

      {/* F. Numeração + DANFSe */}
      <Secao titulo="🔢 Numeração & DANFSe">
        <div style={GRID2}>
          <Campo label="Série padrão da DPS"><input className={inp} value={f.serie_padrao} onChange={(e) => set('serie_padrao', e.target.value)} /></Campo>
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
