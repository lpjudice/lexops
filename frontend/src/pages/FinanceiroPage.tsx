import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { financeiroApi } from '../api/financeiro'
import type { HonorarioCreate, ParcelaInput, RecebimentoCreate, StatusHonorario, TipoHonorario, FormaPagamento, FluxoMes } from '../api/financeiro'
import { fiscalApi } from '../api/fiscal'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import { contratosApi } from '../api/contratos'
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
  const comprovanteRefs = useRef<Record<string, HTMLInputElement | null>>({})
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
  // Parcelamento no novo recebível
  const [parcN, setParcN] = useState(1)
  const [parcNStr, setParcNStr] = useState('1')
  const [parc1Venc, setParc1Venc] = useState('')
  const [parcelasEdit, setParcelasEdit] = useState<ParcelaInput[]>([])
  // Edição inline de parcelas no card (id → {valor, data})
  const [parcEdits, setParcEdits] = useState<Record<string, { valor: number; data_vencimento: string }>>({})

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
      setParcN(1); setParcNStr('1'); setParc1Venc(''); setParcelasEdit([])
    },
  })

  const { data: contratos = [] } = useQuery({
    queryKey: ['contratos'],
    queryFn: () => contratosApi.listar(),
  })

  // Gera o cronograma de parcelas (divisão mensal a partir do 1º vencimento).
  const gerarParcelas = (n: number, primeiro: string, total: number) => {
    if (n < 2 || !primeiro) { setParcelasEdit([]); return }
    const base = Math.round((total / n) * 100) / 100
    const [y, m, d] = primeiro.split('-').map(Number)
    const itens: ParcelaInput[] = []
    let acc = 0
    for (let i = 0; i < n; i++) {
      const v = i === n - 1 ? Math.round((total - acc) * 100) / 100 : base
      if (i < n - 1) acc = Math.round((acc + base) * 100) / 100
      const dt = new Date(y, (m - 1) + i, d)
      const iso = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
      itens.push({ numero: i + 1, valor: v, data_vencimento: iso })
    }
    setParcelasEdit(itens)
  }

  const invalidarFin = () => {
    qc.invalidateQueries({ queryKey: ['honorarios'] })
    qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
  }
  const pagarParcela = useMutation({
    mutationFn: ({ id, data_recebimento, forma }: { id: string; data_recebimento: string; forma: FormaPagamento }) =>
      financeiroApi.pagarParcela(id, { data_recebimento, forma_pagamento: forma }),
    onSuccess: invalidarFin,
  })
  const reabrirParcela = useMutation({
    mutationFn: (id: string) => financeiroApi.reabrirParcela(id),
    onSuccess: invalidarFin,
  })
  const editarParcela = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { valor?: number; data_vencimento?: string } }) =>
      financeiroApi.editarParcela(id, data),
    onSuccess: invalidarFin,
  })
  const removerParcela = useMutation({
    mutationFn: (id: string) => financeiroApi.removerParcela(id),
    onSuccess: invalidarFin,
  })
  const enviarCobranca = useMutation({
    mutationFn: (id: string) => financeiroApi.enviarCobranca(id),
    onSuccess: (r) => { invalidarFin(); alert(`Cobrança enviada (${r.enviados}).`) },
    onError: (e: any) => alert(`Erro ao enviar cobrança:\n${e?.response?.data?.detail || e?.message || 'Erro'}`),
  })
  const toggleCobranca = useMutation({
    mutationFn: ({ id, ativa }: { id: string; ativa: boolean }) =>
      financeiroApi.atualizarHonorario(id, { cobranca_ativa: ativa } as any),
    onSuccess: invalidarFin,
  })

  const deletar = useMutation({
    mutationFn: financeiroApi.deletarHonorario,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
    },
  })

  // Anti-duplicação reversa: ao registrar recebimento, achar NF de mesmo valor
  // (não paga) e sugerir vincular, em vez de a NF virar outra entrada depois.
  const [vincNfPrompt, setVincNfPrompt] = useState<
    { recId: string; valor: number; matches: { id: string; numero_nfse?: string; tomador_nome: string; valor: number; competencia: string; data_emissao?: string }[] } | null
  >(null)
  const conciliarNfRec = useMutation({
    mutationFn: ({ nfId, recId }: { nfId: string; recId: string }) => fiscalApi.conciliar(nfId, recId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
      qc.invalidateQueries({ queryKey: ['fluxo-caixa'] })
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      setVincNfPrompt(null)
    },
  })
  const adicionarRec = useMutation({
    mutationFn: ({ hid, data }: { hid: string; data: RecebimentoCreate }) =>
      financeiroApi.adicionarRecebimento(hid, data),
    onSuccess: async (rec: any, variables) => {
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
      qc.invalidateQueries({ queryKey: ['fluxo-caixa'] })
      setRecForm(EMPTY_REC)
      // Procura NF emitida não paga de mesmo valor para sugerir conciliação
      try {
        const h = honorarios.find((x) => x.id === variables.hid)
        const val = Number(rec?.valor ?? variables.data.valor)
        if (rec?.id && h) {
          const nfs = await fiscalApi.nfsParaConciliar(h.cliente_id, val)
          const iguais = nfs.filter((n) => Math.abs(n.valor - val) < 0.01)
          if (iguais.length > 0) setVincNfPrompt({ recId: rec.id, valor: val, matches: iguais })
        }
      } catch { /* silencioso: conciliação é opcional */ }
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

  const uploadComprovante = useMutation({
    mutationFn: ({ recId, file }: { recId: string; file: File }) =>
      financeiroApi.uploadComprovante(recId, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['honorarios'] }),
    onError: (e: any) => alert(`Erro ao enviar comprovante:\n${e?.response?.data?.detail || e?.message || 'Erro'}`),
  })

  const removerComprovante = useMutation({
    mutationFn: (recId: string) => financeiroApi.removerComprovante(recId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['honorarios'] }),
  })

  const { data: pastaMestraFin } = useQuery({
    queryKey: ['financeiro-pasta-mestra'],
    queryFn: () => financeiroApi.pastaMestra(),
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
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {pastaMestraFin?.link && (
            <a href={pastaMestraFin.link} target="_blank" rel="noreferrer"
              title="Comprovantes e cópias das cobranças organizados por cliente"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13,
                padding: '7px 14px', borderRadius: 8, border: '1px solid #d1d5db',
                color: '#374151', textDecoration: 'none', background: '#fff',
              }}>
              ☁ Pasta mestra do Financeiro
            </a>
          )}
          {aba === 'recebiveis' && (
            <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
              {showForm ? 'Cancelar' : '+ Novo Honorário'}
            </button>
          )}
        </div>
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
          onSubmit={(e) => {
            e.preventDefault()
            const usaParcelas = parcN >= 2 && parcelasEdit.length > 0
            const base: HonorarioCreate = {
              ...form,
              cobranca_emails: (form.cobranca_emails ?? []).map((e) => e.trim()).filter(Boolean),
            }
            const payload: HonorarioCreate = usaParcelas
              ? { ...base, parcelas: parcelasEdit, valor_total: parcelasEdit.reduce((s, p) => s + p.valor, 0) }
              : base
            criar.mutate(payload)
          }}
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
          {/* ── Parcelamento ─────────────────────────────────────────── */}
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Parcelamento</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input type="number" min={1} className={styles.input} style={{ width: 90 }}
                value={parcNStr}
                onChange={(e) => {
                  const raw = e.target.value
                  setParcNStr(raw)
                  const n = Math.max(1, parseInt(raw) || 1)
                  setParcN(n)
                  gerarParcelas(n, parc1Venc, form.valor_total)
                }}
                onBlur={() => setParcNStr(String(parcN))}
                title="Nº de parcelas" />
              <span style={{ fontSize: 12, color: '#6b7280' }}>parcela(s), 1º venc.:</span>
              <input type="date" className={styles.input} style={{ width: 170 }}
                value={parc1Venc}
                onChange={(e) => { setParc1Venc(e.target.value); gerarParcelas(parcN, e.target.value, form.valor_total) }} />
              {parcN >= 2 && (
                <button type="button" className={styles.btnTable}
                  onClick={() => gerarParcelas(parcN, parc1Venc, form.valor_total)}>↻ Recalcular</button>
              )}
            </div>
            {parcN >= 2 && parcelasEdit.length > 0 && (
              <div style={{ marginTop: 8, border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
                <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: '#f9fafb' }}>
                      <th style={{ padding: 6, textAlign: 'left' }}>#</th>
                      <th style={{ padding: 6, textAlign: 'left' }}>Vencimento</th>
                      <th style={{ padding: 6, textAlign: 'left' }}>Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parcelasEdit.map((p, i) => (
                      <tr key={i} style={{ borderTop: '1px solid #eee' }}>
                        <td style={{ padding: 6 }}>{p.numero}</td>
                        <td style={{ padding: 6 }}>
                          <input type="date" className={styles.input} style={{ padding: '4px 6px' }}
                            value={p.data_vencimento}
                            onChange={(e) => setParcelasEdit(parcelasEdit.map((x, j) => j === i ? { ...x, data_vencimento: e.target.value } : x))} />
                        </td>
                        <td style={{ padding: 6, width: 160 }}>
                          <CurrencyInput className={styles.input} style={{ padding: '4px 6px' }}
                            value={p.valor}
                            onChange={(v) => setParcelasEdit(parcelasEdit.map((x, j) => j === i ? { ...x, valor: v } : x))} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ padding: '6px 8px', fontSize: 12, textAlign: 'right', background: '#f9fafb', color: '#374151' }}>
                  Soma das parcelas: <b>{fmtVal(parcelasEdit.reduce((s, p) => s + p.valor, 0))}</b>
                  {Math.abs(parcelasEdit.reduce((s, p) => s + p.valor, 0) - form.valor_total) > 0.01 && (
                    <span style={{ color: '#b91c1c', fontWeight: 700 }}> · ⚠ soma total incorreta</span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ── Vínculo com contrato ─────────────────────────────────── */}
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Vincular a contrato (opcional)</label>
            <ComboBox
              options={contratos
                .filter((c) => !form.cliente_id || c.cliente_id === form.cliente_id)
                .map((c) => ({ value: c.id, label: c.titulo, sublabel: c.status }))}
              value={form.contrato_id ?? ''}
              onChange={(v) => setForm({ ...form, contrato_id: v || undefined })}
              placeholder="Buscar contrato..."
            />
          </div>

          {/* ── Cobrança automática ──────────────────────────────────── */}
          <div className={styles.formRow}>
            <label className={styles.formLabel} style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer' }}>
              <input type="checkbox" checked={!!form.cobranca_ativa}
                onChange={(e) => {
                  const ativa = e.target.checked
                  const clienteSel = clientes.find((c) => c.id === form.cliente_id)
                  const jaTemEmails = (form.cobranca_emails ?? []).length > 0
                  setForm({
                    ...form,
                    cobranca_ativa: ativa,
                    cobranca_emails: ativa && !jaTemEmails && clienteSel?.email
                      ? [clienteSel.email]
                      : form.cobranca_emails,
                  })
                }} />
              Cobrança automática (e-mail + PDF ao cliente até o pagamento)
            </label>
            {form.cobranca_ativa && (() => {
              const clienteSel = clientes.find((c) => c.id === form.cliente_id)
              const candidatos = [clienteSel?.email, clienteSel?.responsavel_email]
                .filter((e): e is string => !!e)
              const selecionados = form.cobranca_emails ?? []
              const extras = selecionados
                .map((email, idx) => ({ email, idx }))
                .filter(({ email }) => !candidatos.includes(email))

              const toggleCandidato = (email: string) => {
                setForm({
                  ...form,
                  cobranca_emails: selecionados.includes(email)
                    ? selecionados.filter((e) => e !== email)
                    : [...selecionados, email],
                })
              }
              const addExtra = () => setForm({ ...form, cobranca_emails: [...selecionados, ''] })
              const updateExtraAt = (idx: number, value: string) => {
                const novo = [...selecionados]
                novo[idx] = value
                setForm({ ...form, cobranca_emails: novo })
              }
              const removeAt = (idx: number) => {
                setForm({ ...form, cobranca_emails: selecionados.filter((_, i) => i !== idx) })
              }

              return (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>Enviar cobrança para:</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                    {candidatos.length === 0 && extras.length === 0 && (
                      <span style={{ fontSize: 12, color: '#b45309' }}>⚠ Cliente sem e-mail cadastrado — adicione abaixo</span>
                    )}
                    {candidatos.map((email) => {
                      const ativo = selecionados.includes(email)
                      return (
                        <button key={email} type="button"
                          onClick={() => toggleCandidato(email)}
                          style={{
                            padding: '5px 12px', borderRadius: 999, fontSize: 12, cursor: 'pointer',
                            border: ativo ? '1px solid #7c3aed' : '1px solid #d1d5db',
                            background: ativo ? '#f5f3ff' : '#fff',
                            color: ativo ? '#5b21b6' : '#374151',
                          }}>
                          {ativo ? '✓ ' : ''}📧 {email}
                        </button>
                      )
                    })}
                    <button type="button" onClick={addExtra}
                      style={{
                        padding: '5px 12px', borderRadius: 999, fontSize: 12, cursor: 'pointer',
                        border: '1px dashed #d1d5db', background: '#fff', color: '#374151',
                      }}>
                      + adicionar e-mail
                    </button>
                  </div>
                  {extras.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                      {extras.map(({ email, idx }) => (
                        <div key={idx} style={{ display: 'flex', gap: 6 }}>
                          <input className={styles.input} type="email" value={email}
                            onChange={(e) => updateExtraAt(idx, e.target.value)}
                            placeholder="E-mail adicional" autoFocus={email === ''} />
                          <button type="button" className={styles.btnDanger} onClick={() => removeAt(idx)}>×</button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })()}
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
          <button type="submit" className={styles.btnPrimary}
            disabled={criar.isPending || (parcN >= 2 && parcelasEdit.length > 0 && Math.abs(parcelasEdit.reduce((s, p) => s + p.valor, 0) - form.valor_total) > 0.01)}>
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
            const parcelasVencidas = (h.parcelas || []).filter(
              (p) => p.status === 'pendente' && new Date(p.data_vencimento + 'T12:00:00') < new Date()
            )

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
                    <div className={cs.cardTitulo}>
                      {h.descricao}
                      {parcelasVencidas.length > 0 && (
                        <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 700, color: '#a2585e', background: '#fbeeee', border: '1px solid #f3d6d6', borderRadius: 999, padding: '2px 9px' }}>
                          ⚠ {parcelasVencidas.length} parcela(s) vencida(s)
                        </span>
                      )}
                    </div>
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
                        <button className={cs.btnExpand}
                          onClick={() => { setEditandoHonorario(h.id); setEditForm({}) }}>
                          ✎ Editar honorário
                        </button>
                      </div>
                    )}

                    {/* Cobrança automática + Parcelas (cronograma) */}
                    {(h.parcelas?.length > 0 || h.cobranca_ativa) && (
                      <div style={{ marginBottom: 14 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
                          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
                            <input type="checkbox" checked={!!h.cobranca_ativa}
                              onChange={(e) => toggleCobranca.mutate({ id: h.id, ativa: e.target.checked })} />
                            💌 Cobrança automática
                          </label>
                          {h.cobranca_ativa && (
                            <button className={styles.btnTable}
                              disabled={enviarCobranca.isPending}
                              onClick={() => enviarCobranca.mutate(h.id)}
                              title="Envia agora o e-mail + PDF das parcelas vencidas">
                              📧 Enviar cobrança agora
                            </button>
                          )}
                        </div>
                        {h.parcelas?.length > 0 && (
                          <>
                            <div className={cs.sectionTitle}>Parcelas</div>
                            <table className={cs.recTable}>
                              <thead>
                                <tr><th>#</th><th>Vencimento</th><th style={{ textAlign: 'right' }}>Valor</th><th>Situação</th><th></th></tr>
                              </thead>
                              <tbody>
                                {h.parcelas.map((p) => {
                                  const ed = parcEdits[p.id]
                                  const atrasada = p.status === 'pendente' && new Date(p.data_vencimento + 'T12:00:00') < new Date()
                                  return (
                                    <tr key={p.id}>
                                      <td>{p.numero}</td>
                                      <td>
                                        {p.status === 'pendente' ? (
                                          <input type="date" className={styles.input} style={{ padding: '3px 6px' }}
                                            value={ed?.data_vencimento ?? p.data_vencimento}
                                            onChange={(e) => setParcEdits({ ...parcEdits, [p.id]: { valor: ed?.valor ?? p.valor, data_vencimento: e.target.value } })} />
                                        ) : fmtData(p.data_vencimento)}
                                      </td>
                                      <td className={cs.tdValor}>
                                        {p.status === 'pendente' ? (
                                          <CurrencyInput className={styles.input} style={{ padding: '3px 6px', width: 130 }}
                                            value={ed?.valor ?? p.valor}
                                            onChange={(v) => setParcEdits({ ...parcEdits, [p.id]: { data_vencimento: ed?.data_vencimento ?? p.data_vencimento, valor: v } })} />
                                        ) : fmtVal(p.valor)}
                                      </td>
                                      <td>
                                        <span style={{ fontSize: 11, fontWeight: 700, color: p.status === 'pago' ? '#2f6f5e' : atrasada ? '#a2585e' : '#6b7280' }}>
                                          {p.status === 'pago' ? '✓ Paga' : atrasada ? 'Vencida' : 'A vencer'}
                                        </span>
                                      </td>
                                      <td style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                        {p.status === 'pendente' ? (
                                          <>
                                            {ed && (ed.valor !== p.valor || ed.data_vencimento !== p.data_vencimento) && (
                                              <button className={styles.btnTable} title="Salvar alterações da parcela"
                                                onClick={() => { editarParcela.mutate({ id: p.id, data: ed }); const { [p.id]: _, ...rest } = parcEdits; setParcEdits(rest) }}>💾</button>
                                            )}
                                            <button className={styles.btnPrimary} style={{ padding: '3px 10px', fontSize: 12 }}
                                              title="Marcar parcela como paga (gera recebimento)"
                                              onClick={() => pagarParcela.mutate({ id: p.id, data_recebimento: new Date().toISOString().slice(0, 10), forma: 'pix' })}>
                                              ✓ Pagar
                                            </button>
                                            <button className={styles.btnDanger}
                                              onClick={() => { if (confirm('Remover esta parcela?')) removerParcela.mutate(p.id) }}>×</button>
                                          </>
                                        ) : (
                                          <button className={styles.btnTable} title="Reabrir (desfaz o pagamento)"
                                            onClick={() => reabrirParcela.mutate(p.id)}>↩ Reabrir</button>
                                        )}
                                      </td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                              Ao pagar uma parcela, é criado um recebimento — a NFS-e é emitida por recebimento na lista abaixo.
                            </div>
                          </>
                        )}
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
                            <th>Comprovante</th>
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
                              <td>
                                {rec.comprovante_filename ? (
                                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                    {rec.comprovante_drive_link ? (
                                      <a href={rec.comprovante_drive_link} target="_blank" rel="noreferrer"
                                        style={{ fontSize: 12, color: '#2563eb' }}>
                                        📎 {rec.comprovante_filename}
                                      </a>
                                    ) : (
                                      <span style={{ fontSize: 12, color: '#6b7280' }}>📎 {rec.comprovante_filename}</span>
                                    )}
                                    <button className={styles.btnDanger}
                                      title="Remover comprovante"
                                      onClick={() => { if (confirm('Remover comprovante?')) removerComprovante.mutate(rec.id) }}>
                                      ×
                                    </button>
                                  </div>
                                ) : (
                                  <label className={styles.btnTable} style={{ cursor: 'pointer', display: 'inline-block' }}>
                                    {uploadComprovante.isPending ? '⏳' : '📎 Anexar'}
                                    <input
                                      ref={(el) => { comprovanteRefs.current[rec.id] = el }}
                                      type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                                      onChange={(e) => {
                                        const file = e.target.files?.[0]
                                        if (file) uploadComprovante.mutate({ recId: rec.id, file })
                                        if (comprovanteRefs.current[rec.id]) comprovanteRefs.current[rec.id]!.value = ''
                                      }}
                                    />
                                  </label>
                                )}
                              </td>
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
                              <td colSpan={6} style={{ color: '#9ca3af', textAlign: 'center', padding: 14 }}>
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

      {/* Anti-duplicação reversa: recebimento registrado combina com NF não paga */}
      {vincNfPrompt && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={(e) => { if (e.target === e.currentTarget) setVincNfPrompt(null) }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: 20, maxWidth: 440, width: '90%' }}>
            <div style={{ fontWeight: 700, fontSize: 16, color: '#1f2937', marginBottom: 4 }}>Vincular à NF?</div>
            <div style={{ fontSize: 13, color: '#374151', marginBottom: 12 }}>
              Existe NF emitida <b>não paga</b> de mesmo valor ({fmtVal(vincNfPrompt.valor)}). Se este recebimento é o
              pagamento dela, vincule — assim a NF não vira <b>outra</b> entrada no Fluxo de Caixa.
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {vincNfPrompt.matches.map((n) => (
                <button key={n.id} disabled={conciliarNfRec.isPending}
                  onClick={() => conciliarNfRec.mutate({ nfId: n.id, recId: vincNfPrompt.recId })}
                  style={{ textAlign: 'left', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: '10px 12px', cursor: 'pointer' }}>
                  <span style={{ fontWeight: 700, color: '#15803d' }}>
                    {n.numero_nfse ? `NF #${n.numero_nfse}` : 'NF'} · {fmtVal(n.valor)}
                  </span>
                  <div style={{ fontSize: 11, color: '#6b7280' }}>
                    {n.tomador_nome} · comp. {n.competencia}
                    {n.data_emissao && ` · emitida ${fmtData(n.data_emissao)}`}
                  </div>
                </button>
              ))}
            </div>
            <button onClick={() => setVincNfPrompt(null)}
              style={{ marginTop: 12, background: '#fff', color: '#374151', border: '1px solid #d1d5db', borderRadius: 8, padding: '8px 14px', cursor: 'pointer' }}>
              Não vincular (deixar separado)
            </button>
          </div>
        </div>
      )}
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
  const navigate = useNavigate()
  const [aberto, setAberto] = useState<Record<string, boolean>>({})
  const { data, isLoading } = useQuery({
    queryKey: ['fluxo-caixa'],
    queryFn: () => financeiroApi.fluxoCaixa(),
  })

  if (isLoading) return <p className={styles.empty}>Carregando…</p>
  if (!data) return <p className={styles.empty}>Sem dados.</p>

  const totalEntradas = data.meses.reduce((s, m) => s + m.total, 0)
  const totalSaidas = data.meses.reduce((s, m) => s + (m.total_saidas || 0), 0)
  const saldoTotal = totalEntradas - totalSaidas
  const mesCorrente = new Date().toISOString().slice(0, 7)

  return (
    <div>
      {/* Cards resumo */}
      <div className={cs.summaryGrid} style={{ marginBottom: 20 }}>
        <div className={cs.summaryCard}>
          <div className={cs.summaryLabel}>Entradas (caixa)</div>
          <div className={cs.summaryValue} style={{ color: '#15803d' }}>{fmtVal(totalEntradas)}</div>
        </div>
        <div className={cs.summaryCard}>
          <div className={cs.summaryLabel}>Saídas (despesas)</div>
          <div className={cs.summaryValue} style={{ color: '#b91c1c' }}>{fmtVal(totalSaidas)}</div>
        </div>
        <div className={cs.summaryCard}>
          <div className={cs.summaryLabel}>Saldo (entradas − saídas)</div>
          <div className={cs.summaryValue} style={{ color: saldoTotal >= 0 ? '#15803d' : '#b91c1c' }}>{fmtVal(saldoTotal)}</div>
        </div>
        <div className={cs.summaryCard}>
          <div className={cs.summaryLabel}>Crédito a receber</div>
          <div className={cs.summaryValue} style={{ color: '#b45309' }}>{fmtVal(data.credito_a_receber.total)}</div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
            Honorários {fmtVal(data.credito_a_receber.honorarios_pendentes)} · NFs não pagas {fmtVal(data.credito_a_receber.nfs_nao_pagas)}
          </div>
        </div>
      </div>

      {/* Movimento por mês (entradas − saídas) */}
      <div className={cs.sectionTitle} style={{ marginBottom: 10 }}>Movimento por mês</div>
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
                      {m.entradas.length} entrada(s) · {m.saidas.length} saída(s)
                    </span>
                  </span>
                  <span style={{ display: 'flex', gap: 14, alignItems: 'baseline', fontSize: 13 }}>
                    <span style={{ color: '#15803d' }}>+{fmtVal(m.total)}</span>
                    <span style={{ color: '#b91c1c' }}>−{fmtVal(m.total_saidas)}</span>
                    <span style={{ fontWeight: 700, color: m.saldo >= 0 ? '#15803d' : '#b91c1c' }}>
                      = {fmtVal(m.saldo)}
                    </span>
                  </span>
                </div>
                {isAberto && (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <tbody>
                      {m.entradas.map((e, i) => {
                        const irNf = e.nf_id ? () => navigate(`/fiscal?nf=${e.nf_id}`) : undefined
                        return (
                        <tr key={i} style={{ borderTop: '1px solid #f3f4f6', cursor: irNf ? 'pointer' : 'default' }}
                          onClick={irNf}
                          title={irNf ? 'Abrir a NF' : undefined}>
                          <td style={{ padding: '8px 16px', color: '#6b7280', whiteSpace: 'nowrap', width: 90 }}>{fmtData(e.data)}</td>
                          <td style={{ padding: '8px 8px' }}>
                            <div style={{ fontWeight: 600 }}>
                              {e.cliente}
                              {e.nf_conciliada && (
                                <span title={`Conciliada com NF ${e.nf_conciliada}${e.nf_tomador ? ' — ' + e.nf_tomador : ''} (clique para abrir)`}
                                  style={{ marginLeft: 6, fontSize: 10, background: '#dcfce7', color: '#15803d', padding: '1px 6px', borderRadius: 999, fontWeight: 700 }}>
                                  🧾 NF {e.nf_conciliada} ✓
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: 11, color: '#6b7280' }}>{e.descricao}</div>
                          </td>
                          <td style={{ padding: '8px 8px', textAlign: 'center' }}>
                            {e.origem === 'nf_so' ? (
                              <span title="NF paga sem entrada de caixa conciliada — clique para abrir e conciliar"
                                style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, fontWeight: 700, background: '#fef3c7', color: '#b45309' }}>
                                só NF · a conciliar
                              </span>
                            ) : (
                              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, fontWeight: 700, background: '#f0fdf4', color: '#15803d' }}>
                                {e.forma.toUpperCase()}
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 700, color: e.origem === 'nf_so' ? '#b45309' : '#065f46', whiteSpace: 'nowrap' }}>
                            {fmtVal(e.valor)}
                          </td>
                        </tr>
                        )
                      })}
                      {m.saidas.length > 0 && (
                        <tr style={{ borderTop: '1px solid #e5e7eb', background: '#fef2f2' }}>
                          <td colSpan={4} style={{ padding: '6px 16px', fontSize: 11, fontWeight: 700, color: '#b91c1c' }}>
                            Saídas (despesas que saíram do caixa)
                          </td>
                        </tr>
                      )}
                      {m.saidas.map((s, i) => (
                        <tr key={`s${i}`} style={{ borderTop: '1px solid #f3f4f6' }}>
                          <td style={{ padding: '8px 16px', color: '#6b7280', whiteSpace: 'nowrap', width: 90 }}>{fmtData(s.data)}</td>
                          <td style={{ padding: '8px 8px' }}>
                            <div style={{ fontWeight: 600 }}>
                              {s.fornecedor}
                              {s.eh_reembolso && (
                                <span title="Adiantamento reembolsável — o cliente devolve depois"
                                  style={{ marginLeft: 6, fontSize: 10, background: '#e0e7ff', color: '#3730a3', padding: '1px 6px', borderRadius: 999, fontWeight: 700 }}>
                                  reembolso
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: 11, color: '#6b7280' }}>{s.descricao}</div>
                          </td>
                          <td style={{ padding: '8px 8px', textAlign: 'center' }}>
                            <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, fontWeight: 700, background: '#fef2f2', color: '#b91c1c' }}>
                              {s.categoria}
                            </span>
                          </td>
                          <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 700, color: '#b91c1c', whiteSpace: 'nowrap' }}>
                            −{fmtVal(s.valor)}
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
              <tr key={i} style={{ borderTop: '1px solid #f3f4f6', cursor: it.nf_id ? 'pointer' : 'default' }}
                onClick={it.nf_id ? () => navigate(`/fiscal?nf=${it.nf_id}`) : undefined}
                title={it.nf_id ? 'Abrir a NF' : undefined}>
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
