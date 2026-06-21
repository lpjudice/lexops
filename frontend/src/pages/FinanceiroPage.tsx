import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { financeiroApi } from '../api/financeiro'
import type { HonorarioCreate, RecebimentoCreate, StatusHonorario, TipoHonorario, FormaPagamento, FluxoMes } from '../api/financeiro'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import CurrencyInput from '../components/CurrencyInput'
import ComboBox from '../components/ComboBox'
import type { ComboOption } from '../components/ComboBox'
import styles from './Page.module.css'
import cs from './FinanceiroPage.module.css'

const STATUS_LABEL: Record<StatusHonorario, string> = {
  pendente: 'Pendente', parcial: 'Parcial', pago: 'Pago', cancelado: 'Cancelado',
}
const TIPO_LABEL: Record<TipoHonorario, string> = {
  fixo: 'Fixo', percentual: 'Percentual', exito: 'Êxito',
}
const FORMAS: FormaPagamento[] = ['pix', 'ted', 'boleto', 'cheque', 'dinheiro', 'outro']
const MESES_PT = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

const EMPTY_H: HonorarioCreate = {
  cliente_id: '', descricao: '', tipo: 'fixo', valor_total: 0,
}
const EMPTY_REC: RecebimentoCreate = {
  valor: 0, data_recebimento: new Date().toISOString().slice(0, 10), forma_pagamento: 'pix',
}

function fmtVal(v: number) {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function fmtData(d: string) {
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

export default function FinanceiroPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [aba, setAba] = useState<'recebiveis' | 'fluxo'>('recebiveis')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<HonorarioCreate>(EMPTY_H)
  const [expandido, setExpandido] = useState<string | null>(null)
  const [recForm, setRecForm] = useState<RecebimentoCreate>(EMPTY_REC)
  const [filtroStatus, setFiltroStatus] = useState<string>('')
  const [editandoValor, setEditandoValor] = useState<string | null>(null)
  const [novoValor, setNovoValor] = useState(0)
  // Edição completa de honorário
  const [editandoHonorario, setEditandoHonorario] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Partial<HonorarioCreate & { status: StatusHonorario }>>({})
  // Criação rápida de cliente inline
  const [novoClienteNome, setNovoClienteNome] = useState('')
  const [showNovoCliente, setShowNovoCliente] = useState(false)
  const [novoClienteEmail, setNovoClienteEmail] = useState('')

  const { data: honorarios = [], isLoading } = useQuery({
    queryKey: ['honorarios', filtroStatus],
    queryFn: () => financeiroApi.listarHonorarios(
      filtroStatus === 'ag_assinatura'
        ? { pendente_assinatura: true }
        : filtroStatus
          ? { status: filtroStatus }
          : undefined
    ),
  })

  const { data: pendentesAssinatura = [] } = useQuery({
    queryKey: ['honorarios-pendentes-assinatura'],
    queryFn: () => financeiroApi.listarHonorarios(),
    select: (data) => data.filter((h) => h.pendente_assinatura),
  })
  const { data: resumo } = useQuery({
    queryKey: ['financeiro-resumo'],
    queryFn: () => financeiroApi.resumo(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })
  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })

  // Options for ComboBox
  const clienteOptions: ComboOption[] = clientes.map((c) => ({ value: c.id, label: c.nome }))
  const processoOptions: ComboOption[] = processos.map((p) => {
    const cl = clientes.find((c) => c.id === p.cliente_id)
    return {
      value: p.id,
      label: p.numero_cnj,
      sublabel: cl ? `Cliente: ${cl.nome}` : undefined,
    }
  })

  const criarClienteRapido = useMutation({
    mutationFn: (nome: string) => clientesApi.criar({ nome, tipo: 'PF', email: novoClienteEmail || undefined }),
    onSuccess: (novo) => {
      qc.invalidateQueries({ queryKey: ['clientes'] })
      setForm((f) => ({ ...f, cliente_id: novo.id }))
      setShowNovoCliente(false)
      setNovoClienteEmail('')
    },
  })

  const criar = useMutation({
    mutationFn: financeiroApi.criarHonorario,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
      setShowForm(false)
      setForm(EMPTY_H)
    },
  })

  const deletar = useMutation({
    mutationFn: financeiroApi.deletarHonorario,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
    },
  })

  const adicionarRec = useMutation({
    mutationFn: ({ hid, data }: { hid: string; data: RecebimentoCreate }) =>
      financeiroApi.adicionarRecebimento(hid, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
      setRecForm(EMPTY_REC)
    },
  })

  const editarValor = useMutation({
    mutationFn: ({ id, valor_total }: { id: string; valor_total: number }) =>
      financeiroApi.atualizarHonorario(id, { valor_total }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
      setEditandoValor(null)
    },
  })

  const atualizarTudo = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<HonorarioCreate & { status: StatusHonorario; contrato_orfao: boolean }> }) =>
      financeiroApi.atualizarHonorario(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
      setEditandoHonorario(null)
    },
  })

  const removerRec = useMutation({
    mutationFn: ({ hid, rid }: { hid: string; rid: string }) =>
      financeiroApi.removerRecebimento(hid, rid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
    },
  })

  const clienteNome = (id: string) => clientes.find((c) => c.id === id)?.nome ?? '—'

  // Barra de meses: normaliza altura relativa
  const maxMes = resumo
    ? Math.max(...resumo.por_mes.map((m) => m.total_recebido), 1)
    : 1

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Financeiro</h1>
        {aba === 'recebiveis' && (
          <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancelar' : '+ Novo Honorário'}
          </button>
        )}
      </div>

      {/* Abas: Recebíveis (contratos/honorários) × Fluxo de Caixa (entradas reais) */}
      <div style={{ display: 'flex', gap: 8, borderBottom: '2px solid #e5e7eb', marginBottom: 20 }}>
        {([['recebiveis', 'Recebíveis'], ['fluxo', 'Fluxo de Caixa']] as const).map(([k, label]) => (
          <button key={k} onClick={() => setAba(k)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: '8px 14px',
              fontSize: 14, fontWeight: aba === k ? 700 : 500,
              color: aba === k ? '#0f766e' : '#6b7280',
              borderBottom: aba === k ? '2px solid #0f766e' : '2px solid transparent',
              marginBottom: -2,
            }}>
            {label}
          </button>
        ))}
      </div>

      {aba === 'fluxo' && <FluxoCaixaView />}

      {/* Cards de resumo — Honorários */}
      {aba === 'recebiveis' && resumo && (
        <>
          <div className={cs.sectionTitle} style={{ marginBottom: 6 }}>Honorários</div>
          <div className={cs.summaryGrid}>
            <div className={cs.summaryCard}>
              <div className={cs.summaryLabel}>Total Contratado</div>
              <div className={cs.summaryValue}>{fmtVal(resumo.total_contratado)}</div>
            </div>
            <div className={cs.summaryCard}>
              <div className={cs.summaryLabel}>Total Recebido</div>
              <div className={`${cs.summaryValue} ${cs.verde}`}>{fmtVal(resumo.total_recebido)}</div>
            </div>
            <div className={cs.summaryCard}>
              <div className={cs.summaryLabel}>A Receber</div>
              <div className={`${cs.summaryValue} ${cs.azul}`}>{fmtVal(resumo.total_pendente)}</div>
            </div>
            <div className={cs.summaryCard}>
              <div className={cs.summaryLabel}>Vencido</div>
              <div className={`${cs.summaryValue} ${resumo.total_vencido > 0 ? cs.vermelho : ''}`}>
                {fmtVal(resumo.total_vencido)}
              </div>
            </div>
          </div>

          {/* Card — Pendentes de Assinatura */}
          {pendentesAssinatura.length > 0 && (
            <div className={cs.summaryGrid} style={{ marginTop: 8 }}>
              <div className={`${cs.summaryCard} ${cs.cardPendente}`} style={{ gridColumn: '1 / -1' }}>
                <div className={cs.summaryLabel}>⏳ Ag. Assinaturas — {pendentesAssinatura.length} contrato(s)</div>
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 6 }}>
                  {pendentesAssinatura.map((h) => (
                    <span key={h.id} style={{ fontSize: 12, color: '#92400e' }}>
                      {h.descricao}: <strong>{h.valor_total.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</strong>
                    </span>
                  ))}
                </div>
                <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
                  Total: {fmtVal(pendentesAssinatura.reduce((s, h) => s + h.valor_total, 0))} — valores não incluídos nas projeções acima até a assinatura ser confirmada.
                </div>
              </div>
            </div>
          )}

          {/* Cards de resumo — Reembolsos */}
          <div className={cs.sectionTitle} style={{ margin: '12px 0 6px' }}>Reembolsos</div>
          <div className={cs.summaryGrid}>
            <div className={cs.summaryCard}>
              <div className={cs.summaryLabel}>Aguardando Pagamento</div>
              <div className={`${cs.summaryValue} ${resumo.total_reembolsos_pendentes > 0 ? cs.laranja : ''}`}>
                {fmtVal(resumo.total_reembolsos_pendentes)}
              </div>
            </div>
            <div className={cs.summaryCard}>
              <div className={cs.summaryLabel}>Reembolsados</div>
              <div className={`${cs.summaryValue} ${cs.verde}`}>{fmtVal(resumo.total_reembolsos_pagos)}</div>
            </div>
          </div>

          {/* Projeção por vencimento — 30/60/90 dias */}
          {(resumo.a_vencer_30 > 0 || resumo.a_vencer_60 > 0 || resumo.a_vencer_90 > 0) && (
            <>
              <div className={cs.sectionTitle} style={{ margin: '12px 0 6px' }}>A Vencer (por prazo)</div>
              <div className={cs.summaryGrid}>
                <div className={cs.summaryCard}>
                  <div className={cs.summaryLabel}>Até 30 dias</div>
                  <div className={`${cs.summaryValue} ${resumo.a_vencer_30 > 0 ? cs.amarelo : ''}`}>
                    {fmtVal(resumo.a_vencer_30)}
                  </div>
                </div>
                <div className={cs.summaryCard}>
                  <div className={cs.summaryLabel}>31 – 60 dias</div>
                  <div className={`${cs.summaryValue} ${resumo.a_vencer_60 > 0 ? cs.azul : ''}`}>
                    {fmtVal(resumo.a_vencer_60)}
                  </div>
                </div>
                <div className={cs.summaryCard}>
                  <div className={cs.summaryLabel}>61 – 90 dias</div>
                  <div className={cs.summaryValue}>{fmtVal(resumo.a_vencer_90)}</div>
                </div>
              </div>
            </>
          )}

          {/* Card de projeção de êxito */}
          {resumo.projecao_exito > 0 && (
            <>
              <div className={cs.sectionTitle} style={{ margin: '12px 0 6px' }}>Projeção de Êxito</div>
              <div className={cs.exitoCard}>
                <div className={cs.exitoDesc}>
                  Soma dos honorários de êxito esperados (valor da causa × % êxito), excluindo pagos e cancelados.
                  Este valor <strong>não</strong> compõe o total de honorários contratados.
                </div>
                <div className={cs.exitoValor}>{fmtVal(resumo.projecao_exito)}</div>
              </div>
            </>
          )}
        </>
      )}

      {/* Gráfico de meses */}
      {aba === 'recebiveis' && resumo && resumo.por_mes.length > 0 && (
        <div className={styles.form} style={{ marginBottom: 24 }}>
          <div className={cs.sectionTitle}>Recebimentos por mês</div>
          <div className={cs.mesesGrid}>
            {resumo.por_mes.map((m) => (
              <div key={`${m.ano}-${m.mes}`} className={cs.mesBar}>
                <div
                  className={cs.mesBarFill}
                  style={{ height: `${Math.max(4, (m.total_recebido / maxMes) * 64)}px` }}
                  title={fmtVal(m.total_recebido)}
                />
                <div className={cs.mesBarLabel}>{MESES_PT[m.mes - 1]}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Resumo por cliente */}
      {aba === 'recebiveis' && resumo && resumo.por_cliente.length > 0 && (
        <div className={styles.form} style={{ marginTop: 16, marginBottom: 24 }}>
          <div className={cs.sectionTitle} style={{ marginBottom: 6 }}>Por cliente</div>
          <div className={cs.clienteScroll}>
            {resumo.por_cliente.map((c) => (
              <div key={String(c.cliente_id)} className={cs.clienteRow}>
                <span className={cs.clienteNome}>{c.cliente_nome}</span>
                <div className={cs.clienteValores}>
                  <span className={cs.valorRecebido}>{fmtVal(c.total_recebido)}</span>
                  {c.saldo_pendente > 0 && (
                    <span className={cs.valorPendente}>({fmtVal(c.saldo_pendente)} pendente)</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Formulário novo honorário */}
      {aba === 'recebiveis' && showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); criar.mutate(form) }}
          className={styles.form}
        >
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Cliente *</label>
            <ComboBox
              options={clienteOptions}
              value={form.cliente_id}
              onChange={(v) => setForm({ ...form, cliente_id: v })}
              placeholder="Buscar ou criar cliente..."
              onCreate={(q) => { setNovoClienteNome(q); setShowNovoCliente(true) }}
              createLabel="Criar cliente"
              required
            />
            {showNovoCliente && (
              <div style={{ marginTop: 8, background: '#f0fdf9', border: '1px solid #a7f3d0', borderRadius: 8, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#065f46' }}>Criar cliente: {novoClienteNome}</div>
                <input
                  className={styles.input}
                  placeholder="E-mail (opcional)"
                  value={novoClienteEmail}
                  onChange={(e) => setNovoClienteEmail(e.target.value)}
                  style={{ fontSize: 12 }}
                />
                <div style={{ display: 'flex', gap: 6 }}>
                  <button type="button" className={styles.btnPrimary} style={{ fontSize: 12, padding: '5px 14px' }}
                    disabled={criarClienteRapido.isPending}
                    onClick={() => criarClienteRapido.mutate(novoClienteNome)}>
                    Criar
                  </button>
                  <button type="button" className={styles.btnDanger} onClick={() => setShowNovoCliente(false)}>Cancelar</button>
                </div>
              </div>
            )}
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição *</label>
            <input
              className={styles.input}
              placeholder="Ex: Honorários — Planejamento Sucessório"
              value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })}
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Processo (opcional)</label>
            <ComboBox
              options={processoOptions}
              value={form.processo_id ?? ''}
              onChange={(v) => setForm({ ...form, processo_id: v || undefined })}
              placeholder="Buscar por CNJ ou cliente..."
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Tipo</label>
            <select
              className={styles.input}
              value={form.tipo}
              onChange={(e) => setForm({ ...form, tipo: e.target.value as TipoHonorario })}
            >
              {(Object.entries(TIPO_LABEL) as [TipoHonorario, string][]).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>

          {/* Campos extras — Êxito */}
          {form.tipo === 'exito' && (
            <>
              <div className={cs.exitoFormBanner}>
                Honorário de êxito — preencha os dados abaixo para calcular a projeção. O valor total do êxito será calculado automaticamente.
              </div>
              <div className={styles.formRow}>
                <label className={styles.formLabel}>Valor da Causa (R$) *</label>
                <CurrencyInput
                  className={styles.input}
                  value={form.valor_causa ?? 0}
                  onChange={(v) => setForm({ ...form, valor_causa: v, valor_total: v * ((form.percentual_exito ?? 15) / 100) })}
                  placeholder="Ex: 500.000,00"
                />
              </div>
              <div className={styles.formRow}>
                <label className={styles.formLabel}>% Êxito</label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="number" min={0} max={100} step={0.5}
                    className={styles.input}
                    style={{ width: 100 }}
                    value={form.percentual_exito ?? 15}
                    onChange={(e) => {
                      const pct = parseFloat(e.target.value) || 0
                      setForm({ ...form, percentual_exito: pct, valor_total: (form.valor_causa ?? 0) * (pct / 100) })
                    }}
                  />
                  <span style={{ fontSize: 12, color: '#6b7280' }}>
                    = {((form.valor_causa ?? 0) * ((form.percentual_exito ?? 15) / 100)).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} esperado
                  </span>
                </div>
              </div>
              <div className={styles.formRow}>
                <label className={styles.formLabel}>Data estimada de sentença</label>
                <input
                  type="date"
                  className={styles.input}
                  value={form.data_estimada_sentenca ?? ''}
                  onChange={(e) => setForm({ ...form, data_estimada_sentenca: e.target.value || undefined })}
                />
              </div>
            </>
          )}

          <div className={styles.formRow}>
            <label className={styles.formLabel}>{form.tipo === 'exito' ? 'Valor Êxito Calculado (R$)' : 'Valor Total (R$) *'}</label>
            <CurrencyInput
              className={styles.input}
              value={form.valor_total}
              onChange={(v) => setForm({ ...form, valor_total: v })}
              placeholder="40.000,00"
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data do Contrato</label>
            <input
              type="date"
              className={styles.input}
              value={form.data_contrato ?? ''}
              onChange={(e) => setForm({ ...form, data_contrato: e.target.value || undefined })}
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data de Vencimento</label>
            <input
              type="date"
              className={styles.input}
              value={form.data_vencimento ?? ''}
              onChange={(e) => setForm({ ...form, data_vencimento: e.target.value || undefined })}
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Observações</label>
            <textarea
              className={styles.input}
              rows={2}
              value={form.observacoes ?? ''}
              onChange={(e) => setForm({ ...form, observacoes: e.target.value || undefined })}
            />
          </div>
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {/* Filtro status + Lista (somente Recebíveis) */}
      {aba === 'recebiveis' && (<>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {(['', 'pendente', 'parcial', 'pago', 'cancelado', 'ag_assinatura'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFiltroStatus(s)}
            style={{
              padding: '4px 12px',
              borderRadius: 999,
              border: '1px solid #e5e7eb',
              background: filtroStatus === s ? '#7c3aed' : '#f3f4f6',
              color: filtroStatus === s ? '#fff' : '#6b7280',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {s === '' ? 'Todos' : s === 'ag_assinatura' ? 'Ag. Assinatura' : STATUS_LABEL[s as StatusHonorario]}
          </button>
        ))}
      </div>

      {/* Lista */}
      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : honorarios.length === 0 ? (
        <p className={styles.empty}>Nenhum honorário encontrado.</p>
      ) : (
        <div className={cs.lista}>
          {honorarios.map((h) => {
            const pct = h.valor_total > 0
              ? Math.min(100, (h.total_recebido / h.valor_total) * 100)
              : 0
            const vencido = h.data_vencimento &&
              new Date(h.data_vencimento) < new Date() &&
              h.status !== 'pago'

            return (
              <div key={h.id} className={`${cs.card} ${h.contrato_orfao ? cs.cardOrfao : ''}`}>
                {h.contrato_orfao && (
                  <div className={cs.orfaoBanner}>
                    ⚠ Contrato vinculado foi excluído — este honorário precisa ser validado.
                    <button onClick={() => atualizarTudo.mutate({ id: h.id, data: { contrato_orfao: false } })}>
                      Manter
                    </button>
                    <button onClick={() => { if (confirm('Excluir este honorário?')) deletar.mutate(h.id) }}>
                      Excluir
                    </button>
                  </div>
                )}
                <div className={cs.cardTop}>
                  <div className={cs.cardLeft}>
                    <div className={cs.cardTitulo}>{h.descricao}</div>
                    <div className={cs.cardMeta}>
                      {clienteNome(h.cliente_id)} · {TIPO_LABEL[h.tipo]}
                      {h.data_vencimento && (
                        <span style={{ color: vencido ? '#b91c1c' : undefined }}>
                          {' '}· Vence {fmtData(h.data_vencimento)}
                          {vencido && ' ⚠'}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className={cs.cardRight}>
                    <div className={cs.progressWrap}>
                      <div className={cs.progressBar}>
                        <div className={cs.progressFill} style={{ width: `${pct}%` }} />
                      </div>
                      <div className={cs.progressLabel}>{pct.toFixed(0)}%</div>
                    </div>
                    {editandoValor === h.id ? (
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <CurrencyInput
                          className={styles.input}
                          value={novoValor}
                          onChange={setNovoValor}
                          placeholder="0,00"
                        />
                        <button
                          className={styles.btnPrimary}
                          style={{ padding: '5px 12px', fontSize: 12 }}
                          disabled={!novoValor || editarValor.isPending}
                          onClick={() => editarValor.mutate({ id: h.id, valor_total: novoValor })}
                        >
                          ✓
                        </button>
                        <button
                          className={styles.btnDanger}
                          onClick={() => setEditandoValor(null)}
                        >
                          ×
                        </button>
                      </div>
                    ) : (
                      <div
                        className={cs.valorTotal}
                        style={{ cursor: 'pointer' }}
                        title="Clique para editar"
                        onClick={() => { setEditandoValor(h.id); setNovoValor(h.valor_total) }}
                      >
                        {fmtVal(h.valor_total)} ✎
                      </div>
                    )}
                    <span className={`${cs.statusBadge} ${cs[`status_${h.status}`]}`}>
                      {STATUS_LABEL[h.status]}
                    </span>
                    <button
                      className={cs.btnExpand}
                      onClick={() => setExpandido(expandido === h.id ? null : h.id)}
                    >
                      {expandido === h.id ? '▲' : '▼'}
                    </button>
                    <button
                      className={styles.btnDanger}
                      onClick={() => { if (confirm('Remover honorário?')) deletar.mutate(h.id) }}
                    >
                      ×
                    </button>
                  </div>
                </div>

                {expandido === h.id && (
                  <div className={cs.cardBody}>
                    {/* Edição completa */}
                    {editandoHonorario === h.id ? (
                      <div>
                        <div className={cs.sectionTitle} style={{ marginBottom: 12 }}>Editar Honorário</div>
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Descrição</label>
                          <input className={styles.input}
                            value={editForm.descricao ?? h.descricao}
                            onChange={(e) => setEditForm({ ...editForm, descricao: e.target.value })} />
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Tipo</label>
                            <select className={styles.input}
                              value={editForm.tipo ?? h.tipo}
                              onChange={(e) => setEditForm({ ...editForm, tipo: e.target.value as TipoHonorario })}>
                              {(Object.entries(TIPO_LABEL) as [TipoHonorario, string][]).map(([k, v]) => (
                                <option key={k} value={k}>{v}</option>
                              ))}
                            </select>
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Status</label>
                            <select className={styles.input}
                              value={editForm.status ?? h.status}
                              onChange={(e) => setEditForm({ ...editForm, status: e.target.value as StatusHonorario })}>
                              {(Object.entries(STATUS_LABEL) as [StatusHonorario, string][]).map(([k, v]) => (
                                <option key={k} value={k}>{v}</option>
                              ))}
                            </select>
                          </div>
                        </div>
                        {(editForm.tipo ?? h.tipo) === 'exito' && (
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                            <div className={styles.formRow}>
                              <label className={styles.formLabel}>Valor da Causa (R$)</label>
                              <CurrencyInput className={styles.input}
                                value={editForm.valor_causa ?? h.valor_causa ?? 0}
                                onChange={(v) => setEditForm({
                                  ...editForm, valor_causa: v,
                                  valor_total: v * ((editForm.percentual_exito ?? h.percentual_exito ?? 15) / 100)
                                })} />
                            </div>
                            <div className={styles.formRow}>
                              <label className={styles.formLabel}>% Êxito</label>
                              <input type="number" min={0} max={100} step={0.5}
                                className={styles.input}
                                value={editForm.percentual_exito ?? h.percentual_exito ?? 15}
                                onChange={(e) => {
                                  const pct = parseFloat(e.target.value) || 0
                                  setEditForm({
                                    ...editForm, percentual_exito: pct,
                                    valor_total: (editForm.valor_causa ?? h.valor_causa ?? 0) * (pct / 100)
                                  })
                                }} />
                            </div>
                          </div>
                        )}
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Valor Total (R$)</label>
                          <CurrencyInput className={styles.input}
                            value={editForm.valor_total ?? h.valor_total}
                            onChange={(v) => setEditForm({ ...editForm, valor_total: v })} />
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Data do Contrato</label>
                            <input type="date" className={styles.input}
                              value={editForm.data_contrato ?? h.data_contrato ?? ''}
                              onChange={(e) => setEditForm({ ...editForm, data_contrato: e.target.value || undefined })} />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Data de Vencimento</label>
                            <input type="date" className={styles.input}
                              value={editForm.data_vencimento ?? h.data_vencimento ?? ''}
                              onChange={(e) => setEditForm({ ...editForm, data_vencimento: e.target.value || undefined })} />
                          </div>
                        </div>
                        {(editForm.tipo ?? h.tipo) === 'exito' && (
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Data estimada de sentença</label>
                            <input type="date" className={styles.input}
                              value={editForm.data_estimada_sentenca ?? h.data_estimada_sentenca ?? ''}
                              onChange={(e) => setEditForm({ ...editForm, data_estimada_sentenca: e.target.value || undefined })} />
                          </div>
                        )}
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Observações</label>
                          <textarea className={styles.input} rows={2}
                            value={editForm.observacoes ?? h.observacoes ?? ''}
                            onChange={(e) => setEditForm({ ...editForm, observacoes: e.target.value || undefined })} />
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button className={styles.btnPrimary}
                            disabled={atualizarTudo.isPending}
                            onClick={() => atualizarTudo.mutate({ id: h.id, data: editForm })}>
                            {atualizarTudo.isPending ? 'Salvando...' : '✓ Salvar'}
                          </button>
                          <button className={styles.btnTable}
                            onClick={() => { setEditandoHonorario(null); setEditForm({}) }}>
                            Cancelar
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <button className={styles.btnPrimary}
                          onClick={() => navigate(`/fiscal?honorario=${h.id}`)}>
                          🧾 Emitir NFS-e
                        </button>
                        <button className={cs.btnExpand}
                          onClick={() => { setEditandoHonorario(h.id); setEditForm({}) }}>
                          ✎ Editar honorário
                        </button>
                      </div>
                    )}

                    {/* Recebimentos */}
                    <div>
                      <div className={cs.sectionTitle}>
                        Recebimentos — {fmtVal(h.total_recebido)} de {fmtVal(h.valor_total)}
                        {h.saldo_pendente > 0 && (
                          <span style={{ color: '#92400e', marginLeft: 8 }}>
                            ({fmtVal(h.saldo_pendente)} pendente)
                          </span>
                        )}
                      </div>
                      <table className={cs.recTable}>
                        <thead>
                          <tr>
                            <th>Data</th>
                            <th>Forma</th>
                            <th>Observação</th>
                            <th style={{ textAlign: 'right' }}>Valor</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {h.recebimentos.map((rec) => (
                            <tr key={rec.id}>
                              <td>{fmtData(rec.data_recebimento)}</td>
                              <td style={{ textTransform: 'uppercase', fontSize: 11 }}>{rec.forma_pagamento}</td>
                              <td>{rec.observacao || '—'}</td>
                              <td className={cs.tdValor}>{fmtVal(rec.valor)}</td>
                              <td style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                <button
                                  className={styles.btnTable}
                                  title="Emitir NFS-e para este recebimento"
                                  onClick={() =>
                                    navigate(`/fiscal?honorario=${h.id}&recebimento=${rec.id}`)
                                  }
                                >
                                  🧾 NFS-e
                                </button>
                                <button
                                  className={styles.btnDanger}
                                  onClick={() => removerRec.mutate({ hid: h.id, rid: rec.id })}
                                >
                                  ×
                                </button>
                              </td>
                            </tr>
                          ))}
                          {h.recebimentos.length === 0 && (
                            <tr>
                              <td colSpan={5} style={{ color: '#9ca3af', textAlign: 'center', padding: 14 }}>
                                Nenhum recebimento registrado.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>

                    {/* Formulário novo recebimento */}
                    {h.status !== 'pago' && h.status !== 'cancelado' && (
                      <div>
                        <div className={cs.sectionTitle}>Registrar recebimento</div>
                        <div className={cs.recForm}>
                          <input
                            type="date"
                            className={styles.input}
                            value={recForm.data_recebimento}
                            onChange={(e) => setRecForm({ ...recForm, data_recebimento: e.target.value })}
                          />
                          <CurrencyInput
                            className={styles.input}
                            value={recForm.valor}
                            onChange={(v) => setRecForm({ ...recForm, valor: v })}
                            placeholder={`máx ${fmtVal(h.saldo_pendente)}`}
                          />
                          <select
                            className={styles.input}
                            value={recForm.forma_pagamento}
                            onChange={(e) => setRecForm({ ...recForm, forma_pagamento: e.target.value as FormaPagamento })}
                          >
                            {FORMAS.map((f) => <option key={f} value={f}>{f.toUpperCase()}</option>)}
                          </select>
                          <input
                            className={styles.input}
                            placeholder="Observação (opcional)"
                            value={recForm.observacao ?? ''}
                            onChange={(e) => setRecForm({ ...recForm, observacao: e.target.value || undefined })}
                          />
                          <button
                            className={styles.btnPrimary}
                            disabled={!recForm.valor}
                            onClick={() => adicionarRec.mutate({ hid: h.id, data: recForm })}
                          >
                            + Registrar
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      </>)}
    </div>
  )
}

// ─── Fluxo de Caixa (entradas reais por mês + crédito a receber) ───────────────

const MESES_NOME = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
function nomeCompet(c: string) {
  const [a, m] = c.split('-')
  return `${MESES_NOME[parseInt(m) - 1]} / ${a}`
}

function FluxoCaixaView() {
  const [aberto, setAberto] = useState<Record<string, boolean>>({})
  const { data, isLoading } = useQuery({
    queryKey: ['fluxo-caixa'],
    queryFn: () => financeiroApi.fluxoCaixa(),
  })

  if (isLoading) return <p className={styles.empty}>Carregando…</p>
  if (!data) return <p className={styles.empty}>Sem dados.</p>

  const totalEntradas = data.meses.reduce((s, m) => s + m.total, 0)
  const mesCorrente = new Date().toISOString().slice(0, 7)

  return (
    <div>
      {/* Cards resumo */}
      <div className={cs.summaryGrid} style={{ marginBottom: 20 }}>
        <div className={cs.summaryCard}>
          <div className={cs.summaryLabel}>Entradas (caixa) — total</div>
          <div className={cs.summaryValue} style={{ color: '#15803d' }}>{fmtVal(totalEntradas)}</div>
        </div>
        <div className={cs.summaryCard}>
          <div className={cs.summaryLabel}>Crédito a receber</div>
          <div className={cs.summaryValue} style={{ color: '#b45309' }}>{fmtVal(data.credito_a_receber.total)}</div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
            Honorários {fmtVal(data.credito_a_receber.honorarios_pendentes)} · NFs não pagas {fmtVal(data.credito_a_receber.nfs_nao_pagas)}
          </div>
        </div>
      </div>

      {/* Entradas por mês */}
      <div className={cs.sectionTitle} style={{ marginBottom: 10 }}>Entradas por mês</div>
      {data.meses.length === 0 ? (
        <p className={styles.empty}>Nenhuma entrada registrada ainda.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 28 }}>
          {data.meses.map((m: FluxoMes) => {
            const isAberto = aberto[m.competencia] ?? (m.competencia === mesCorrente)
            return (
              <div key={m.competencia} style={{ border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
                <div onClick={() => setAberto((a) => ({ ...a, [m.competencia]: !isAberto }))}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '12px 16px', cursor: 'pointer', background: '#f9fafb' }}>
                  <span style={{ fontWeight: 700, color: '#1f2937' }}>
                    {isAberto ? '▾' : '▸'} {nomeCompet(m.competencia)}
                    <span style={{ fontWeight: 400, color: '#6b7280', marginLeft: 8, fontSize: 12 }}>
                      {m.entradas.length} entrada(s)
                    </span>
                  </span>
                  <span style={{ fontWeight: 700, color: '#15803d' }}>{fmtVal(m.total)}</span>
                </div>
                {isAberto && (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <tbody>
                      {m.entradas.map((e, i) => (
                        <tr key={i} style={{ borderTop: '1px solid #f3f4f6' }}>
                          <td style={{ padding: '8px 16px', color: '#6b7280', whiteSpace: 'nowrap', width: 90 }}>{fmtData(e.data)}</td>
                          <td style={{ padding: '8px 8px' }}>
                            <div style={{ fontWeight: 600 }}>{e.cliente}</div>
                            <div style={{ fontSize: 11, color: '#6b7280' }}>{e.descricao}</div>
                          </td>
                          <td style={{ padding: '8px 8px', textAlign: 'center' }}>
                            <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, fontWeight: 700,
                              background: e.origem === 'nf_avulsa' ? '#eff6ff' : '#f0fdf4',
                              color: e.origem === 'nf_avulsa' ? '#1d4ed8' : '#15803d' }}>
                              {e.origem === 'nf_avulsa' ? 'NF avulsa' : e.forma.toUpperCase()}
                            </span>
                          </td>
                          <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 700, color: '#065f46', whiteSpace: 'nowrap' }}>
                            {fmtVal(e.valor)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Crédito a receber */}
      <div className={cs.sectionTitle} style={{ marginBottom: 10 }}>
        Crédito a receber (ainda não entrou no caixa)
      </div>
      {data.credito_a_receber.itens.length === 0 ? (
        <p className={styles.empty}>Nada pendente.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, border: '1px solid #e5e7eb', borderRadius: 10 }}>
          <thead>
            <tr style={{ background: '#fffbeb', borderBottom: '1px solid #fde68a' }}>
              <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600 }}>Origem</th>
              <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600 }}>Descrição</th>
              <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600 }}>Vencimento</th>
              <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 600 }}>Valor</th>
            </tr>
          </thead>
          <tbody>
            {data.credito_a_receber.itens.map((it, i) => (
              <tr key={i} style={{ borderTop: '1px solid #f3f4f6' }}>
                <td style={{ padding: '8px 16px' }}>
                  <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, fontWeight: 700,
                    background: it.tipo === 'nf' ? '#eff6ff' : '#f3e8ff',
                    color: it.tipo === 'nf' ? '#1d4ed8' : '#7c3aed' }}>
                    {it.tipo === 'nf' ? 'NF não paga' : 'Honorário'}
                  </span>
                </td>
                <td style={{ padding: '8px 8px' }}>
                  <div style={{ fontWeight: 600 }}>{it.cliente}</div>
                  <div style={{ fontSize: 11, color: '#6b7280' }}>{it.descricao}</div>
                </td>
                <td style={{ padding: '8px 8px', color: '#6b7280' }}>{it.vencimento ? fmtData(it.vencimento) : '—'}</td>
                <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 700, color: '#b45309', whiteSpace: 'nowrap' }}>
                  {fmtVal(it.valor)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
