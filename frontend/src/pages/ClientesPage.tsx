import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { clientesApi } from '../api/clientes'
import type { ClienteCreate } from '../api/clientes'
import {
  applyDocMask, buscarCep, ESTADO_CIVIL_OPCOES, maskCEP, maskCPF, maskTelefone,
} from '../utils/masks'
import styles from './Page.module.css'
import cs from './ClientesPage.module.css'

const EMPTY: ClienteCreate = { nome: '', tipo: 'PF', cpf_cnpj: '', email: '', telefone: '', observacoes: '' }

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

  const toggleMonitorar = useMutation({
    mutationFn: ({ id, monitorar_diario }: { id: string; monitorar_diario: boolean }) =>
      clientesApi.atualizar(id, { monitorar_diario }),
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
                  {c.monitorar_diario && (
                    <span className={styles.badge} style={{ background: '#064e3b', color: '#6ee7b7', borderColor: '#065f46' }} title="Nome incluído na busca automática do Diário Oficial">
                      ◎ Diário
                    </span>
                  )}
                  {c.email && <span className={cs.meta}>✉ {c.email}</span>}
                  {c.telefone && <span className={cs.meta}>☏ {c.telefone}</span>}
                </div>
                <div className={cs.cardActions}>
                  <button
                    className={styles.btnTable}
                    disabled={toggleMonitorar.isPending}
                    title={c.monitorar_diario ? 'Parar de monitorar este cliente no Diário Oficial' : 'Monitorar o nome deste cliente no Diário Oficial'}
                    style={c.monitorar_diario ? { color: '#6ee7b7', borderColor: '#065f46' } : undefined}
                    onClick={() => toggleMonitorar.mutate({ id: c.id, monitorar_diario: !c.monitorar_diario })}
                  >
                    {c.monitorar_diario ? '◎ Monitorando' : '○ Monitorar Diário'}
                  </button>
                  <Link to={`/clientes/${c.id}`} className={styles.btnTable}>Ver</Link>
                  <button className={styles.btnTable}
                    onClick={() => {
                      setEditando(editando === c.id ? null : c.id)
                      setEditForm({
                        nome: c.nome, tipo: c.tipo, cpf_cnpj: c.cpf_cnpj, email: c.email,
                        telefone: c.telefone, whatsapp: c.whatsapp, observacoes: c.observacoes,
                        cep: c.cep, logradouro: c.logradouro, numero: c.numero, complemento: c.complemento,
                        bairro: c.bairro, cidade: c.cidade, uf: c.uf,
                        data_nascimento: c.data_nascimento, rg: c.rg, estado_civil: c.estado_civil,
                        profissao: c.profissao, empresas_vinculadas: c.empresas_vinculadas,
                        nome_fantasia: c.nome_fantasia, responsavel_nome: c.responsavel_nome,
                        responsavel_cpf: c.responsavel_cpf, responsavel_email: c.responsavel_email,
                        responsavel_telefone: c.responsavel_telefone,
                      })
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

function EnderecoFields({ form, onChange }: { form: ClienteCreate; onChange: (f: ClienteCreate) => void }) {
  async function onCepBlur() {
    const res = await buscarCep(form.cep ?? '')
    if (!res) return
    onChange({
      ...form,
      logradouro: res.logradouro || form.logradouro,
      bairro: res.bairro || form.bairro,
      cidade: res.localidade || form.cidade,
      uf: res.uf || form.uf,
    })
  }
  return (
    <>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>CEP</label>
        <input className={styles.input} placeholder="00000-000" value={form.cep ?? ''}
          onChange={(e) => onChange({ ...form, cep: maskCEP(e.target.value) })}
          onBlur={onCepBlur} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Logradouro</label>
        <input className={styles.input} value={form.logradouro ?? ''}
          onChange={(e) => onChange({ ...form, logradouro: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Número</label>
        <input className={styles.input} value={form.numero ?? ''}
          onChange={(e) => onChange({ ...form, numero: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Complemento</label>
        <input className={styles.input} value={form.complemento ?? ''}
          onChange={(e) => onChange({ ...form, complemento: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Bairro</label>
        <input className={styles.input} value={form.bairro ?? ''}
          onChange={(e) => onChange({ ...form, bairro: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Cidade</label>
        <input className={styles.input} value={form.cidade ?? ''}
          onChange={(e) => onChange({ ...form, cidade: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>UF</label>
        <input className={styles.input} maxLength={2} style={{ maxWidth: 80 }} value={form.uf ?? ''}
          onChange={(e) => onChange({ ...form, uf: e.target.value.toUpperCase().slice(0, 2) })} />
      </div>
    </>
  )
}

function ClienteFormFields({ form, onChange }: { form: ClienteCreate; onChange: (f: ClienteCreate) => void }) {
  const isPF = form.tipo === 'PF'
  return (
    <>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Tipo *</label>
        <select className={styles.input} value={form.tipo}
          onChange={(e) => onChange({ ...form, tipo: e.target.value as 'PF' | 'PJ', cpf_cnpj: '' })}>
          <option value="PF">Pessoa Física</option>
          <option value="PJ">Pessoa Jurídica</option>
        </select>
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>{isPF ? 'Nome completo *' : 'Razão social *'}</label>
        <input className={styles.input} value={form.nome ?? ''}
          onChange={(e) => onChange({ ...form, nome: e.target.value })} required />
      </div>
      {!isPF && (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Nome fantasia</label>
          <input className={styles.input} value={form.nome_fantasia ?? ''}
            onChange={(e) => onChange({ ...form, nome_fantasia: e.target.value })} />
        </div>
      )}
      <div className={styles.formRow}>
        <label className={styles.formLabel}>{isPF ? 'CPF' : 'CNPJ'}</label>
        <input className={styles.input}
          placeholder={isPF ? '000.000.000-00' : '00.000.000/0000-00'}
          value={form.cpf_cnpj ?? ''}
          onChange={(e) => onChange({ ...form, cpf_cnpj: applyDocMask(e.target.value, form.tipo) })} />
      </div>

      {isPF && (
        <>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>RG</label>
            <input className={styles.input} value={form.rg ?? ''}
              onChange={(e) => onChange({ ...form, rg: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data de nascimento</label>
            <input type="date" className={styles.input} value={form.data_nascimento ?? ''}
              onChange={(e) => onChange({ ...form, data_nascimento: e.target.value || null })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Estado civil</label>
            <select className={styles.input} value={form.estado_civil ?? ''}
              onChange={(e) => onChange({ ...form, estado_civil: e.target.value })}>
              <option value="">—</option>
              {ESTADO_CIVIL_OPCOES.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Profissão</label>
            <input className={styles.input} value={form.profissao ?? ''}
              onChange={(e) => onChange({ ...form, profissao: e.target.value })} />
          </div>
        </>
      )}

      <div className={styles.formRow}>
        <label className={styles.formLabel}>{isPF ? 'Email' : 'Email comercial'}</label>
        <input type="email" className={styles.input} value={form.email ?? ''}
          onChange={(e) => onChange({ ...form, email: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>{isPF ? 'Telefone (WhatsApp)' : 'Telefone comercial'}</label>
        <input className={styles.input} placeholder="(00) 0.0000-0000"
          value={form.telefone ?? ''}
          onChange={(e) => onChange({ ...form, telefone: maskTelefone(e.target.value) })} />
      </div>
      {!isPF && (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>WhatsApp comercial</label>
          <input className={styles.input} placeholder="(00) 0.0000-0000"
            value={form.whatsapp ?? ''}
            onChange={(e) => onChange({ ...form, whatsapp: maskTelefone(e.target.value) })} />
        </div>
      )}

      <EnderecoFields form={form} onChange={onChange} />

      {isPF ? (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Empresas vinculadas ao CPF</label>
          <textarea className={styles.input} rows={2} placeholder="Uma por linha"
            value={form.empresas_vinculadas ?? ''}
            onChange={(e) => onChange({ ...form, empresas_vinculadas: e.target.value })} />
        </div>
      ) : (
        <>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Responsável</label>
            <input className={styles.input} value={form.responsavel_nome ?? ''}
              onChange={(e) => onChange({ ...form, responsavel_nome: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>CPF do responsável</label>
            <input className={styles.input} placeholder="000.000.000-00"
              value={form.responsavel_cpf ?? ''}
              onChange={(e) => onChange({ ...form, responsavel_cpf: maskCPF(e.target.value) })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Email do responsável</label>
            <input type="email" className={styles.input} value={form.responsavel_email ?? ''}
              onChange={(e) => onChange({ ...form, responsavel_email: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Telefone do responsável (WhatsApp)</label>
            <input className={styles.input} placeholder="(00) 0.0000-0000"
              value={form.responsavel_telefone ?? ''}
              onChange={(e) => onChange({ ...form, responsavel_telefone: maskTelefone(e.target.value) })} />
          </div>
        </>
      )}

      <div className={styles.formRow}>
        <label className={styles.formLabel}>Observações</label>
        <textarea className={styles.input} rows={2} value={form.observacoes ?? ''}
          onChange={(e) => onChange({ ...form, observacoes: e.target.value })} />
      </div>
    </>
  )
}
