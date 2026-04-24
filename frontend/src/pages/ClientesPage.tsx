import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { clientesApi } from '../api/clientes'
import type { ClienteCreate } from '../api/clientes'
import styles from './Page.module.css'
import cs from './ClientesPage.module.css'

const EMPTY: ClienteCreate = { nome: '', tipo: 'PF', cpf_cnpj: '', email: '', telefone: '', observacoes: '' }

function maskCPF(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 11)
  if (d.length <= 3) return d
  if (d.length <= 6) return `${d.slice(0,3)}.${d.slice(3)}`
  if (d.length <= 9) return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6)}`
  return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9)}`
}

function maskCNPJ(v: string) {
  // CNPJ pode ser alfanumérico (nova regra 2026), mas mantemos a formatação posicional
  const d = v.replace(/[^a-zA-Z0-9]/g, '').slice(0, 14).toUpperCase()
  if (d.length <= 2) return d
  if (d.length <= 5) return `${d.slice(0,2)}.${d.slice(2)}`
  if (d.length <= 8) return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5)}`
  if (d.length <= 12) return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8)}`
  return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}`
}

function maskTelefone(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 11)
  if (d.length <= 2) return d.length ? `(${d}` : ''
  if (d.length <= 6) return `(${d.slice(0,2)}) ${d.slice(2)}`
  if (d.length <= 10) return `(${d.slice(0,2)}) ${d.slice(2,6)}-${d.slice(6)}`
  return `(${d.slice(0,2)}) ${d.slice(2,7)}-${d.slice(7)}`
}

function applyDocMask(v: string, tipo: 'PF' | 'PJ') {
  return tipo === 'PF' ? maskCPF(v) : maskCNPJ(v)
}

export default function ClientesPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ClienteCreate>(EMPTY)
  const [editando, setEditando] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Partial<ClienteCreate>>({})
  const [busca, setBusca] = useState('')

  const { data: clientes = [], isLoading } = useQuery({
    queryKey: ['clientes'],
    queryFn: clientesApi.listar,
  })

  const clientesFiltrados = clientes.filter((c) => {
    if (!busca.trim()) return true
    const q = busca.toLowerCase()
    return (
      c.nome.toLowerCase().includes(q) ||
      (c.email?.toLowerCase().includes(q) ?? false)
    )
  })

  const criar = useMutation({
    mutationFn: clientesApi.criar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clientes'] })
      setShowForm(false)
      setForm(EMPTY)
    },
  })

  const criarErro = criar.error
    ? ((criar.error as any)?.response?.data?.detail ?? 'Erro ao salvar. Verifique os dados e tente novamente.')
    : null

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ClienteCreate> }) =>
      clientesApi.atualizar(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clientes'] })
      setEditando(null)
    },
  })

  const deletar = useMutation({
    mutationFn: (id: string) => clientesApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clientes'] }),
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Clientes</h1>
        <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Novo Cliente'}
        </button>
      </div>

      <div className={cs.buscaRow}>
        <input
          className={cs.buscaInput}
          placeholder="Buscar por nome ou email..."
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        {busca && (
          <button className={cs.buscaLimpar} onClick={() => setBusca('')}>×</button>
        )}
      </div>

      {showForm && (
        <form onSubmit={(e) => { e.preventDefault(); criar.mutate(form) }} className={styles.form}>
          <ClienteFormFields
            form={form}
            onChange={(f) => { criar.reset(); setForm(f) }}
          />
          {criarErro && (
            <p style={{ color: '#b91c1c', fontSize: 13, margin: '4px 0' }}>
              ⚠ {String(criarErro)}
            </p>
          )}
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : clientes.length === 0 ? (
        <p className={styles.empty}>Nenhum cliente cadastrado.</p>
      ) : clientesFiltrados.length === 0 ? (
        <p className={styles.empty}>Nenhum cliente encontrado para "{busca}".</p>
      ) : (
        <div className={cs.lista}>
          {clientesFiltrados.map((c) => (
            <div key={c.id} className={cs.card}>
              <div className={cs.cardRow}>
                <div className={cs.cardInfo}>
                  <span className={cs.nome}>{c.nome}</span>
                  <span className={styles.badge}>{c.tipo}</span>
                  {c.incompleto && <span className={cs.incompleto}>Incompleto</span>}
                  {c.email && <span className={cs.meta}>✉ {c.email}</span>}
                  {c.telefone && <span className={cs.meta}>☏ {c.telefone}</span>}
                </div>
                <div className={cs.cardActions}>
                  <Link to={`/clientes/${c.id}`} className={styles.btnTable}>Ver</Link>
                  <button className={styles.btnTable}
                    onClick={() => {
                      setEditando(editando === c.id ? null : c.id)
                      setEditForm({ nome: c.nome, tipo: c.tipo, cpf_cnpj: c.cpf_cnpj, email: c.email, telefone: c.telefone, observacoes: c.observacoes })
                    }}>
                    {editando === c.id ? 'Cancelar' : 'Editar'}
                  </button>
                  <button className={styles.btnDanger}
                    onClick={() => { if (confirm(`Remover ${c.nome}?`)) deletar.mutate(c.id) }}>
                    ×
                  </button>
                </div>
              </div>

              {editando === c.id && (
                <div className={cs.editPanel}>
                  <ClienteFormFields
                    form={editForm as ClienteCreate}
                    onChange={(f) => setEditForm(f)}
                  />
                  <button className={styles.btnPrimary} disabled={atualizar.isPending}
                    onClick={() => atualizar.mutate({ id: c.id, data: { ...editForm, incompleto: false } })}>
                    {atualizar.isPending ? 'Salvando...' : 'Salvar alterações'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ClienteFormFields({ form, onChange }: { form: ClienteCreate; onChange: (f: ClienteCreate) => void }) {
  return (
    <>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Nome *</label>
        <input className={styles.input} value={form.nome ?? ''}
          onChange={(e) => onChange({ ...form, nome: e.target.value })} required />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Tipo *</label>
        <select className={styles.input} value={form.tipo}
          onChange={(e) => onChange({ ...form, tipo: e.target.value as 'PF' | 'PJ', cpf_cnpj: '' })}>
          <option value="PF">Pessoa Física</option>
          <option value="PJ">Pessoa Jurídica</option>
        </select>
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>{form.tipo === 'PF' ? 'CPF' : 'CNPJ'}</label>
        <input className={styles.input}
          placeholder={form.tipo === 'PF' ? '000.000.000-00' : '00.000.000/0000-00'}
          value={form.cpf_cnpj ?? ''}
          onChange={(e) => onChange({ ...form, cpf_cnpj: applyDocMask(e.target.value, form.tipo) })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Email</label>
        <input type="email" className={styles.input} value={form.email ?? ''}
          onChange={(e) => onChange({ ...form, email: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Telefone</label>
        <input className={styles.input} placeholder="(00) 0.0000-0000"
          value={form.telefone ?? ''}
          onChange={(e) => onChange({ ...form, telefone: maskTelefone(e.target.value) })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Observações</label>
        <textarea className={styles.input} rows={2} value={form.observacoes ?? ''}
          onChange={(e) => onChange({ ...form, observacoes: e.target.value })} />
      </div>
    </>
  )
}
