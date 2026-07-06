import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reembolsosApi } from '../api/reembolsos'
import type { ItemReembolso, ReembolsoCreate, ItemReembolsoCreate, StatusReembolso } from '../api/reembolsos'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import CurrencyInput from '../components/CurrencyInput'
import ComboBox from '../components/ComboBox'
import { useAuth } from '../contexts/AuthContext'
import styles from './Page.module.css'
import cs from './ReembolsosPage.module.css'

const STATUS_LABEL: Record<StatusReembolso, string> = {
  rascunho: 'Rascunho',
  aguardando_pagamento: 'Ag. Pagamento',
  enviado: 'Enviado',
  pago: 'Pago',
  cancelado: 'Cancelado',
}

type FiltroReembolso = 'abertos' | 'pagos' | 'cancelados' | 'todos'
type OrdenacaoReembolso =
  | 'criado_recente'
  | 'criado_antigo'
  | 'vencimento_proximo'
  | 'vencimento_distante'
  | 'valor_maior'
  | 'valor_menor'

const NATUREZAS = [
  'Custas judiciais', 'Honorários periciais', 'Transporte', 'Hospedagem',
  'Alimentação', 'Correios/Cartório', 'Diligências', 'Outro',
]

const EMPTY_FORM: ReembolsoCreate = {
  cliente_id: '', titulo: '', data_emissao: new Date().toISOString().slice(0, 10),
}
const EMPTY_ITEM: ItemReembolsoCreate = {
  data: new Date().toISOString().slice(0, 10),
  descricao: '', natureza: 'Outro', valor: 0,
}

function fmtValor(v: number) {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function fmtData(d: string) {
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}
function podeEditarDespesas(status: StatusReembolso) {
  return status === 'rascunho' || status === 'aguardando_pagamento' || status === 'enviado'
}
function isAberto(status: StatusReembolso) {
  return status !== 'pago' && status !== 'cancelado'
}
function timeValue(value?: string | null, fallback = Number.MAX_SAFE_INTEGER) {
  if (!value) return fallback
  const parsed = new Date(value).getTime()
  return Number.isNaN(parsed) ? fallback : parsed
}

export default function ReembolsosPage() {
  const qc = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const { usuario } = useAuth()

  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ReembolsoCreate>(EMPTY_FORM)
  const [expandido, setExpandido] = useState<string | null>(null)
  const [itemForm, setItemForm] = useState<ItemReembolsoCreate>(EMPTY_ITEM)
  const [itemFile, setItemFile] = useState<File | null>(null)
  const [emailMap, setEmailMap] = useState<Record<string, string>>({})
  const [copiarUsuarioMap, setCopiarUsuarioMap] = useState<Record<string, boolean>>({})
  const [editandoItem, setEditandoItem] = useState<{ itemId: string; valor: number; natureza: string } | null>(null)
  const [filtro, setFiltro] = useState<FiltroReembolso>('abertos')
  const [ordenacao, setOrdenacao] = useState<OrdenacaoReembolso>('criado_recente')
  // Track which reembolso id has a pending cancel+dup action
  const [cancelDupPending, setCancelDupPending] = useState<string | null>(null)

  const { data: reembolsos = [], isLoading } = useQuery({
    queryKey: ['reembolsos'],
    queryFn: () => reembolsosApi.listar(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })
  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })

  const criar = useMutation({
    mutationFn: reembolsosApi.criar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reembolsos'] })
      setShowForm(false)
      setForm(EMPTY_FORM)
    },
  })

  const deletar = useMutation({
    mutationFn: reembolsosApi.deletar,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
  })

  const adicionarItem = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ItemReembolsoCreate }) =>
      reembolsosApi.adicionarItem(id, data),
    onSuccess: async (novoItem, vars) => {
      // If file was selected, upload it immediately
      if (itemFile) {
        try {
          await reembolsosApi.uploadComprovante(vars.id, novoItem.id, itemFile)
        } catch { /* best-effort */ }
        setItemFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
      }
      qc.invalidateQueries({ queryKey: ['reembolsos'] })
      setItemForm(EMPTY_ITEM)
    },
  })

  const removerItem = useMutation({
    mutationFn: ({ rid, iid }: { rid: string; iid: string }) =>
      reembolsosApi.removerItem(rid, iid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
  })

  const editarItemValor = useMutation({
    mutationFn: ({ rid, iid, data }: { rid: string; iid: string; data: Partial<ItemReembolsoCreate> }) =>
      reembolsosApi.atualizarItem(rid, iid, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reembolsos'] })
      setEditandoItem(null)
    },
  })

  const uploadComprovante = useMutation({
    mutationFn: ({ rid, iid, file }: { rid: string; iid: string; file: File }) =>
      reembolsosApi.uploadComprovante(rid, iid, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
  })

  const removerComprovante = useMutation({
    mutationFn: ({ rid, iid }: { rid: string; iid: string }) =>
      reembolsosApi.removerComprovante(rid, iid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
  })

  const gerarPdf = useMutation({
    mutationFn: (id: string) => reembolsosApi.gerarPdf(id),
    onSuccess: (blob, id) => {
      const r = reembolsos.find((x) => x.id === id)
      const nome = r ? r.titulo : 'nota'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Nota de Reembolso - ${nome}.pdf`
      a.click()
      URL.revokeObjectURL(url)
      qc.invalidateQueries({ queryKey: ['reembolsos'] })
    },
  })

  const enviarEmail = useMutation({
    mutationFn: ({ id, dest, copiarUsuario }: { id: string; dest: string; copiarUsuario: boolean }) =>
      reembolsosApi.enviarEmail(id, dest, copiarUsuario),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
    onError: (e: any) => alert(`Erro ao enviar: ${e?.response?.data?.detail || e?.message}`),
  })

  const marcarPago = useMutation({
    mutationFn: (id: string) => reembolsosApi.marcarPago(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
    onError: (e: any) => alert(`Erro ao marcar como pago: ${e?.response?.data?.detail || e?.message}`),
  })

  const reverterPagamento = useMutation({
    mutationFn: (id: string) => reembolsosApi.reverterPagamento(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
    onError: (e: any) => alert(`Erro ao reverter quitação: ${e?.response?.data?.detail || e?.message}`),
  })

  const restaurar = useMutation({
    mutationFn: (id: string) => reembolsosApi.atualizar(id, { status: 'rascunho' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
  })

  const cancelar = useMutation({
    mutationFn: (id: string) => reembolsosApi.cancelar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
    onError: (e: any) => alert(`Erro ao cancelar: ${e?.response?.data?.detail || e?.message}`),
  })

  const togglePerda = useMutation({
    mutationFn: ({ id, valor }: { id: string; valor: boolean }) =>
      reembolsosApi.atualizar(id, { tratar_como_perda: valor }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
    onError: (e: any) => alert(`Erro: ${e?.response?.data?.detail || e?.message}`),
  })

  const handleCancelarEDuplicar = async (id: string) => {
    if (!confirm('Cancelar esta nota e criar uma cópia em rascunho?')) return
    setCancelDupPending(id)
    try {
      await reembolsosApi.cancelar(id)
      await reembolsosApi.duplicar(id)
      qc.invalidateQueries({ queryKey: ['reembolsos'] })
    } catch (e: any) {
      alert(`Erro: ${e?.response?.data?.detail || e?.message}`)
    } finally {
      setCancelDupPending(null)
    }
  }

  const clienteNome = (id: string) => clientes.find((c) => c.id === id)?.nome ?? '—'
  const emailUsuario = usuario?.google_email || usuario?.email || ''
  const reembolsosAbertos = reembolsos.filter((r) => isAberto(r.status))
  const totalAberto = reembolsosAbertos.reduce((sum, r) => sum + r.total, 0)
  const filtros: Array<{ value: FiltroReembolso; label: string; count: number }> = [
    { value: 'abertos', label: 'Em aberto', count: reembolsosAbertos.length },
    { value: 'pagos', label: 'Pagos', count: reembolsos.filter((r) => r.status === 'pago').length },
    { value: 'cancelados', label: 'Cancelados', count: reembolsos.filter((r) => r.status === 'cancelado').length },
    { value: 'todos', label: 'Todos', count: reembolsos.length },
  ]
  const reembolsosVisiveis = reembolsos
    .filter((r) => {
      if (filtro === 'abertos') return isAberto(r.status)
      if (filtro === 'pagos') return r.status === 'pago'
      if (filtro === 'cancelados') return r.status === 'cancelado'
      return true
    })
    .sort((a, b) => {
      if (ordenacao === 'criado_antigo') return timeValue(a.created_at, 0) - timeValue(b.created_at, 0)
      if (ordenacao === 'vencimento_proximo') return timeValue(a.data_vencimento) - timeValue(b.data_vencimento)
      if (ordenacao === 'vencimento_distante') return timeValue(b.data_vencimento, 0) - timeValue(a.data_vencimento, 0)
      if (ordenacao === 'valor_maior') return b.total - a.total
      if (ordenacao === 'valor_menor') return a.total - b.total
      return timeValue(b.created_at, 0) - timeValue(a.created_at, 0)
    })

  const iniciarEdicaoItem = (item: ItemReembolso) => {
    setEditandoItem({ itemId: item.id, valor: item.valor, natureza: item.natureza })
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Reembolsos</h1>
        <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Novo Reembolso'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); criar.mutate(form) }}
          className={styles.form}
        >
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Título / Referência *</label>
            <input
              className={styles.input}
              placeholder="Ex: Reembolso Pereira Faria - Mar2026"
              value={form.titulo}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Cliente *</label>
            <ComboBox
              options={clientes.map((c) => ({ value: c.id, label: c.nome }))}
              value={form.cliente_id}
              onChange={(v) => setForm({ ...form, cliente_id: v })}
              placeholder="Buscar cliente..."
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Processo (opcional)</label>
            <ComboBox
              options={processos.map((p) => {
                const cl = clientes.find((c) => c.id === p.cliente_id)
                return { value: p.id, label: p.numero_cnj, sublabel: cl ? `Cliente: ${cl.nome}` : undefined }
              })}
              value={form.processo_id ?? ''}
              onChange={(v) => setForm({ ...form, processo_id: v || undefined })}
              placeholder="Buscar por CNJ ou cliente..."
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data de Emissão *</label>
            <input
              type="date"
              className={styles.input}
              value={form.data_emissao}
              onChange={(e) => setForm({ ...form, data_emissao: e.target.value })}
              required
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
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : reembolsos.length === 0 ? (
        <p className={styles.empty}>Nenhum reembolso cadastrado.</p>
      ) : (
        <>
          <div className={cs.listControls}>
            <div className={cs.openSummary}>
              <span className={cs.summaryLabel}>Total em aberto</span>
              <strong>{fmtValor(totalAberto)}</strong>
              <span>{reembolsosAbertos.length} nota{reembolsosAbertos.length === 1 ? '' : 's'} não paga{reembolsosAbertos.length === 1 ? '' : 's'}</span>
            </div>
            <div className={cs.filtersArea}>
              <div className={cs.filterChips} aria-label="Filtrar reembolsos">
                {filtros.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={`${cs.filterChip} ${filtro === item.value ? cs.filterChipActive : ''}`}
                    onClick={() => setFiltro(item.value)}
                  >
                    {item.label}
                    <span>{item.count}</span>
                  </button>
                ))}
              </div>
              <label className={cs.sortControl}>
                <span>Ordenar</span>
                <select
                  className={styles.input}
                  value={ordenacao}
                  onChange={(e) => setOrdenacao(e.target.value as OrdenacaoReembolso)}
                >
                  <option value="criado_recente">Criação: mais recente</option>
                  <option value="criado_antigo">Criação: mais antiga</option>
                  <option value="vencimento_proximo">Vencimento: próximo</option>
                  <option value="vencimento_distante">Vencimento: distante</option>
                  <option value="valor_maior">Valor: maior primeiro</option>
                  <option value="valor_menor">Valor: menor primeiro</option>
                </select>
              </label>
            </div>
          </div>

          {reembolsosVisiveis.length === 0 ? (
            <p className={styles.empty}>Nenhum reembolso neste filtro.</p>
          ) : (
            <div className={cs.lista}>
              {reembolsosVisiveis.map((r) => (
            <div key={r.id} className={`${cs.card} ${r.status === 'cancelado' ? cs.cardCancelado : ''}`}>
              {/* Cabeçalho */}
              <div className={cs.cardTop}>
                <div>
                  <div className={cs.cardTitulo}>{r.titulo}</div>
                  <div className={cs.cardMeta}>
                    {clienteNome(r.cliente_id)} · Emissão {fmtData(r.data_emissao)}
                    {r.data_vencimento && ` · Vence ${fmtData(r.data_vencimento)}`}
                    {r.ultimo_lembrete_em && (
                      <span title={r.email_destinatario ? `Enviado para ${r.email_destinatario}` : undefined}>
                        {' · '}📧 Cobrança enviada {fmtData(r.ultimo_lembrete_em.slice(0, 10))}
                      </span>
                    )}
                  </div>
                </div>
                <div className={cs.cardActions}>
                  <span className={cs.cardTotal}>{fmtValor(r.total)}</span>
                  <span className={`${cs.statusBadge} ${cs[`status_${r.status}`]}`}>
                    {STATUS_LABEL[r.status]}
                  </span>
                  {r.tratar_como_perda && (
                    <span style={{ fontSize: 10, background: '#fee2e2', color: '#b91c1c', padding: '2px 8px', borderRadius: 999, fontWeight: 700, letterSpacing: '.04em' }}>
                      PERDA
                    </span>
                  )}
                  <button
                    className={cs.btnExpand}
                    onClick={() => setExpandido(expandido === r.id ? null : r.id)}
                  >
                    {expandido === r.id ? '▲' : '▼'}
                  </button>
                  {r.status !== 'cancelado' && (
                    <button
                      className={styles.btnDanger}
                      onClick={() => {
                        if (confirm('Remover reembolso? Isso também apagará a pasta correspondente no Drive.')) {
                          deletar.mutate(r.id)
                        }
                      }}
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>

              {expandido === r.id && (
                <div className={cs.cardBody}>
                  {/* Link Drive no topo — ajuste 2 */}
                  {r.drive_link && (
                    <div style={{ marginBottom: 12 }}>
                      <a
                        href={r.drive_link}
                        target="_blank"
                        rel="noreferrer"
                        style={{ fontSize: 13, color: '#2563eb', textDecoration: 'underline' }}
                      >
                        ☁ Abrir pasta no Drive
                      </a>
                    </div>
                  )}
                  {/* Tabela de itens */}
                  <div>
                    <div className={cs.sectionTitle}>Despesas</div>
                    <div className={cs.tableScroll}>
                      <table className={cs.itensTable}>
                        <thead>
                          <tr>
                            <th>Data</th>
                            <th>Descrição</th>
                            <th>Natureza</th>
                            <th>Comprovante</th>
                            <th style={{ textAlign: 'right' }}>Valor</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {r.itens.map((it) => (
                            <tr key={it.id}>
                              <td>{fmtData(it.data)}</td>
                              <td>{it.descricao}</td>
                              <td>
                                {podeEditarDespesas(r.status) ? (
                                  <select
                                    className={styles.input}
                                    value={editandoItem?.itemId === it.id ? editandoItem.natureza : it.natureza}
                                    disabled={editarItemValor.isPending}
                                    onChange={(e) => {
                                      const natureza = e.target.value
                                      if (editandoItem?.itemId === it.id) setEditandoItem({ ...editandoItem, natureza })
                                      editarItemValor.mutate({ rid: r.id, iid: it.id, data: { natureza } })
                                    }}
                                  >
                                    {NATUREZAS.map((n) => <option key={n} value={n}>{n}</option>)}
                                  </select>
                                ) : (
                                  <span>{it.natureza}</span>
                                )}
                              </td>
                              <td>
                                {it.comprovante_path ? (
                                  <span className={cs.comprovanteLine}>
                                    {it.comprovante_drive_link ? (
                                      <a
                                        href={it.comprovante_drive_link}
                                        target="_blank"
                                        rel="noreferrer"
                                        style={{ color: '#15803d', fontSize: 12, textDecoration: 'underline' }}
                                        title="Abrir no Drive"
                                      >
                                        ✓ {it.documento_comprobatorio || 'Comprovante'}
                                      </a>
                                    ) : (
                                      <span style={{ color: '#15803d', fontSize: 12 }} title={it.documento_comprobatorio || it.comprovante_path}>
                                        ✓ {it.documento_comprobatorio || 'Comprovante'}
                                      </span>
                                    )}
                                    {podeEditarDespesas(r.status) && (
                                      <button
                                        className={cs.btnRemoveComprovante}
                                        title="Remover comprovante"
                                        onClick={() => {
                                          if (confirm('Remover comprovante?'))
                                            removerComprovante.mutate({ rid: r.id, iid: it.id })
                                        }}
                                      >×</button>
                                    )}
                                  </span>
                                ) : (
                                  <label className={cs.btnAnexar} title="Anexar comprovante">
                                    📎 Anexar
                                    <input
                                      type="file"
                                      style={{ display: 'none' }}
                                      accept="image/*,.pdf"
                                      onChange={(e) => {
                                        const f = e.target.files?.[0]
                                        if (f) uploadComprovante.mutate({ rid: r.id, iid: it.id, file: f })
                                      }}
                                    />
                                  </label>
                                )}
                              </td>
                              <td className={cs.tdValor}>
                                {podeEditarDespesas(r.status) && editandoItem?.itemId === it.id ? (
                                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                                    <CurrencyInput
                                      className={styles.input}
                                      value={editandoItem.valor}
                                      onChange={(valor) => setEditandoItem({ ...editandoItem, valor })}
                                      placeholder="0,00"
                                    />
                                  </div>
                                ) : (
                                  <span
                                    style={{ cursor: podeEditarDespesas(r.status) ? 'pointer' : undefined }}
                                    title={podeEditarDespesas(r.status) ? 'Clique para editar' : undefined}
                                    onClick={() => {
                                      if (podeEditarDespesas(r.status)) {
                                        iniciarEdicaoItem(it)
                                      }
                                    }}
                                  >
                                    {fmtValor(it.valor)}{podeEditarDespesas(r.status) && ' ✎'}
                                  </span>
                                )}
                              </td>
                              <td>
                                {podeEditarDespesas(r.status) && (
                                  editandoItem?.itemId === it.id ? (
                                    <div style={{ display: 'flex', gap: 4 }}>
                                      <button
                                        className={styles.btnPrimary}
                                        style={{ padding: '4px 10px', fontSize: 12 }}
                                        disabled={!editandoItem.valor || editarItemValor.isPending}
                                        onClick={() => editarItemValor.mutate({
                                          rid: r.id,
                                          iid: it.id,
                                          data: { valor: editandoItem.valor, natureza: editandoItem.natureza },
                                        })}
                                      >✓</button>
                                      <button className={styles.btnDanger} onClick={() => setEditandoItem(null)}>×</button>
                                    </div>
                                  ) : (
                                    <div style={{ display: 'flex', gap: 6 }}>
                                      <button
                                        className={styles.btnPrimary}
                                        style={{ padding: '4px 10px', fontSize: 12 }}
                                        onClick={() => iniciarEdicaoItem(it)}
                                      >✎</button>
                                      <button
                                        className={styles.btnDanger}
                                        onClick={() => removerItem.mutate({ rid: r.id, iid: it.id })}
                                      >×</button>
                                    </div>
                                  )
                                )}
                              </td>
                            </tr>
                          ))}
                          {r.itens.length > 0 && (
                            <tr className={cs.totalRow}>
                              <td colSpan={4} style={{ textAlign: 'right' }}>Total</td>
                              <td className={cs.tdValor}>{fmtValor(r.total)}</td>
                              <td></td>
                            </tr>
                          )}
                          {r.itens.length === 0 && (
                            <tr>
                              <td colSpan={6} style={{ color: '#9ca3af', textAlign: 'center', padding: '14px' }}>
                                Nenhuma despesa adicionada.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Formulário novo item */}
                  {r.status === 'rascunho' && (
                    <div>
                      <div className={cs.sectionTitle}>Adicionar despesa</div>
                      <div className={cs.itemForm}>
                        <input
                          type="date"
                          className={styles.input}
                          value={itemForm.data}
                          onChange={(e) => setItemForm({ ...itemForm, data: e.target.value })}
                        />
                        <input
                          className={styles.input}
                          placeholder="Descrição"
                          value={itemForm.descricao}
                          onChange={(e) => setItemForm({ ...itemForm, descricao: e.target.value })}
                        />
                        <select
                          className={styles.input}
                          value={itemForm.natureza}
                          onChange={(e) => setItemForm({ ...itemForm, natureza: e.target.value })}
                        >
                          {NATUREZAS.map((n) => <option key={n} value={n}>{n}</option>)}
                        </select>
                        <CurrencyInput
                          className={`${styles.input} ${cs.inputValor}`}
                          value={itemForm.valor}
                          onChange={(v) => setItemForm({ ...itemForm, valor: v })}
                          placeholder="Valor (R$)"
                        />
                        {/* File picker replacing the old text "Documento" field */}
                        <label className={cs.filePickerLabel} title={itemFile ? itemFile.name : 'Anexar comprovante (PDF, imagem)'}>
                          📎 {itemFile ? itemFile.name.slice(0, 18) + (itemFile.name.length > 18 ? '…' : '') : 'Comprovante'}
                          <input
                            ref={fileInputRef}
                            type="file"
                            style={{ display: 'none' }}
                            accept="image/*,.pdf"
                            onChange={(e) => setItemFile(e.target.files?.[0] ?? null)}
                          />
                        </label>
                        <button
                          className={styles.btnPrimary}
                          disabled={!itemForm.descricao || !itemForm.valor || adicionarItem.isPending}
                          onClick={() => adicionarItem.mutate({ id: r.id, data: itemForm })}
                        >
                          + Adicionar
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Ações */}
                  <div>
                    <div className={cs.sectionTitle}>Ações</div>

                    {/* Tratar como perda — só no rascunho. Vira despesa/perda real no Backoffice. */}
                    {r.status === 'rascunho' && (
                      <div style={{ marginBottom: 12, padding: '10px 12px', background: r.tratar_como_perda ? '#fef2f2' : '#f9fafb', border: `1px solid ${r.tratar_como_perda ? '#fecaca' : '#e5e7eb'}`, borderRadius: 8 }}>
                        <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer', fontSize: 13 }}>
                          <input
                            type="checkbox"
                            checked={!!r.tratar_como_perda}
                            disabled={togglePerda.isPending}
                            onChange={(e) => togglePerda.mutate({ id: r.id, valor: e.target.checked })}
                            style={{ marginTop: 2 }}
                          />
                          <span>
                            <strong>Tratar como perda</strong> — o cliente não vai reembolsar; este adiantamento
                            vira <strong>despesa/perda do escritório</strong> nos lançamentos do Backoffice (gera crédito IBS/CBS se houver documento).
                            <span style={{ display: 'block', color: 'var(--gray-mid)', fontSize: 11, marginTop: 2 }}>
                              Use só quando desistir de cobrar. Enquanto for ajuste ou for cobrar depois, deixe desmarcado.
                            </span>
                          </span>
                        </label>
                      </div>
                    )}

                    <div className={cs.acoes}>
                      {r.itens.length > 0 && r.status !== 'cancelado' && (
                        <button
                          className={`${styles.btnPrimary} ${cs.btnPdf}`}
                          disabled={gerarPdf.isPending && gerarPdf.variables === r.id}
                          onClick={() => gerarPdf.mutate(r.id)}
                        >
                          {gerarPdf.isPending && gerarPdf.variables === r.id
                            ? 'Gerando PDF...' : '↓ Gerar e Baixar PDF'}
                        </button>
                      )}
                      {r.drive_link && (
                        <a href={r.drive_link} target="_blank" rel="noreferrer" className={cs.btnDrive}>
                          ☁ Ver pasta no Drive
                        </a>
                      )}
                      {(r.status === 'aguardando_pagamento' || r.status === 'enviado') && (
                        <button
                          className={`${styles.btnPrimary} ${cs.btnPago}`}
                          disabled={marcarPago.isPending}
                          onClick={() => { if (confirm('Marcar como pago e enviar e-mail de quitação ao cliente?')) marcarPago.mutate(r.id) }}
                        >
                          ✓ Marcar como Pago
                        </button>
                      )}
                      {r.status === 'pago' && (
                        <button
                          className={cs.btnReverterPago}
                          disabled={reverterPagamento.isPending}
                          onClick={() => {
                            if (confirm('Reverter a quitação e avisar o cliente para desconsiderar o e-mail anterior?'))
                              reverterPagamento.mutate(r.id)
                          }}
                        >
                          Reverter Quitação
                        </button>
                      )}

                      {/* Cancel / Cancel+Duplicate — shown when enviado */}
                      {r.status === 'enviado' && (
                        <>
                          <button
                            className={cs.btnCancelar}
                            disabled={cancelar.isPending}
                            onClick={() => {
                              if (confirm('Cancelar esta nota de reembolso? Um e-mail será enviado ao cliente.'))
                                cancelar.mutate(r.id)
                            }}
                          >
                            ✕ Cancelar
                          </button>
                          <button
                            className={cs.btnDuplicar}
                            disabled={cancelDupPending === r.id}
                            onClick={() => handleCancelarEDuplicar(r.id)}
                          >
                            {cancelDupPending === r.id ? 'Aguarde...' : '⧉ Cancelar e Duplicar'}
                          </button>
                        </>
                      )}
                      {r.status === 'cancelado' && (
                        <>
                          <button
                            className={cs.btnRestaurar}
                            disabled={restaurar.isPending}
                            onClick={() => {
                              if (confirm('Restaurar esta nota como rascunho? Nenhum e-mail será enviado.'))
                                restaurar.mutate(r.id)
                            }}
                          >
                            Restaurar como Rascunho
                          </button>
                          <button
                            className={cs.btnExcluirCancelado}
                            disabled={deletar.isPending}
                            onClick={() => {
                              if (confirm('Excluir definitivamente este reembolso cancelado? Isso também apagará a pasta correspondente no Drive.'))
                                deletar.mutate(r.id)
                            }}
                          >
                            Excluir Definitivamente
                          </button>
                        </>
                      )}
                    </div>

                    {/* Enviar por e-mail — ajuste 3: layout vertical, sem ambiguidade */}
                    {r.itens.length > 0 && r.status !== 'cancelado' && (
                      <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: '#374151' }}>Enviar por e-mail</div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                          <input
                            className={styles.input}
                            type="email"
                            placeholder="E-mail do cliente (destinatário)"
                            style={{ flex: '1 1 220px', minWidth: 0 }}
                            value={emailMap[r.id] ?? (clientes.find((c) => c.id === r.cliente_id)?.email ?? '')}
                            onChange={(e) => setEmailMap({ ...emailMap, [r.id]: e.target.value })}
                          />
                          <button
                            className={`${styles.btnPrimary} ${cs.btnEmail}`}
                            disabled={enviarEmail.isPending || (!emailMap[r.id] && !clientes.find((c) => c.id === r.cliente_id)?.email)}
                            onClick={() => {
                              const dest = emailMap[r.id] || clientes.find((c) => c.id === r.cliente_id)?.email || ''
                              const copiarUsuario = Boolean(copiarUsuarioMap[r.id] && emailUsuario)
                              if (dest && confirm(`Enviar nota por e-mail para ${dest}?${copiarUsuario ? ' Você também receberá uma cópia oculta.' : ''}`))
                                enviarEmail.mutate({ id: r.id, dest, copiarUsuario })
                            }}
                          >
                            ✉ Enviar
                          </button>
                        </div>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#6b7280', userSelect: 'none' }}>
                          <input
                            type="checkbox"
                            checked={Boolean(copiarUsuarioMap[r.id])}
                            disabled={!emailUsuario}
                            onChange={(e) => setCopiarUsuarioMap({ ...copiarUsuarioMap, [r.id]: e.target.checked })}
                          />
                          Enviar cópia oculta (BCC) para mim
                          {emailUsuario && <span style={{ color: '#9ca3af' }}> — {emailUsuario}</span>}
                        </label>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
