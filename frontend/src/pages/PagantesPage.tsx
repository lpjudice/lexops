import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { pagantesApi, type PaganteIn, type PaganteOut } from '../api/pagantes'
import { clientesApi, type Cliente } from '../api/clientes'
import { mascaraDocumento, soDigitos } from '../utils/documentos'

const fmtBRL = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

function fmtDoc(doc?: string) {
  if (!doc) return '—'
  const d = doc.replace(/\D/g, '')
  if (d.length === 11) return d.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4')
  if (d.length === 14) return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5')
  return doc
}

const EMPTY: PaganteIn = { nome: '' }

export default function PagantesPage() {
  const qc = useQueryClient()
  const [mostrarForm, setMostrarForm] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState<PaganteIn>(EMPTY)
  const [erro, setErro] = useState<string | null>(null)
  const [buscaCliente, setBuscaCliente] = useState('')

  const { data: pagantes = [], isLoading } = useQuery({
    queryKey: ['pagantes'],
    queryFn: () => pagantesApi.listar(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const salvar = useMutation({
    mutationFn: (b: PaganteIn) =>
      editId ? pagantesApi.atualizar(editId, b) : pagantesApi.criar(b),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pagantes'] })
      setMostrarForm(false); setForm(EMPTY); setEditId(null); setErro(null); setBuscaCliente('')
    },
    onError: (err: any) => setErro(err.response?.data?.detail || err.message || 'Erro ao salvar'),
  })
  const deletar = useMutation({
    mutationFn: (id: string) => pagantesApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pagantes'] }),
  })

  function set<K extends keyof PaganteIn>(k: K, v: PaganteIn[K]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  // Ao escolher um cliente, preenche os dados do pagante com os dados do cliente
  function escolherCliente(c: Cliente) {
    setForm({
      nome: c.nome,
      cpf_cnpj: c.cpf_cnpj || '',
      email: c.email || '',
      telefone: c.telefone || '',
      cliente_id: c.id,
      observacoes: form.observacoes,
    })
    setBuscaCliente(c.nome)
  }

  function abrirNovo() {
    setForm(EMPTY); setEditId(null); setErro(null); setBuscaCliente(''); setMostrarForm(true)
  }
  function abrirEdicao(p: PaganteOut) {
    setForm({
      nome: p.nome, cpf_cnpj: p.cpf_cnpj || '', email: p.email || '', telefone: p.telefone || '',
      logradouro: p.logradouro, numero: p.numero, complemento: p.complemento,
      bairro: p.bairro, cod_municipio: p.cod_municipio, cep: p.cep,
      cliente_id: p.cliente_id, observacoes: p.observacoes,
    })
    setEditId(p.id); setErro(null); setBuscaCliente(''); setMostrarForm(true)
  }

  const clientesFiltrados = buscaCliente
    ? clientes.filter((c) => c.nome.toLowerCase().includes(buscaCliente.toLowerCase())).slice(0, 8)
    : []

  const fmtEndereco = (p: PaganteOut) => {
    const partes = [p.logradouro, p.numero, p.bairro, p.cep].filter(Boolean)
    return partes.length ? partes.join(' · ') : '—'
  }

  if (isLoading) return <div style={{ padding: 20 }}>Carregando…</div>

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#0f766e' }}>
          Pagantes — Quem recebe NF
        </div>
        <button onClick={abrirNovo}
          style={{ background: '#0f766e', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 16px', fontWeight: 600, cursor: 'pointer' }}>
          + Cadastrar pagante
        </button>
      </div>

      {/* Formulário de cadastro/edição */}
      {mostrarForm && (
        <div style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 10, padding: 16, marginBottom: 20 }}>
          <div style={{ fontWeight: 700, marginBottom: 12, color: '#1f2937' }}>
            {editId ? 'Editar pagante' : 'Novo pagante'}
          </div>

          {/* Atalho: puxar de cliente cadastrado */}
          {!editId && (
            <div style={{ marginBottom: 14, position: 'relative' }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 4 }}>
                Puxar dados de cliente cadastrado (opcional)
              </label>
              <input
                value={buscaCliente}
                onChange={(e) => { setBuscaCliente(e.target.value); if (!e.target.value) set('cliente_id', undefined) }}
                placeholder="Buscar cliente para pré-preencher…"
                style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
              />
              {clientesFiltrados.length > 0 && !form.cliente_id && (
                <ul style={{ position: 'absolute', zIndex: 10, background: '#fff', border: '1px solid #d1d5db', borderRadius: 6, listStyle: 'none', margin: '2px 0 0', padding: 4, width: '100%', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
                  {clientesFiltrados.map((c) => (
                    <li key={c.id}
                      onClick={() => escolherCliente(c)}
                      style={{ padding: '6px 8px', cursor: 'pointer', fontSize: 13, borderRadius: 4 }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#f0fdf4')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                      <b>{c.nome}</b>
                      {c.cpf_cnpj && <span style={{ color: '#6b7280', marginLeft: 8 }}>{fmtDoc(c.cpf_cnpj)}</span>}
                    </li>
                  ))}
                </ul>
              )}
              {form.cliente_id && (
                <div style={{ fontSize: 11, color: '#15803d', marginTop: 4 }}>
                  ✓ Vinculado ao cliente. Os dados abaixo podem ser ajustados.
                </div>
              )}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Campo label="Nome / Razão social *" value={form.nome}
              onChange={(v) => set('nome', v)} />
            <Campo label="CPF / CNPJ" value={mascaraDocumento(form.cpf_cnpj || '')}
              onChange={(v) => set('cpf_cnpj', soDigitos(v))} />
            <Campo label="Email" value={form.email || ''} onChange={(v) => set('email', v)} />
            <Campo label="Telefone" value={form.telefone || ''} onChange={(v) => set('telefone', v)} />
            <Campo label="Logradouro" value={form.logradouro || ''} onChange={(v) => set('logradouro', v)} />
            <Campo label="Número" value={form.numero || ''} onChange={(v) => set('numero', v)} />
            <Campo label="Bairro" value={form.bairro || ''} onChange={(v) => set('bairro', v)} />
            <Campo label="CEP" value={form.cep || ''} onChange={(v) => set('cep', soDigitos(v))} />
          </div>

          {erro && (
            <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, padding: 8, marginTop: 10, fontSize: 12, color: '#b91c1c' }}>
              {erro}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
            <button
              disabled={!form.nome || salvar.isPending}
              onClick={() => salvar.mutate(form)}
              style={{ background: '#0f766e', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 16px', fontWeight: 600, cursor: 'pointer', opacity: !form.nome || salvar.isPending ? 0.5 : 1 }}>
              {salvar.isPending ? 'Salvando…' : editId ? 'Salvar alterações' : 'Cadastrar'}
            </button>
            <button onClick={() => { setMostrarForm(false); setForm(EMPTY); setEditId(null); setErro(null) }}
              style={{ background: '#fff', color: '#374151', border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 16px', cursor: 'pointer' }}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Tabela de pagantes */}
      {pagantes.length === 0 ? (
        <p style={{ fontSize: 13, color: '#6b7280' }}>Nenhum pagante ainda. Cadastre um ou emita uma NF.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #d1d5db', background: '#f9fafb' }}>
                <th style={th}>Nome</th>
                <th style={th}>CPF/CNPJ</th>
                <th style={th}>Email</th>
                <th style={th}>Endereço</th>
                <th style={{ ...th, textAlign: 'center' }}>NFs</th>
                <th style={{ ...th, textAlign: 'right' }}>Total recebido</th>
                <th style={th}>Vínculo</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {pagantes.map((p) => (
                <tr key={p.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ ...td, fontWeight: 600, color: '#1f2937' }}>
                    {p.nome}
                    {p.origem === 'manual' && p.qtd_nfs === 0 && (
                      <span style={{ marginLeft: 6, fontSize: 10, background: '#eff6ff', color: '#1d4ed8', padding: '1px 6px', borderRadius: 4 }}>cadastrado</span>
                    )}
                  </td>
                  <td style={{ ...td, color: '#6b7280' }}>{fmtDoc(p.cpf_cnpj)}</td>
                  <td style={{ ...td, color: '#6b7280', fontSize: 11 }}>{p.email || '—'}</td>
                  <td style={{ ...td, color: '#6b7280', fontSize: 11 }}>{fmtEndereco(p)}</td>
                  <td style={{ ...td, textAlign: 'center', fontWeight: 600 }}>{p.qtd_nfs}</td>
                  <td style={{ ...td, textAlign: 'right', fontWeight: 600, color: '#065f46' }}>{fmtBRL(p.valor_total)}</td>
                  <td style={{ ...td, fontSize: 11 }}>
                    {p.cliente_nome ? (
                      <span style={{ background: '#dcfce7', color: '#15803d', padding: '3px 8px', borderRadius: 4, fontWeight: 600, whiteSpace: 'nowrap' }}>
                        ✓ {p.cliente_nome}
                      </span>
                    ) : (
                      <span style={{ color: '#9ca3af', fontSize: 10 }}>Não-cliente</span>
                    )}
                  </td>
                  <td style={{ ...td, whiteSpace: 'nowrap' }}>
                    <button onClick={() => abrirEdicao(p)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#0f766e', fontSize: 12, marginRight: 8 }}>
                      ✎
                    </button>
                    <button onClick={() => { if (confirm(`Remover pagante ${p.nome}? (não apaga as NFs)`)) deletar.mutate(p.id) }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#b91c1c', fontSize: 14 }}>
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 20, lineHeight: 1.6 }}>
        <p><strong>Pagantes</strong> são as pessoas/empresas contra quem você emite NF (tomadores), cadastradas ou não.</p>
        <p>Cadastre um pagante manualmente (ex.: Ana Maria, que paga por Mangrove) — ele já aparece na emissão de NF.</p>
        <p>Quem recebe uma NF é adicionado automaticamente aqui. <strong>Vínculo</strong> mostra o cliente correspondente (por CPF/CNPJ ou link manual).</p>
      </div>
    </div>
  )
}

const th: React.CSSProperties = { padding: '10px 12px', textAlign: 'left', fontWeight: 600 }
const td: React.CSSProperties = { padding: '10px 12px' }

function Campo({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 4 }}>{label}</label>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, boxSizing: 'border-box' }} />
    </div>
  )
}
