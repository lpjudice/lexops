import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/api/client'
import Modal from '@/components/Modal'
import styles from './Page.module.css'
import cs from './Carteira.module.css'

type Tab = 'clientes' | 'emissoes' | 'debentures' | 'empreendimentos' | 'imobiliario' | 'fundos-ref' | 'fundos' | 'estrategias'

const brl = (v: number | null | undefined) =>
  `R$ ${(v ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const pct = (v: number | null | undefined) =>
  `${(v ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`

const TABS_REF: { key: Tab; label: string }[] = [
  { key: 'emissoes', label: 'Emissões' },
  { key: 'empreendimentos', label: 'Empreendimentos' },
  { key: 'fundos-ref', label: 'Fundos Ref.' },
  { key: 'estrategias', label: 'Estratégias' },
]

const TABS_POS: { key: Tab; label: string }[] = [
  { key: 'clientes', label: 'Clientes' },
  { key: 'debentures', label: 'Debêntures' },
  { key: 'imobiliario', label: 'Imobiliário' },
  { key: 'fundos', label: 'Fundos Posição' },
]

export default function CarteiraPage() {
  const [tab, setTab] = useState<Tab>('debentures')
  const [modal, setModal] = useState<string | null>(null)
  const [form, setForm] = useState<Record<string, any>>({})
  const [editandoClienteId, setEditandoClienteId] = useState<number | null>(null)
  const [buscaSistema, setBuscaSistema] = useState('')
  const qc = useQueryClient()

  const inp = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }))
  const closeModal = () => { setModal(null); setForm({}); setEditandoClienteId(null); setBuscaSistema('') }

  // ── queries ──────────────────────────────────────────────────────
  const { data: dash } = useQuery({
    queryKey: ['carteira-dash'],
    queryFn: () => api.get('/carteira/dashboard').then(r => r.data),
  })
  const { data: clientesRes } = useQuery({
    queryKey: ['carteira-clientes'],
    queryFn: () => api.get('/carteira/clientes', { params: { limit: 200 } }).then(r => r.data),
  })
  const { data: emissoesRef = [] } = useQuery({
    queryKey: ['carteira-emissoes'],
    queryFn: () => api.get('/carteira/emissoes').then(r => r.data),
  })
  const { data: debenturesRes } = useQuery({
    queryKey: ['carteira-debentures'],
    queryFn: () => api.get('/carteira/debentures', { params: { limit: 200 } }).then(r => r.data),
  })
  const { data: empreendimentosRef = [] } = useQuery({
    queryKey: ['carteira-empreendimentos'],
    queryFn: () => api.get('/carteira/empreendimentos').then(r => r.data),
  })
  const { data: imobiliarioRes } = useQuery({
    queryKey: ['carteira-imobiliario'],
    queryFn: () => api.get('/carteira/imobiliario', { params: { limit: 200 } }).then(r => r.data),
  })
  const { data: fundosRefRes = [] } = useQuery({
    queryKey: ['carteira-fundos-ref'],
    queryFn: () => api.get('/carteira/fundos-referencia').then(r => r.data),
  })
  const { data: fundosRes } = useQuery({
    queryKey: ['carteira-fundos'],
    queryFn: () => api.get('/carteira/fundos', { params: { limit: 200 } }).then(r => r.data),
  })
  const { data: estrategiasRes } = useQuery({
    queryKey: ['carteira-estrategias'],
    queryFn: () => api.get('/carteira/estrategias').then(r => r.data),
  })
  // Busca de clientes no sistema principal (para vincular ao carteira_cliente)
  const { data: clientesSistema = [] } = useQuery({
    queryKey: ['clientes-sistema-busca', buscaSistema],
    queryFn: () => api.get('/clientes', { params: { busca: buscaSistema, limit: 10 } }).then(r => r.data?.data ?? r.data),
    enabled: buscaSistema.length >= 2,
  })

  const clientes: any[] = clientesRes?.data ?? []
  const debentures: any[] = debenturesRes?.data ?? []
  const imobiliario: any[] = imobiliarioRes?.data ?? []
  const fundos: any[] = fundosRes?.data ?? []
  const estrategias: any[] = estrategiasRes?.data ?? []
  const emissoes: any[] = Array.isArray(emissoesRef) ? emissoesRef : []
  const empreendimentos: any[] = Array.isArray(empreendimentosRef) ? empreendimentosRef : []
  const fundosRef: any[] = Array.isArray(fundosRefRes) ? fundosRefRes : []

  // ── lookup helpers ────────────────────────────────────────────────
  const clienteNome = (id: number) => {
    const c = clientes.find((c: any) => c.id === id)
    if (!c) return `#${id}`
    if (c.nome) return c.nome
    if (c.observacoes?.startsWith('[IMPORTADO XLS] ')) return c.observacoes.replace('[IMPORTADO XLS] ', '')
    return `#${id}`
  }
  const emissaoNome = (id: number) => emissoes.find(e => e.id === id)?.nome_serie ?? `#${id}`
  const empreendimentoNome = (id: number) => empreendimentos.find(e => e.id === id)?.nome_venda ?? `#${id}`
  const fundoNome = (id: number) => fundosRef.find(f => f.id === id)?.nome_fundo ?? `#${id}`

  // ── mutations ─────────────────────────────────────────────────────
  const mk = (url: string, keys: string[], numFields: string[] = []) => useMutation({
    mutationFn: () => {
      const payload: Record<string, any> = { ...form }
      numFields.forEach(k => { if (payload[k] !== undefined && payload[k] !== '') payload[k] = Number(payload[k]) })
      return api.post(url, payload).then(r => r.data)
    },
    onSuccess: () => {
      keys.forEach(k => qc.invalidateQueries({ queryKey: [k] }))
      closeModal()
    },
    onError: (e: any) => alert(e?.response?.data?.detail || 'Erro ao salvar'),
  })

  const salvarCliente = mk('/carteira/clientes', ['carteira-clientes', 'carteira-dash'],
    ['pro_labore_valor', 'percentual_sucesso_geral'])

  const atualizarCliente = useMutation({
    mutationFn: () => {
      const payload: Record<string, any> = { ...form }
      ;['pro_labore_valor', 'percentual_sucesso_geral'].forEach(k => {
        if (payload[k] !== undefined && payload[k] !== '') payload[k] = Number(payload[k])
      })
      return api.put(`/carteira/clientes/${editandoClienteId}`, payload).then(r => r.data)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['carteira-clientes'] })
      qc.invalidateQueries({ queryKey: ['carteira-dash'] })
      closeModal()
    },
    onError: (e: any) => alert(e?.response?.data?.detail || 'Erro ao salvar'),
  })

  const salvarEmissao = mk('/carteira/emissoes', ['carteira-emissoes'], ['numero_emissao'])
  const salvarDebenture = mk('/carteira/debentures', ['carteira-debentures', 'carteira-dash'],
    ['cliente_id', 'emissao_id', 'valor_aplicado', 'valor_atual_estimado', 'percentual_sucesso_honor', 'numero_debentures'])
  const salvarEmpreendimento = mk('/carteira/empreendimentos', ['carteira-empreendimentos'])
  const salvarImobiliario = mk('/carteira/imobiliario', ['carteira-imobiliario', 'carteira-dash'],
    ['cliente_id', 'empreendimento_id', 'valor_total_compromissado', 'valor_efetivamente_investido', 'percentual_participacao', 'percentual_sucesso_honorario'])
  const salvarFundoRef = mk('/carteira/fundos-referencia', ['carteira-fundos-ref'])
  const salvarFundo = mk('/carteira/fundos', ['carteira-fundos', 'carteira-dash'],
    ['cliente_id', 'fundo_id', 'valor_aplicado', 'valor_atual_estimado', 'percentual_sucesso_honor'])
  const salvarEstrategia = mk('/carteira/estrategias', ['carteira-estrategias'])

  // ── abrir edição de cliente ───────────────────────────────────────
  const abrirEdicaoCliente = (c: any) => {
    const nomeAtual = c.nome ?? (c.observacoes?.startsWith('[IMPORTADO XLS] ')
      ? c.observacoes.replace('[IMPORTADO XLS] ', '') : '')
    setForm({
      nome: nomeAtual,
      tipo_pessoa: c.tipo_pessoa ?? 'PF',
      cpf: c.cpf ?? '',
      email: c.email ?? '',
      telefone: c.telefone ?? '',
      pro_labore_tipo: c.pro_labore_tipo ?? 'fixo',
      pro_labore_valor: c.pro_labore_valor ?? '',
      percentual_sucesso_geral: c.percentual_sucesso_geral ?? '',
      cliente_uuid: c.cliente_uuid ?? '',
      observacoes: c.observacoes ?? '',
      ativo: c.ativo ?? true,
    })
    setEditandoClienteId(c.id)
    setModal('cliente')
  }

  const emptyRow = (cols: number) => (
    <tr>
      <td colSpan={cols} style={{ textAlign: 'center', padding: '40px 24px', color: '#9ca3af', fontSize: 14 }}>
        Nenhum registro cadastrado
      </td>
    </tr>
  )

  const statusBadge = (s: string | boolean) => {
    if (s === true || s === 'Ativo' || s === 'Ativa') return <span className={`${styles.badge} ${styles.status_ativo}`}>{s === true ? 'Ativo' : s}</span>
    if (s === false || s === 'Inativo' || s === 'Inativa') return <span className={`${styles.badge} ${styles.status_arquivado}`}>{s === false ? 'Inativo' : s}</span>
    if (s === 'Resgate Solicitado') return <span className={`${styles.badge} ${styles.status_suspenso}`}>{s}</span>
    if (s === 'Resgatado') return <span className={`${styles.badge} ${styles.status_encerrado}`}>{s}</span>
    return <span className={styles.badge}>{String(s)}</span>
  }

  // ── form helpers ─────────────────────────────────────────────────
  const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div className={styles.formRow}>
      <label className={styles.formLabel}>{label}</label>
      {children}
    </div>
  )
  const Inp = ({ k, type = 'text', placeholder = '' }: { k: string; type?: string; placeholder?: string }) => (
    <input className={styles.input} type={type} value={form[k] ?? ''} onChange={e => inp(k, e.target.value)} placeholder={placeholder} />
  )
  const Sel = ({ k, options }: { k: string; options: { value: string | number; label: string }[] }) => (
    <select className={styles.input} value={form[k] ?? ''} onChange={e => inp(k, e.target.value)}>
      <option value="">— Selecione —</option>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )

  const addBtn = (label: string, onClick: () => void) => (
    <div className={styles.pageHeader} style={{ marginBottom: 12 }}>
      <span />
      <button className={styles.btnPrimary} onClick={onClick}>+ {label}</button>
    </div>
  )

  const clienteOptions = clientes.map((c: any) => ({
    value: c.id,
    label: clienteNome(c.id),
  }))

  return (
    <div style={{ padding: '24px 28px' }}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Carteira</h1>
      </div>

      {/* KPI Cards */}
      <div className={cs.kpiGrid}>
        <div className={cs.kpiCard}>
          <span className={cs.kpiLabel}>Clientes</span>
          <span className={cs.kpiValue}>{dash?.total_clientes ?? 0}</span>
        </div>
        <div className={cs.kpiCard}>
          <span className={cs.kpiLabel}>Carteira Total</span>
          <span className={cs.kpiValue}>{brl(dash?.carteira_total)}</span>
        </div>
        <div className={cs.kpiCard}>
          <span className={cs.kpiLabel}>Valor Atual</span>
          <span className={cs.kpiValue}>{brl(dash?.valor_atual_total)}</span>
        </div>
        <div className={cs.kpiCard}>
          <span className={cs.kpiLabel}>Pro-Labore / mês</span>
          <span className={cs.kpiValue}>{brl(dash?.pro_labore_mensal)}</span>
        </div>
        <div className={cs.kpiCard}>
          <span className={cs.kpiLabel}>Honorários Esperados</span>
          <span className={cs.kpiValue}>{brl(dash?.expectativa_honorarios)}</span>
        </div>
      </div>

      {/* Tab Bar com dois grupos */}
      <div className={cs.tabBar}>
        <span className={cs.tabGroupLabel}>Carteira</span>
        {TABS_POS.map(t => (
          <button
            key={t.key}
            className={`${cs.tabBtn} ${tab === t.key ? cs.tabBtnActive : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
        <span className={cs.tabGroupLabel} style={{ marginLeft: 8 }}>Referência</span>
        {TABS_REF.map(t => (
          <button
            key={t.key}
            className={`${cs.tabBtn} ${tab === t.key ? cs.tabBtnActive : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── CLIENTES ─────────────────────────────────────────────── */}
      {tab === 'clientes' && (
        <>
          {addBtn('Novo Cliente', () => {
            setForm({ pro_labore_tipo: 'fixo', tipo_pessoa: 'PF' })
            setEditandoClienteId(null)
            setModal('cliente')
          })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Nome</th><th>Tipo</th><th>CPF</th>
                  <th>Modelo honor.</th><th>Pro-Labore</th><th>% Sucesso</th><th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {clientes.length === 0 ? emptyRow(8) : clientes.map((c: any) => (
                  <tr key={c.id}>
                    <td><strong>{clienteNome(c.id)}</strong></td>
                    <td><span className={styles.badge}>{c.tipo_pessoa ?? 'PF'}</span></td>
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{c.cpf ?? '—'}</td>
                    <td>{c.pro_labore_tipo === 'percentual' ? '% carteira' : 'mensal fixo'}</td>
                    <td>{c.pro_labore_valor ? brl(c.pro_labore_valor) : '—'}</td>
                    <td>{c.percentual_sucesso_geral ? pct(c.percentual_sucesso_geral) : '—'}</td>
                    <td>{statusBadge(c.ativo)}</td>
                    <td>
                      <button
                        style={{ background: 'none', border: '1px solid var(--gray-border)', borderRadius: 4, padding: '3px 10px', cursor: 'pointer', fontSize: 12, color: 'var(--gray-mid)' }}
                        onClick={() => abrirEdicaoCliente(c)}
                      >
                        Editar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── EMISSÕES ─────────────────────────────────────────────── */}
      {tab === 'emissoes' && (
        <>
          {addBtn('Nova Emissão', () => { setForm({ numero_emissao: 1 }); setModal('emissao') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>#</th><th>Série</th><th>Nº Emissão</th>
                  <th>Emissor</th><th>Indexador</th><th>Vencimento</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {emissoes.length === 0 ? emptyRow(7) : emissoes.map((e: any) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td><strong>{e.nome_serie}</strong></td>
                    <td>{e.numero_emissao}ª</td>
                    <td>{e.emissor}</td>
                    <td>{e.indexador}{e.taxa_adicional ? ` + ${e.taxa_adicional}` : ''}</td>
                    <td>{e.data_vencimento_previsto ?? '—'}</td>
                    <td>{statusBadge(e.ativo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── DEBÊNTURES ───────────────────────────────────────────── */}
      {tab === 'debentures' && (
        <>
          {addBtn('Nova Posição', () => { setForm({ status_resgate: 'Ativo', faz_parte_honorarios: false }); setModal('debenture') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Cautela</th><th>Emissão</th><th>Cliente</th>
                  <th>Aplicado</th><th>Atual</th><th>Status</th><th>Honorários</th>
                </tr>
              </thead>
              <tbody>
                {debentures.length === 0 ? emptyRow(7) : debentures.map((d: any) => (
                  <tr key={d.id}>
                    <td><strong>{d.numero_cautela}</strong></td>
                    <td>{emissaoNome(d.emissao_id)}</td>
                    <td>{clienteNome(d.cliente_id)}</td>
                    <td>{brl(d.valor_aplicado)}</td>
                    <td>{d.valor_atual_estimado ? brl(d.valor_atual_estimado) : '—'}</td>
                    <td>{statusBadge(d.status_resgate)}</td>
                    <td>{d.faz_parte_honorarios ? pct(d.percentual_sucesso_honor) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── EMPREENDIMENTOS ──────────────────────────────────────── */}
      {tab === 'empreendimentos' && (
        <>
          {addBtn('Novo Empreendimento', () => { setForm({}); setModal('empreendimento') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>#</th><th>Nome</th><th>Tipo</th>
                  <th>Localização</th><th>Veículo ABM</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {empreendimentos.length === 0 ? emptyRow(6) : empreendimentos.map((e: any) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td><strong>{e.nome_venda}</strong></td>
                    <td>{e.tipo_desenvolvimento ?? '—'}</td>
                    <td>{e.localizacao ?? '—'}</td>
                    <td>{e.abmparse_veiculo ?? '—'}</td>
                    <td>{statusBadge(e.ativo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── IMOBILIÁRIO ──────────────────────────────────────────── */}
      {tab === 'imobiliario' && (
        <>
          {addBtn('Nova Posição', () => { setForm({ percentual_participacao: 100, faz_parte_honorarios: false }); setModal('imobiliario') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Empreendimento</th><th>Cliente</th>
                  <th>Comprometido</th><th>Investido</th><th>% Part.</th><th>Honorários</th>
                </tr>
              </thead>
              <tbody>
                {imobiliario.length === 0 ? emptyRow(6) : imobiliario.map((i: any) => (
                  <tr key={i.id}>
                    <td>{empreendimentoNome(i.empreendimento_id)}</td>
                    <td>{clienteNome(i.cliente_id)}</td>
                    <td>{brl(i.valor_total_compromissado)}</td>
                    <td>{brl(i.valor_efetivamente_investido)}</td>
                    <td>{pct(i.percentual_participacao)}</td>
                    <td>{i.faz_parte_honorarios ? pct(i.percentual_sucesso_honorario) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── FUNDOS REF ───────────────────────────────────────────── */}
      {tab === 'fundos-ref' && (
        <>
          {addBtn('Novo Fundo', () => { setForm({}); setModal('fundo-ref') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>#</th><th>Nome</th><th>CNPJ</th>
                  <th>Gestora</th><th>Tipo</th><th>Indexador</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {fundosRef.length === 0 ? emptyRow(7) : fundosRef.map((f: any) => (
                  <tr key={f.id}>
                    <td>{f.id}</td>
                    <td><strong>{f.nome_fundo}</strong></td>
                    <td>{f.cnpj_fundo ?? '—'}</td>
                    <td>{f.gestora ?? '—'}</td>
                    <td>{f.tipo_fundo ?? '—'}</td>
                    <td>{f.indexador ?? '—'}</td>
                    <td>{statusBadge(f.ativo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── FUNDOS POSIÇÃO ───────────────────────────────────────── */}
      {tab === 'fundos' && (
        <>
          {addBtn('Nova Posição', () => { setForm({ faz_parte_honorarios: false }); setModal('fundo') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Fundo</th><th>Cliente</th>
                  <th>Aplicado</th><th>Atual</th><th>Data Aplicação</th><th>Honorários</th>
                </tr>
              </thead>
              <tbody>
                {fundos.length === 0 ? emptyRow(6) : fundos.map((f: any) => (
                  <tr key={f.id}>
                    <td>{fundoNome(f.fundo_id)}</td>
                    <td>{clienteNome(f.cliente_id)}</td>
                    <td>{brl(f.valor_aplicado)}</td>
                    <td>{f.valor_atual_estimado ? brl(f.valor_atual_estimado) : '—'}</td>
                    <td>{f.data_aplicacao ?? '—'}</td>
                    <td>{f.faz_parte_honorarios ? pct(f.percentual_sucesso_honor) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── ESTRATÉGIAS ──────────────────────────────────────────── */}
      {tab === 'estrategias' && (
        <>
          {addBtn('Nova Estratégia', () => { setForm({ publico: true }); setModal('estrategia') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr><th>#</th><th>Nome</th><th>Descrição</th><th>Usos</th><th>Status</th></tr>
              </thead>
              <tbody>
                {estrategias.length === 0 ? emptyRow(5) : estrategias.map((e: any) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td><strong>{e.nome}</strong></td>
                    <td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.descricao ?? '—'}</td>
                    <td>{e.usuarios_count ?? 0}</td>
                    <td>{statusBadge(e.ativo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ════════════════ MODAIS ════════════════════════════════════ */}

      {/* ── MODAL CLIENTE (criar + editar) ───────────────────────── */}
      {modal === 'cliente' && (
        <Modal
          title={editandoClienteId ? `Editar cliente — ${clienteNome(editandoClienteId)}` : 'Novo cliente na carteira'}
          onClose={closeModal}
          width={560}
        >
          {/* Vinculação ao sistema principal */}
          <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 6, padding: '10px 14px', marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--gray-mid)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
              Vincular a cliente existente no sistema
            </div>
            <input
              className={styles.input}
              placeholder="Digite o nome para buscar..."
              value={buscaSistema}
              onChange={e => setBuscaSistema(e.target.value)}
              style={{ marginBottom: clientesSistema.length > 0 ? 6 : 0 }}
            />
            {clientesSistema.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {clientesSistema.map((cs: any) => (
                  <button
                    key={cs.id}
                    style={{ textAlign: 'left', background: 'white', border: '1px solid var(--gray-border)', borderRadius: 4, padding: '5px 10px', cursor: 'pointer', fontSize: 13 }}
                    onClick={() => {
                      inp('nome', cs.nome)
                      inp('cpf', cs.cpf_cnpj ?? '')
                      inp('email', cs.email ?? '')
                      inp('telefone', cs.telefone ?? '')
                      inp('tipo_pessoa', cs.tipo === 'PF' ? 'PF' : 'PJ')
                      inp('cliente_uuid', cs.id)
                      setBuscaSistema('')
                    }}
                  >
                    <strong>{cs.nome}</strong>
                    {cs.cpf_cnpj && <span style={{ color: 'var(--gray-mid)', marginLeft: 8, fontSize: 12 }}>{cs.cpf_cnpj}</span>}
                  </button>
                ))}
              </div>
            )}
            {form.cliente_uuid && (
              <div style={{ fontSize: 11, color: 'var(--teal, #0d9488)', marginTop: 4 }}>
                ✓ Vinculado ao cadastro do sistema
                <button
                  style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-mid)', fontSize: 11 }}
                  onClick={() => inp('cliente_uuid', '')}
                >remover vínculo</button>
              </div>
            )}
          </div>

          <Field label="Nome completo *">
            <Inp k="nome" placeholder="Nome do investidor" />
          </Field>
          <Field label="Tipo pessoa">
            <Sel k="tipo_pessoa" options={[
              { value: 'PF', label: 'PF — Pessoa Física' },
              { value: 'PJ', label: 'PJ — Pessoa Jurídica' },
            ]} />
          </Field>
          <Field label={form.tipo_pessoa === 'PJ' ? 'CNPJ' : 'CPF'}>
            <Inp k="cpf" placeholder={form.tipo_pessoa === 'PJ' ? '00.000.000/0001-00' : '000.000.000-00'} />
          </Field>

          {form.tipo_pessoa !== 'PJ' && (
            <>
              <Field label="Estado civil">
                <Sel k="estado_civil" options={[
                  { value: 'solteiro', label: 'Solteiro(a)' },
                  { value: 'casado', label: 'Casado(a)' },
                  { value: 'uniao_estavel', label: 'União estável' },
                  { value: 'divorciado', label: 'Divorciado(a)' },
                  { value: 'viuvo', label: 'Viúvo(a)' },
                ]} />
              </Field>
              <Field label="Profissão">
                <Inp k="profissao" placeholder="Ex: Empresário, Médico" />
              </Field>
            </>
          )}

          {form.tipo_pessoa === 'PJ' && (
            <Field label="Representante legal">
              <Inp k="representante_nome" placeholder="Nome do representante" />
            </Field>
          )}

          <Field label="E-mail">
            <Inp k="email" type="email" placeholder="email@exemplo.com" />
          </Field>
          <Field label="Telefone">
            <Inp k="telefone" placeholder="(27) 9 9999-9999" />
          </Field>

          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '12px 0', paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--gray-mid)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Modelo de honorários
            </div>
            <Field label="Tipo de cobrança">
              <Sel k="pro_labore_tipo" options={[
                { value: 'fixo', label: 'Mensal fixo (pro-labore)' },
                { value: 'percentual', label: 'Percentual sobre carteira' },
                { value: 'nenhum', label: 'Nenhum (apenas êxito)' },
              ]} />
            </Field>
            {form.pro_labore_tipo !== 'nenhum' && (
              <Field label={form.pro_labore_tipo === 'percentual' ? '% da carteira (ao ano)' : 'Valor mensal (R$)'}>
                <Inp k="pro_labore_valor" type="number" placeholder={form.pro_labore_tipo === 'percentual' ? 'Ex: 1.5' : 'Ex: 5000'} />
              </Field>
            )}
            <Field label="% Honorários de êxito (geral)">
              <Inp k="percentual_sucesso_geral" type="number" placeholder="Ex: 20" />
            </Field>
          </div>

          <Field label="Observações">
            <textarea className={styles.input} rows={2} value={form.observacoes ?? ''} onChange={e => inp('observacoes', e.target.value)} />
          </Field>

          {editandoClienteId && (
            <Field label="Status">
              <Sel k="ativo" options={[
                { value: 'true', label: 'Ativo' },
                { value: 'false', label: 'Inativo' },
              ]} />
            </Field>
          )}

          <button
            className={styles.btnPrimary}
            onClick={() => editandoClienteId ? atualizarCliente.mutate() : salvarCliente.mutate()}
            disabled={salvarCliente.isPending || atualizarCliente.isPending}
          >
            {(salvarCliente.isPending || atualizarCliente.isPending) ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {modal === 'emissao' && (
        <Modal title="Nova Emissão de Debênture" onClose={closeModal} width={560}>
          <Field label="Nome da Série *">
            <Inp k="nome_serie" placeholder="Ex: APEX I" />
          </Field>
          <Field label="Nº da Emissão *">
            <Inp k="numero_emissao" type="number" />
          </Field>
          <Field label="Emissor *">
            <Inp k="emissor" placeholder="Razão social do emissor" />
          </Field>
          <Field label="CNPJ Emissor">
            <Inp k="cnpj_emissor" placeholder="00.000.000/0001-00" />
          </Field>
          <Field label="Indexador">
            <Inp k="indexador" placeholder="Ex: CDI, IPCA, IGPM" />
          </Field>
          <Field label="Taxa Adicional">
            <Inp k="taxa_adicional" placeholder="Ex: + 2% a.a." />
          </Field>
          <Field label="Data Início">
            <Inp k="data_inicio_emissao" type="date" />
          </Field>
          <Field label="Data Vencimento Previsto">
            <Inp k="data_vencimento_previsto" type="date" />
          </Field>
          <button className={styles.btnPrimary} onClick={() => salvarEmissao.mutate()} disabled={salvarEmissao.isPending}>
            {salvarEmissao.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {modal === 'debenture' && (
        <Modal title="Nova Posição — Debênture" onClose={closeModal} width={560}>
          <Field label="Cliente *">
            <Sel k="cliente_id" options={clienteOptions} />
          </Field>
          <Field label="Emissão *">
            <Sel k="emissao_id" options={emissoes.map((e: any) => ({ value: e.id, label: `${e.nome_serie} — ${e.emissor}` }))} />
          </Field>
          <Field label="Nº Cautela *">
            <Inp k="numero_cautela" placeholder="Ex: CAU-001" />
          </Field>
          <Field label="Valor Aplicado (R$) *">
            <Inp k="valor_aplicado" type="number" placeholder="Ex: 100000" />
          </Field>
          <Field label="Data de Aquisição *">
            <Inp k="data_aquisicao" type="date" />
          </Field>
          <Field label="Valor Atual Estimado (R$)">
            <Inp k="valor_atual_estimado" type="number" />
          </Field>
          <Field label="Status Resgate">
            <Sel k="status_resgate" options={[
              { value: 'Ativo', label: 'Ativo' },
              { value: 'Resgate Solicitado', label: 'Resgate Solicitado' },
              { value: 'Resgatado', label: 'Resgatado' },
            ]} />
          </Field>
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} />
              Faz parte de honorários
            </label>
          </div>
          {form.faz_parte_honorarios && (
            <Field label="% Sucesso (honorários)">
              <Inp k="percentual_sucesso_honor" type="number" placeholder="Ex: 20" />
            </Field>
          )}
          <button className={styles.btnPrimary} onClick={() => salvarDebenture.mutate()} disabled={salvarDebenture.isPending}>
            {salvarDebenture.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {modal === 'empreendimento' && (
        <Modal title="Novo Empreendimento Imobiliário" onClose={closeModal} width={560}>
          <Field label="Nome de Venda *">
            <Inp k="nome_venda" placeholder="Ex: Residencial Botafogo" />
          </Field>
          <Field label="Razão Social">
            <Inp k="nome_razao_social" />
          </Field>
          <Field label="CNPJ Empreendimento">
            <Inp k="cnpj_empreendimento" placeholder="00.000.000/0001-00" />
          </Field>
          <Field label="Tipo Desenvolvimento">
            <Inp k="tipo_desenvolvimento" placeholder="Ex: Residencial, Loteamento, Logístico" />
          </Field>
          <Field label="Localização">
            <Inp k="localizacao" placeholder="Ex: Rio de Janeiro, RJ" />
          </Field>
          <Field label="Veículo ABM-PARSE">
            <Inp k="abmparse_veiculo" placeholder="Ex: Apex Realty" />
          </Field>
          <button className={styles.btnPrimary} onClick={() => salvarEmpreendimento.mutate()} disabled={salvarEmpreendimento.isPending}>
            {salvarEmpreendimento.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {modal === 'imobiliario' && (
        <Modal title="Nova Posição — Imobiliário" onClose={closeModal} width={560}>
          <Field label="Cliente *">
            <Sel k="cliente_id" options={clienteOptions} />
          </Field>
          <Field label="Empreendimento *">
            <Sel k="empreendimento_id" options={empreendimentos.map((e: any) => ({ value: e.id, label: e.nome_venda }))} />
          </Field>
          <Field label="Valor Total Comprometido (R$) *">
            <Inp k="valor_total_compromissado" type="number" />
          </Field>
          <Field label="Valor Efetivamente Investido (R$) *">
            <Inp k="valor_efetivamente_investido" type="number" />
          </Field>
          <Field label="% Participação">
            <Inp k="percentual_participacao" type="number" placeholder="100" />
          </Field>
          <Field label="Data Primeiro Aporte">
            <Inp k="data_primeiro_aporte" type="date" />
          </Field>
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} />
              Faz parte de honorários
            </label>
          </div>
          {form.faz_parte_honorarios && (
            <Field label="% Sucesso (honorários)">
              <Inp k="percentual_sucesso_honorario" type="number" />
            </Field>
          )}
          <button className={styles.btnPrimary} onClick={() => salvarImobiliario.mutate()} disabled={salvarImobiliario.isPending}>
            {salvarImobiliario.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {modal === 'fundo-ref' && (
        <Modal title="Novo Fundo de Referência" onClose={closeModal} width={520}>
          <Field label="Nome do Fundo *">
            <Inp k="nome_fundo" />
          </Field>
          <Field label="CNPJ do Fundo">
            <Inp k="cnpj_fundo" />
          </Field>
          <Field label="Gestora">
            <Inp k="gestora" />
          </Field>
          <Field label="Administradora">
            <Inp k="administradora" />
          </Field>
          <Field label="Tipo">
            <Inp k="tipo_fundo" placeholder="Ex: FII, FIA, Multimercado, FIDC" />
          </Field>
          <Field label="Indexador">
            <Inp k="indexador" placeholder="Ex: CDI, IPCA" />
          </Field>
          <button className={styles.btnPrimary} onClick={() => salvarFundoRef.mutate()} disabled={salvarFundoRef.isPending}>
            {salvarFundoRef.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {modal === 'fundo' && (
        <Modal title="Nova Posição — Fundo" onClose={closeModal} width={560}>
          <Field label="Cliente *">
            <Sel k="cliente_id" options={clienteOptions} />
          </Field>
          <Field label="Fundo *">
            <Sel k="fundo_id" options={fundosRef.map((f: any) => ({ value: f.id, label: f.nome_fundo }))} />
          </Field>
          <Field label="Valor Aplicado (R$) *">
            <Inp k="valor_aplicado" type="number" />
          </Field>
          <Field label="Data de Aplicação *">
            <Inp k="data_aplicacao" type="date" />
          </Field>
          <Field label="Valor Atual Estimado (R$)">
            <Inp k="valor_atual_estimado" type="number" />
          </Field>
          <Field label="Nº Conta (opcional)">
            <Inp k="numero_conta" />
          </Field>
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} />
              Faz parte de honorários
            </label>
          </div>
          {form.faz_parte_honorarios && (
            <Field label="% Sucesso (honorários)">
              <Inp k="percentual_sucesso_honor" type="number" />
            </Field>
          )}
          <button className={styles.btnPrimary} onClick={() => salvarFundo.mutate()} disabled={salvarFundo.isPending}>
            {salvarFundo.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {modal === 'estrategia' && (
        <Modal title="Nova Estratégia" onClose={closeModal}>
          <Field label="Nome *">
            <Inp k="nome" placeholder="Ex: Conservadora, Agressiva, ABM-PARSE" />
          </Field>
          <Field label="Descrição">
            <textarea className={styles.input} rows={4} value={form.descricao ?? ''} onChange={e => inp('descricao', e.target.value)} />
          </Field>
          <button className={styles.btnPrimary} onClick={() => salvarEstrategia.mutate()} disabled={salvarEstrategia.isPending}>
            {salvarEstrategia.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}
    </div>
  )
}
