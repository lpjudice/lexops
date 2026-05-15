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
    mutationFn: (id: string) => reembolsosApi.atualizar(id, { status: 'pago' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
  })

  const cancelar = useMutation({
    mutationFn: (id: string) => reembolsosApi.cancelar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reembolsos'] }),
    onError: (e: any) => alert(`Erro ao cancelar: ${e?.response?.data?.detail || e?.message}`),
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
        <div className={cs.lista}>
          {reembolsos.map((r) => (
            <div key={r.id} className={`${cs.card} ${r.status === 'cancelado' ? cs.cardCancelado : ''}`}>
              {/* Cabeçalho */}
              <div className={cs.cardTop}>
                <div>
                  <div className={cs.cardTitulo}>{r.titulo}</div>
                  <div className={cs.cardMeta}>
                    {clienteNome(r.cliente_id)} · Emissão {fmtData(r.data_emissao)}
                    {r.data_vencimento && ` · Vence ${fmtData(r.data_vencimento)}`}
                  </div>
                </div>
                <div className={cs.cardActions}>
                  <span className={cs.cardTotal}>{fmtValor(r.total)}</span>
                  <span className={`${cs.statusBadge} ${cs[`status_${r.status}`]}`}>
                    {STATUS_LABEL[r.status]}
                  </span>
                  <button
                    className={cs.btnExpand}
                    onClick={() => setExpandido(expandido === r.id ? null : r.id)}
                  >
                    {expandido === r.id ? '▲' : '▼'}
                  </button>
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
                </div>
              </div>

              {expandido === r.id && (
                <div className={cs.cardBody}>
                  {/* Tabela de itens */}
                  <div>
                    <div className={cs.sectionTitle}>Despesas</div>
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
                                  <span style={{ color: '#15803d', fontSize: 12 }} title={it.documento_comprobatorio || it.comprovante_path}>
                                    ✓ Anexado{it.documento_comprobatorio ? ` (${it.documento_comprobatorio})` : ''}
                                  </span>
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
                          onClick={() => { if (confirm('Marcar como pago?')) marcarPago.mutate(r.id) }}
                        >
                          ✓ Marcar como Pago
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
                    </div>

                    {/* Enviar por e-mail */}
                    {r.itens.length > 0 && r.status !== 'cancelado' && (
                      <div className={cs.emailRow}>
                        <input
                          className={styles.input}
                          type="email"
                          placeholder="E-mail do destinatário"
                          value={emailMap[r.id] ?? (clientes.find((c) => c.id === r.cliente_id)?.email ?? '')}
                          onChange={(e) => setEmailMap({ ...emailMap, [r.id]: e.target.value })}
                        />
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#475569' }}>
                          <input
                            type="checkbox"
                            checked={Boolean(copiarUsuarioMap[r.id])}
                            disabled={!emailUsuario}
                            onChange={(e) => setCopiarUsuarioMap({ ...copiarUsuarioMap, [r.id]: e.target.checked })}
                          />
                          Me enviar cópia oculta{emailUsuario ? ` (${emailUsuario})` : ''}
                        </label>
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
                          ✉ Enviar por E-mail
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
