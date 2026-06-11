import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { backofficeApi, type Despesa, type MesAnual } from '../api/backoffice'
import styles from './Page.module.css'

// ─── Utilitários ─────────────────────────────────────────────────────────────

function fmtBRL(v: number) {
  return (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function fmtPct(v: number) {
  return `${(v ?? 0).toFixed(2).replace('.', ',')}%`
}
function mesAtual() { return new Date().toISOString().slice(0, 7) }
function mesLabel(mes: string) {
  const [ano, mm] = mes.split('-')
  const nomes = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
  return `${nomes[Number(mm) - 1]}/${ano}`
}

const STATUS_COR: Record<string, string> = {
  validado: '#15803d', revalidar: '#b45309', pendente: '#6b7280', novo: '#1d4ed8',
}
const TIPO_CLIENTE_LABEL: Record<string, string> = {
  pj_regular: 'PJ (regime regular)', pj_simples: 'PJ (Simples)', pf: 'Pessoa física',
}

// ─── Componentes de KPI ───────────────────────────────────────────────────────

function Kpi({ label, value, sub, cor }: { label: string; value: string; sub?: string; cor?: string }) {
  return (
    <div className={styles.tableCard} style={{ padding: '14px 18px', flex: 1, minWidth: 150 }}>
      <div style={{ fontSize: 11, color: 'var(--gray-mid)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '.05em' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: cor || 'var(--dark)', marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--gray-mid)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

// ─── Tab: Comparativo ────────────────────────────────────────────────────────

function TabComparativo({ mes }: { mes: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['backoffice-decisao', mes],
    queryFn: () => backofficeApi.decisao(mes),
  })

  if (isLoading || !data) return <div className={styles.empty}>Calculando…</div>

  const vencedor = data.regimes.find(r => r.slug === data.vencedor)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {data.nfs_sincronizadas > 0 && (
        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '8px 14px', fontSize: 12, color: '#15803d' }}>
          ✓ {data.nfs_sincronizadas} nota(s) fiscal(is) importada(s) automaticamente para {mesLabel(mes)}.
        </div>
      )}

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <Kpi label="Receita do mês" value={fmtBRL(data.totais.receita_total)} sub={`${mesLabel(mes)}`} />
        <Kpi label="Folha total" value={fmtBRL(data.totais.folha_total)} sub="com encargos" />
        <Kpi label="Crédito IBS/CBS" value={fmtBRL(data.totais.credito_total)} sub={`base elegível ${fmtBRL(data.totais.despesas_elegiveis)}`} cor="var(--teal)" />
        <Kpi
          label="Regime sugerido"
          value={vencedor?.nome ?? '—'}
          sub={vencedor ? `carga ${fmtPct(vencedor.carga_efetiva_pct)}` : undefined}
          cor="var(--teal)"
        />
      </div>

      {/* Leitura executiva */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={{ background: 'rgba(0,176,144,.07)', border: '1px solid rgba(0,176,144,.2)', borderRadius: 10, padding: '14px 18px' }}>
          <div style={{ fontSize: 11, color: 'var(--teal)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em' }}>Melhor para o caixa</div>
          <div style={{ fontSize: 18, fontWeight: 800, marginTop: 6, color: 'var(--dark)' }}>{vencedor?.nome ?? '—'}</div>
          <div style={{ fontSize: 12, color: 'var(--gray-mid)', marginTop: 4 }}>
            Total estimado: {fmtBRL(vencedor?.breakdown.total_com_folha ?? 0)}
          </div>
        </div>
        <div style={{ background: 'rgba(59,130,246,.06)', border: '1px solid rgba(59,130,246,.2)', borderRadius: 10, padding: '14px 18px' }}>
          <div style={{ fontSize: 11, color: '#1d4ed8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em' }}>Crédito ao cliente PJ</div>
          <div style={{ fontSize: 18, fontWeight: 800, marginTop: 6, color: 'var(--dark)' }}>
            {fmtBRL(vencedor?.credito_cliente ?? 0)}
          </div>
          <div style={{ fontSize: 12, color: 'var(--gray-mid)', marginTop: 4 }}>estimado no regime vencedor</div>
        </div>
      </div>

      {/* Tabela comparativa */}
      <div className={styles.tableCard}>
        <div style={{ padding: '14px 18px 8px', fontWeight: 700, fontSize: 13 }}>Comparativo entre regimes</div>
        <div style={{ overflowX: 'auto' }}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Regime</th>
                <th style={{ textAlign: 'right' }}>Tributos s/ operação</th>
                <th style={{ textAlign: 'right' }}>Folha/encargos</th>
                <th style={{ textAlign: 'right' }}>Total estimado</th>
                <th style={{ textAlign: 'right' }}>Carga efetiva</th>
                <th style={{ textAlign: 'right' }}>Crédito ao cliente</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.regimes.map(r => (
                <tr key={r.slug} style={r.slug === data.vencedor ? { background: '#f0fdf4' } : undefined}>
                  <td style={{ fontWeight: r.slug === data.vencedor ? 700 : 400 }}>{r.nome}</td>
                  <td style={{ textAlign: 'right' }}>{fmtBRL(r.breakdown.total_tributos)}</td>
                  <td style={{ textAlign: 'right', color: 'var(--gray-mid)' }}>
                    {fmtBRL(r.breakdown.inss_patronal + r.breakdown.fgts)}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtBRL(r.breakdown.total_com_folha)}</td>
                  <td style={{ textAlign: 'right' }}>{fmtPct(r.carga_efetiva_pct)}</td>
                  <td style={{ textAlign: 'right', color: '#1d4ed8' }}>{fmtBRL(r.credito_cliente)}</td>
                  <td>
                    {r.slug === data.vencedor
                      ? <span style={{ background: '#dcfce7', color: '#15803d', fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 999 }}>vencedor</span>
                      : null}
                    {r.obs && <span style={{ fontSize: 10, color: 'var(--gray-mid)', marginLeft: 4 }}>{r.obs}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Breakdown detalhado do vencedor */}
        {vencedor && (
          <details style={{ padding: '0 18px 14px' }}>
            <summary style={{ cursor: 'pointer', fontSize: 12, fontWeight: 600, color: 'var(--gray-mid)', marginTop: 8 }}>
              Ver breakdown detalhado — {vencedor.nome}
            </summary>
            <table className={styles.table} style={{ marginTop: 8 }}>
              <tbody>
                {[
                  ['DAS (Simples)', vencedor.breakdown.das],
                  ['PIS', vencedor.breakdown.pis],
                  ['COFINS', vencedor.breakdown.cofins],
                  ['IRPJ', vencedor.breakdown.irpj],
                  ['CSLL', vencedor.breakdown.csll],
                  ['ISS', vencedor.breakdown.iss],
                  ['IBS bruto', vencedor.breakdown.ibs_bruto],
                  ['CBS bruto', vencedor.breakdown.cbs_bruto],
                  ['(-) Crédito IBS', -vencedor.breakdown.credito_ibs],
                  ['(-) Crédito CBS', -vencedor.breakdown.credito_cbs],
                  ['INSS patronal', vencedor.breakdown.inss_patronal],
                  ['FGTS', vencedor.breakdown.fgts],
                ].filter(([, v]) => (v as number) !== 0).map(([label, val]) => (
                  <tr key={label as string}>
                    <td style={{ color: 'var(--gray-mid)', fontSize: 12 }}>{label as string}</td>
                    <td style={{ textAlign: 'right', fontSize: 12, color: (val as number) < 0 ? '#15803d' : undefined }}>
                      {fmtBRL(Math.abs(val as number))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}

        <p style={{ padding: '0 18px 12px', fontSize: 11, color: 'var(--gray-mid)', margin: 0 }}>
          Estimativas para planejamento — confirme com o contador antes de decidir a migração de regime.
          {data.premissas.override_ativo && ' ⚠ Premissas customizadas para este mês.'}
        </p>
      </div>
    </div>
  )
}

// ─── Tab: Lançamentos ─────────────────────────────────────────────────────────

function TabLancamentos({ mes }: { mes: string }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['backoffice-lancamentos', mes],
    queryFn: () => backofficeApi.lancamentos(mes),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] })
    qc.invalidateQueries({ queryKey: ['backoffice-decisao', mes] })
  }

  const [folhaEdit, setFolhaEdit] = useState(false)
  const [folhaForm, setFolhaForm] = useState<Record<string, string>>({})
  const [showDespesaForm, setShowDespesaForm] = useState(false)
  const [showReceitaForm, setShowReceitaForm] = useState(false)

  const saveFolha = useMutation({
    mutationFn: () => backofficeApi.upsertFolha(mes, Object.fromEntries(
      Object.entries(folhaForm).map(([k, v]) => [k, Number(v) || 0])
    )),
    onSuccess: () => { setFolhaEdit(false); invalidate() },
  })

  const addDespesa = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const fd = new FormData(form)
      return backofficeApi.addDespesa(mes, {
        categoria: fd.get('categoria'),
        fornecedor: fd.get('fornecedor'),
        descricao: fd.get('descricao') || null,
        valor: Number(fd.get('valor')),
        tem_nota: fd.get('tem_nota') === 'on',
        elegivel: fd.get('elegivel') === 'on',
      })
    },
    onSuccess: (_, form) => { form.reset(); setShowDespesaForm(false); invalidate() },
  })

  const deleteDespesa = useMutation({
    mutationFn: (id: string) => backofficeApi.deleteDespesa(id),
    onSuccess: invalidate,
  })

  const addReceita = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const fd = new FormData(form)
      return backofficeApi.addReceita(mes, {
        cliente_nome: fd.get('cliente_nome'),
        tipo_cliente: fd.get('tipo_cliente'),
        valor: Number(fd.get('valor')),
        retencoes: Number(fd.get('retencoes')) || 0,
        credito_interesse: fd.get('credito_interesse') === 'on',
        modo_tributacao: fd.get('modo_tributacao'),
      })
    },
    onSuccess: (_, form) => { form.reset(); setShowReceitaForm(false); invalidate() },
  })

  const deleteReceita = useMutation({
    mutationFn: (id: string) => backofficeApi.deleteReceita(id),
    onSuccess: invalidate,
  })

  const patchElegivel = useMutation({
    mutationFn: ({ id, elegivel }: { id: string; elegivel: boolean }) =>
      backofficeApi.patchDespesa(id, { elegivel }),
    onSuccess: invalidate,
  })

  if (isLoading || !data) return <div className={styles.empty}>Carregando…</div>

  const folha = data.folha
  const folhaTotal = Object.values(folha).reduce((a, b) => a + b, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Receitas */}
      <div className={styles.tableCard}>
        <div style={{ padding: '14px 18px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontWeight: 700, fontSize: 13 }}>Receitas</span>
            <span style={{ fontSize: 11, color: 'var(--gray-mid)', marginLeft: 8 }}>
              NFs importadas automaticamente · manuais aqui
            </span>
          </div>
          <button className={styles.btnSmall} onClick={() => setShowReceitaForm(v => !v)}>
            {showReceitaForm ? 'Cancelar' : '+ Manual'}
          </button>
        </div>

        {showReceitaForm && (
          <form
            style={{ padding: '0 18px 14px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}
            onSubmit={e => { e.preventDefault(); addReceita.mutate(e.currentTarget) }}
          >
            <label className={styles.fieldGroup}>
              <span>Cliente</span>
              <input name="cliente_nome" required placeholder="Nome do cliente" />
            </label>
            <label className={styles.fieldGroup}>
              <span>Tipo</span>
              <select name="tipo_cliente">
                <option value="pj_regular">PJ regime regular</option>
                <option value="pj_simples">PJ Simples</option>
                <option value="pf">Pessoa física</option>
              </select>
            </label>
            <label className={styles.fieldGroup}>
              <span>Valor (R$)</span>
              <input name="valor" type="number" step="0.01" required />
            </label>
            <label className={styles.fieldGroup}>
              <span>Retenções (R$)</span>
              <input name="retencoes" type="number" step="0.01" defaultValue="0" />
            </label>
            <label className={styles.fieldGroup}>
              <span>Tributação</span>
              <select name="modo_tributacao">
                <option value="embutido">Embutido no preço</option>
                <option value="por_fora">Por fora (destaque)</option>
              </select>
            </label>
            <label className={styles.fieldGroup} style={{ justifyContent: 'center', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" name="credito_interesse" defaultChecked />
              <span>Cliente valoriza crédito IBS/CBS</span>
            </label>
            <div style={{ gridColumn: '1/-1' }}>
              <button type="submit" className={styles.btnPrimary}>Adicionar receita manual</button>
            </div>
          </form>
        )}

        <table className={styles.table}>
          <thead>
            <tr>
              <th>Cliente</th><th>Tipo</th>
              <th style={{ textAlign: 'right' }}>Valor</th>
              <th style={{ textAlign: 'right' }}>Retenções</th>
              <th>Crédito</th><th>Origem</th><th></th>
            </tr>
          </thead>
          <tbody>
            {data.receitas.length === 0 && (
              <tr><td colSpan={7} style={{ color: 'var(--gray-mid)', textAlign: 'center', padding: '12px 0' }}>
                Nenhuma receita — NFs serão importadas na próxima consulta à tela Comparativo.
              </td></tr>
            )}
            {data.receitas.map(r => (
              <tr key={r.id}>
                <td>{r.cliente_nome}</td>
                <td style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{TIPO_CLIENTE_LABEL[r.tipo_cliente] ?? r.tipo_cliente}</td>
                <td style={{ textAlign: 'right' }}>{fmtBRL(r.valor)}</td>
                <td style={{ textAlign: 'right', color: r.retencoes > 0 ? '#15803d' : 'var(--gray-mid)' }}>{fmtBRL(r.retencoes)}</td>
                <td>
                  {r.credito_interesse
                    ? <span style={{ fontSize: 10, background: '#dbeafe', color: '#1d4ed8', padding: '2px 6px', borderRadius: 999, fontWeight: 600 }}>valoriza</span>
                    : <span style={{ fontSize: 10, color: 'var(--gray-mid)' }}>—</span>}
                </td>
                <td style={{ fontSize: 11 }}>
                  {r.is_manual
                    ? <span style={{ color: '#b45309' }}>manual</span>
                    : <span style={{ color: 'var(--teal)' }}>NF</span>}
                </td>
                <td>
                  {r.is_manual && (
                    <button style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 13 }}
                      onClick={() => deleteReceita.mutate(r.id)}>×</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Folha */}
      <div className={styles.tableCard}>
        <div style={{ padding: '14px 18px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontWeight: 700, fontSize: 13 }}>Folha de pagamento</span>
            <span style={{ fontSize: 11, color: 'var(--gray-mid)', marginLeft: 8 }}>Total: {fmtBRL(folhaTotal)}</span>
          </div>
          <button className={styles.btnSmall} onClick={() => {
            setFolhaEdit(v => !v)
            if (!folhaEdit) setFolhaForm(Object.fromEntries(Object.entries(folha).map(([k, v]) => [k, String(v)])))
          }}>
            {folhaEdit ? 'Cancelar' : 'Editar'}
          </button>
        </div>

        {folhaEdit ? (
          <div style={{ padding: '0 18px 14px', display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
            {(['salarios','prolabore','inss_patronal','rat','fgts','beneficios','outros'] as const).map(k => (
              <label key={k} className={styles.fieldGroup}>
                <span style={{ textTransform: 'capitalize' }}>{k.replace('_', ' ')}</span>
                <input type="number" step="0.01" value={folhaForm[k] ?? '0'}
                  onChange={e => setFolhaForm(f => ({ ...f, [k]: e.target.value }))} />
              </label>
            ))}
            <div style={{ gridColumn: '1/-1' }}>
              <button className={styles.btnPrimary} onClick={() => saveFolha.mutate()}>Salvar folha</button>
            </div>
          </div>
        ) : (
          <div style={{ padding: '0 18px 14px', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8 }}>
            {[
              ['Salários', folha.salarios], ['Pró-labore', folha.prolabore],
              ['INSS patronal', folha.inss_patronal], ['RAT', folha.rat],
              ['FGTS', folha.fgts], ['Benefícios', folha.beneficios],
              ['Outros', folha.outros],
            ].map(([label, val]) => (
              <div key={label as string}>
                <div style={{ fontSize: 10, color: 'var(--gray-mid)', textTransform: 'uppercase', fontWeight: 700 }}>{label as string}</div>
                <div style={{ fontSize: 14, fontWeight: 700, marginTop: 2 }}>{fmtBRL(val as number)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Despesas */}
      <div className={styles.tableCard}>
        <div style={{ padding: '14px 18px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>Despesas</span>
          <button className={styles.btnSmall} onClick={() => setShowDespesaForm(v => !v)}>
            {showDespesaForm ? 'Cancelar' : '+ Despesa'}
          </button>
        </div>

        {showDespesaForm && (
          <form
            style={{ padding: '0 18px 14px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}
            onSubmit={e => { e.preventDefault(); addDespesa.mutate(e.currentTarget) }}
          >
            <label className={styles.fieldGroup}>
              <span>Categoria</span>
              <input name="categoria" required placeholder="Ex.: Software jurídico" />
            </label>
            <label className={styles.fieldGroup}>
              <span>Fornecedor</span>
              <input name="fornecedor" required />
            </label>
            <label className={styles.fieldGroup}>
              <span>Descrição (opcional)</span>
              <input name="descricao" />
            </label>
            <label className={styles.fieldGroup}>
              <span>Valor (R$)</span>
              <input name="valor" type="number" step="0.01" required />
            </label>
            <label className={styles.fieldGroup} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" name="tem_nota" defaultChecked />
              <span>Possui nota fiscal</span>
            </label>
            <label className={styles.fieldGroup} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" name="elegivel" />
              <span>Elegível para crédito IBS/CBS</span>
            </label>
            <div style={{ gridColumn: '1/-1' }}>
              <button type="submit" className={styles.btnPrimary}>Adicionar despesa</button>
            </div>
          </form>
        )}

        <table className={styles.table}>
          <thead>
            <tr>
              <th>Categoria</th><th>Fornecedor</th>
              <th style={{ textAlign: 'right' }}>Valor</th>
              <th>Nota</th><th>Elegível</th>
              <th style={{ textAlign: 'right' }}>Crédito est.</th>
              <th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {data.despesas.length === 0 && (
              <tr><td colSpan={8} style={{ color: 'var(--gray-mid)', textAlign: 'center', padding: '12px 0' }}>
                Nenhuma despesa lançada ainda.
              </td></tr>
            )}
            {data.despesas.map((d: Despesa) => (
              <tr key={d.id}>
                <td style={{ fontSize: 12 }}>{d.categoria}</td>
                <td style={{ fontSize: 12, color: 'var(--gray-mid)' }}>{d.fornecedor}</td>
                <td style={{ textAlign: 'right' }}>{fmtBRL(d.valor)}</td>
                <td>
                  {d.tem_nota
                    ? <span style={{ fontSize: 10, background: '#dcfce7', color: '#15803d', padding: '2px 6px', borderRadius: 999 }}>sim</span>
                    : <span style={{ fontSize: 10, color: '#ef4444' }}>não</span>}
                </td>
                <td>
                  <button
                    onClick={() => patchElegivel.mutate({ id: d.id, elegivel: !d.elegivel })}
                    style={{
                      fontSize: 10, padding: '2px 6px', borderRadius: 999, border: 'none', cursor: 'pointer',
                      background: d.elegivel ? '#dcfce7' : '#f3f4f6',
                      color: d.elegivel ? '#15803d' : '#6b7280',
                      fontWeight: 600,
                    }}
                  >
                    {d.elegivel ? 'sim' : 'não'}
                  </button>
                </td>
                <td style={{ textAlign: 'right', color: d.credito.total > 0 ? 'var(--teal)' : 'var(--gray-mid)', fontWeight: d.credito.total > 0 ? 700 : 400 }}>
                  {fmtBRL(d.credito.total)}
                </td>
                <td>
                  <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 999, background: '#f3f4f6', color: STATUS_COR[d.status] || '#6b7280', fontWeight: 600 }}>
                    {d.status}
                  </span>
                </td>
                <td>
                  <button style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 13 }}
                    onClick={() => deleteDespesa.mutate(d.id)}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Tab: Créditos (catálogo de regras) ──────────────────────────────────────

function TabCreditos() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['backoffice-regras'],
    queryFn: () => backofficeApi.regras(),
  })

  const patch = useMutation({
    mutationFn: ({ id, ...body }: { id: string; [k: string]: unknown }) =>
      backofficeApi.patchRegra(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backoffice-regras'] }),
  })

  if (isLoading || !data) return <div className={styles.empty}>Carregando…</div>

  return (
    <div>
      <div className={styles.tableCard} style={{ marginBottom: 12 }}>
        <div style={{ padding: '12px 18px', fontSize: 12, color: 'var(--gray-mid)', borderBottom: '1px solid #f3f4f6' }}>
          <strong>Catálogo de regras de crédito IBS/CBS</strong> — cada categoria de despesa pode ser
          validada uma vez e reutilizada nos meses seguintes. Regras com mais de 6 meses sem revisão
          aparecem como "revalidar".
        </div>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Categoria</th><th>Base legal</th><th>Elegível</th>
              <th>Status</th><th>Última revisão</th><th>Próxima revisão</th><th></th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 && (
              <tr><td colSpan={7} style={{ color: 'var(--gray-mid)', textAlign: 'center', padding: '12px 0' }}>
                Nenhuma regra cadastrada ainda. Regras são criadas ao lançar despesas.
              </td></tr>
            )}
            {data.map(r => (
              <tr key={r.id}>
                <td style={{ fontWeight: 600, fontSize: 12 }}>{r.categoria}</td>
                <td style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{r.base_legal}</td>
                <td>
                  <button
                    onClick={() => patch.mutate({ id: r.id, elegivel: !r.elegivel })}
                    style={{
                      fontSize: 10, padding: '2px 6px', borderRadius: 999, border: 'none', cursor: 'pointer',
                      background: r.elegivel ? '#dcfce7' : '#f3f4f6',
                      color: r.elegivel ? '#15803d' : '#6b7280', fontWeight: 600,
                    }}
                  >
                    {r.elegivel ? 'sim' : 'não'}
                  </button>
                </td>
                <td>
                  <select
                    value={r.status}
                    onChange={e => patch.mutate({ id: r.id, status: e.target.value })}
                    style={{ fontSize: 11, border: '1px solid #e5e7eb', borderRadius: 4, padding: '2px 4px', color: STATUS_COR[r.status] }}
                  >
                    <option value="validado">validado</option>
                    <option value="pendente">pendente</option>
                    <option value="revalidar">revalidar</option>
                    <option value="excecao">exceção</option>
                  </select>
                </td>
                <td style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{r.last_check ?? '—'}</td>
                <td style={{ fontSize: 11, color: r.next_check ? '#b45309' : 'var(--gray-mid)' }}>{r.next_check ?? '—'}</td>
                <td style={{ fontSize: 11, color: 'var(--gray-mid)', maxWidth: 200, whiteSpace: 'normal' }}>{r.notas}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Tab: Anual ───────────────────────────────────────────────────────────────

function TabAnual() {
  const { data, isLoading } = useQuery({
    queryKey: ['backoffice-anual'],
    queryFn: () => backofficeApi.anual(),
  })

  if (isLoading || !data) return <div className={styles.empty}>Carregando…</div>
  if (data.length === 0) return (
    <div className={styles.empty}>Nenhum mês com receita registrada ainda.</div>
  )

  const regimeCores: Record<string, string> = {
    simples: '#0d9488', lp: '#1d4ed8', lr: '#7c3aed',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {data.map((m: MesAnual) => (
          <div key={m.mes} className={styles.tableCard} style={{ padding: '14px 18px', minWidth: 200, flex: '1 0 200px' }}>
            <div style={{ fontSize: 11, color: 'var(--gray-mid)', fontWeight: 700, textTransform: 'uppercase' }}>{mesLabel(m.mes)}</div>
            <div style={{ fontSize: 16, fontWeight: 800, color: regimeCores[m.vencedor] || 'var(--dark)', marginTop: 6 }}>
              {m.vencedor_nome}
            </div>
            <div style={{ fontSize: 12, marginTop: 8, display: 'flex', flexDirection: 'column', gap: 3 }}>
              <span style={{ color: 'var(--gray-mid)' }}>Receita <strong>{fmtBRL(m.receita_total)}</strong></span>
              <span style={{ color: 'var(--teal)' }}>Crédito <strong>{fmtBRL(m.credito_total)}</strong></span>
              <span style={{ color: 'var(--gray-mid)' }}>Carga <strong>{fmtPct(m.carga_efetiva_pct)}</strong></span>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.tableCard}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Mês</th><th>Regime vencedor</th>
              <th style={{ textAlign: 'right' }}>Receita</th>
              <th style={{ textAlign: 'right' }}>Crédito IBS/CBS</th>
              <th style={{ textAlign: 'right' }}>Carga efetiva</th>
            </tr>
          </thead>
          <tbody>
            {data.map((m: MesAnual) => (
              <tr key={m.mes}>
                <td style={{ fontWeight: 600 }}>{mesLabel(m.mes)}</td>
                <td style={{ color: regimeCores[m.vencedor] || 'var(--dark)', fontWeight: 600 }}>{m.vencedor_nome}</td>
                <td style={{ textAlign: 'right' }}>{fmtBRL(m.receita_total)}</td>
                <td style={{ textAlign: 'right', color: 'var(--teal)', fontWeight: 600 }}>{fmtBRL(m.credito_total)}</td>
                <td style={{ textAlign: 'right' }}>{fmtPct(m.carga_efetiva_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

type Tab = 'comparativo' | 'lancamentos' | 'creditos' | 'anual'

const TABS: { id: Tab; label: string }[] = [
  { id: 'comparativo', label: 'Comparativo' },
  { id: 'lancamentos', label: 'Lançamentos' },
  { id: 'creditos', label: 'Crédito IBS/CBS' },
  { id: 'anual', label: 'Visão Anual' },
]

export default function BackofficeDecisaoPage() {
  const [mes, setMes] = useState(mesAtual)
  const [tab, setTab] = useState<Tab>('comparativo')

  return (
    <div>
      {/* Cabeçalho */}
      <div className={styles.pageHeader} style={{ flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 className={styles.pageTitle}>Decisão <strong>Tributária</strong></h1>
          <div style={{ fontSize: 12, color: 'var(--gray-mid)', marginTop: 2 }}>
            Comparativo Simples Nacional · Lucro Presumido · Lucro Real — com crédito IBS/CBS da Reforma
          </div>
        </div>
        <input
          type="month"
          value={mes}
          onChange={e => setMes(e.target.value)}
          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #e5e7eb', fontSize: 13 }}
        />
      </div>

      {/* Sub-nav */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid #e5e7eb', marginBottom: 20 }}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: '8px 18px',
              background: 'none',
              border: 'none',
              borderBottom: tab === t.id ? '2px solid var(--teal)' : '2px solid transparent',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: tab === t.id ? 700 : 400,
              color: tab === t.id ? 'var(--teal)' : 'var(--gray-mid)',
              transition: 'color .15s',
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Conteúdo */}
      {tab === 'comparativo' && <TabComparativo mes={mes} />}
      {tab === 'lancamentos' && <TabLancamentos mes={mes} />}
      {tab === 'creditos' && <TabCreditos />}
      {tab === 'anual' && <TabAnual />}
    </div>
  )
}
