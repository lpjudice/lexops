import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/api/client'
import Modal from '@/components/Modal'
import styles from './Page.module.css'
import cs from './Carteira.module.css'

type Tab = 'posicao-cliente' | 'clientes' | 'emissoes' | 'debentures' | 'empreendimentos' | 'imobiliario' | 'fundos-ref' | 'fundos' | 'estrategias'

const brl = (v: number | null | undefined) =>
  `R$ ${(v ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const pct = (v: number | null | undefined) =>
  `${(v ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`

const TABS_POS: { key: Tab; label: string }[] = [
  { key: 'posicao-cliente', label: 'Posição por Cliente' },
  { key: 'debentures', label: 'Debêntures' },
  { key: 'imobiliario', label: 'Imobiliário' },
  { key: 'fundos', label: 'Fundos' },
]
const TABS_REF: { key: Tab; label: string }[] = [
  { key: 'clientes', label: 'Clientes' },
  { key: 'emissoes', label: 'Emissões' },
  { key: 'empreendimentos', label: 'Empreendimentos' },
  { key: 'fundos-ref', label: 'Fundos Ref.' },
  { key: 'estrategias', label: 'Estratégias' },
]

// ── ComboSelect (sincrono — opções já carregadas) ────────────────────
function ComboSelect({
  value, onChange, options, placeholder,
}: {
  value: string | number | null | undefined
  onChange: (v: string | number) => void
  options: { value: string | number; label: string }[]
  placeholder?: string
}) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const selected = options.find(o => String(o.value) === String(value ?? ''))
  const filtered = search.length > 0
    ? options.filter(o => o.label.toLowerCase().includes(search.toLowerCase()))
    : options

  return (
    <div style={{ position: 'relative' }}>
      <input
        className={styles.input}
        value={open ? search : (selected?.label ?? '')}
        placeholder={placeholder ?? '— Selecione ou busque —'}
        onFocus={() => { setOpen(true); setSearch('') }}
        onChange={e => setSearch(e.target.value)}
        onBlur={() => setTimeout(() => setOpen(false), 180)}
      />
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200, background: 'var(--white)', border: '1px solid var(--gray-border)', borderRadius: 6, maxHeight: 220, overflowY: 'auto', boxShadow: '0 8px 24px rgba(0,0,0,0.12)' }}>
          {filtered.length === 0
            ? <div style={{ padding: '10px 14px', color: 'var(--gray-mid)', fontSize: 13 }}>Nenhum resultado</div>
            : filtered.slice(0, 30).map(o => (
              <div key={o.value}
                style={{ padding: '8px 14px', cursor: 'pointer', fontSize: 13, background: String(o.value) === String(value ?? '') ? 'var(--teal-light, #f0fdfa)' : undefined, borderBottom: '1px solid var(--gray-light, #f3f4f6)' }}
                onMouseDown={() => { onChange(o.value); setSearch(''); setOpen(false) }}>
                {o.label}
              </div>
            ))
          }
        </div>
      )}
    </div>
  )
}

// ── Busca assíncrona de clientes do sistema principal ────────────────
function SystemClientCombo({ onSelect }: { onSelect: (c: any) => void }) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const { data: results = [] } = useQuery({
    queryKey: ['sistema-clientes-busca', search],
    queryFn: () => api.get('/clientes', { params: { busca: search, limit: 12 } }).then(r => r.data?.data ?? r.data),
    enabled: search.length >= 2,
    staleTime: 30_000,
  })

  return (
    <div style={{ position: 'relative' }}>
      <input
        ref={inputRef}
        className={styles.input}
        value={search}
        placeholder="Buscar no sistema principal (mín. 2 letras)..."
        onChange={e => { setSearch(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 180)}
      />
      {open && search.length >= 2 && (results as any[]).length > 0 && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200, background: 'var(--white)', border: '1px solid var(--gray-border)', borderRadius: 6, maxHeight: 220, overflowY: 'auto', boxShadow: '0 8px 24px rgba(0,0,0,0.12)' }}>
          {(results as any[]).map((c: any) => (
            <div key={c.id}
              style={{ padding: '8px 14px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid var(--gray-light, #f3f4f6)', display: 'flex', gap: 10, alignItems: 'baseline' }}
              onMouseDown={() => { onSelect(c); setSearch(''); setOpen(false) }}>
              <strong>{c.nome}</strong>
              {c.cpf_cnpj && <span style={{ color: 'var(--gray-mid)', fontSize: 11 }}>{c.cpf_cnpj}</span>}
            </div>
          ))}
        </div>
      )}
      {open && search.length >= 2 && (results as any[]).length === 0 && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200, background: 'var(--white)', border: '1px solid var(--gray-border)', borderRadius: 6, padding: '10px 14px', color: 'var(--gray-mid)', fontSize: 13 }}>
          Nenhum resultado
        </div>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
export default function CarteiraPage() {
  const [tab, setTab] = useState<Tab>('posicao-cliente')
  const [modal, setModal] = useState<string | null>(null)
  const [form, setForm] = useState<Record<string, any>>({})
  const [editandoClienteId, setEditandoClienteId] = useState<number | null>(null)
  const [editandoEmpId, setEditandoEmpId] = useState<number | null>(null)
  const [filtroDebEmissao, setFiltroDebEmissao] = useState<number | ''>('')
  const [filtroImobEmp, setFiltroImobEmp] = useState<number | ''>('')
  const qc = useQueryClient()

  const inp = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }))
  const closeModal = () => { setModal(null); setForm({}); setEditandoClienteId(null); setEditandoEmpId(null) }

  // ── Render helpers (funções, não componentes) ─────────────────────
  // Chamar como {fi('k')} em vez de <Inp k="k" /> — evita unmount/remount a cada re-render
  const fi = (k: string, type = 'text', placeholder = '') => (
    <input className={styles.input} type={type} value={form[k] ?? ''} onChange={e => inp(k, e.target.value)} placeholder={placeholder} />
  )
  const fta = (k: string, rows = 2) => (
    <textarea className={styles.input} rows={rows} value={form[k] ?? ''} onChange={e => inp(k, e.target.value)} />
  )
  const fs = (k: string, opts: { value: string | number; label: string }[]) => (
    <select className={styles.input} value={form[k] ?? ''} onChange={e => inp(k, e.target.value)}>
      <option value="">— Selecione —</option>
      {opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
  const fl = (label: string, content: React.ReactNode) => (
    <div className={styles.formRow}><label className={styles.formLabel}>{label}</label>{content}</div>
  )

  // ── Queries ───────────────────────────────────────────────────────
  const { data: dash } = useQuery({ queryKey: ['carteira-dash'], queryFn: () => api.get('/carteira/dashboard').then(r => r.data) })
  const { data: clientesRes } = useQuery({ queryKey: ['carteira-clientes'], queryFn: () => api.get('/carteira/clientes', { params: { limit: 200 } }).then(r => r.data) })
  const { data: emissoesRef = [] } = useQuery({ queryKey: ['carteira-emissoes'], queryFn: () => api.get('/carteira/emissoes').then(r => r.data) })
  const { data: debenturesRes } = useQuery({ queryKey: ['carteira-debentures'], queryFn: () => api.get('/carteira/debentures', { params: { limit: 500 } }).then(r => r.data) })
  const { data: empreendimentosRef = [] } = useQuery({ queryKey: ['carteira-empreendimentos'], queryFn: () => api.get('/carteira/empreendimentos').then(r => r.data) })
  const { data: imobiliarioRes } = useQuery({ queryKey: ['carteira-imobiliario'], queryFn: () => api.get('/carteira/imobiliario', { params: { limit: 500 } }).then(r => r.data) })
  const { data: fundosRefRes = [] } = useQuery({ queryKey: ['carteira-fundos-ref'], queryFn: () => api.get('/carteira/fundos-referencia').then(r => r.data) })
  const { data: fundosRes } = useQuery({ queryKey: ['carteira-fundos'], queryFn: () => api.get('/carteira/fundos', { params: { limit: 500 } }).then(r => r.data) })
  const { data: estrategiasRes } = useQuery({ queryKey: ['carteira-estrategias'], queryFn: () => api.get('/carteira/estrategias').then(r => r.data) })

  const clientes: any[] = clientesRes?.data ?? []
  const debentures: any[] = debenturesRes?.data ?? []
  const imobiliario: any[] = imobiliarioRes?.data ?? []
  const fundos: any[] = fundosRes?.data ?? []
  const emissoes: any[] = Array.isArray(emissoesRef) ? emissoesRef : []
  const empreendimentos: any[] = Array.isArray(empreendimentosRef) ? empreendimentosRef : []
  const fundosRef: any[] = Array.isArray(fundosRefRes) ? fundosRefRes : []
  const estrategias: any[] = estrategiasRes?.data ?? []

  // ── Lookups ───────────────────────────────────────────────────────
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

  // ── Agrupamentos por cliente ──────────────────────────────────────
  const clientesAtivos = clientes.filter((c: any) => {
    const temAtivos = debentures.some(d => d.cliente_id === c.id) ||
      imobiliario.some(i => i.cliente_id === c.id) ||
      fundos.some(f => f.cliente_id === c.id)
    return temAtivos
  })

  const debenturesPorCliente = (cid: number) => debentures.filter(d => d.cliente_id === cid)
  const imobPorCliente = (cid: number) => imobiliario.filter(i => i.cliente_id === cid)
  const fundosPorCliente2 = (cid: number) => fundos.filter(f => f.cliente_id === cid)

  // ── Filtros ───────────────────────────────────────────────────────
  const debsFiltradas = filtroDebEmissao ? debentures.filter(d => d.emissao_id === Number(filtroDebEmissao)) : debentures
  const imobFiltrado = filtroImobEmp ? imobiliario.filter(i => i.empreendimento_id === Number(filtroImobEmp)) : imobiliario

  // Clientes que têm debs/imob após filtro
  const clientesComDeb = [...new Set(debsFiltradas.map(d => d.cliente_id))]
    .map(cid => ({ id: cid, nome: clienteNome(cid), posicoes: debsFiltradas.filter(d => d.cliente_id === cid) }))
    .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'))

  const clientesComImob = [...new Set(imobFiltrado.map(i => i.cliente_id))]
    .map(cid => ({ id: cid, nome: clienteNome(cid), posicoes: imobFiltrado.filter(i => i.cliente_id === cid) }))
    .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'))

  const clientesComFundos = [...new Set(fundos.map(f => f.cliente_id))]
    .map(cid => ({ id: cid, nome: clienteNome(cid), posicoes: fundos.filter(f => f.cliente_id === cid) }))
    .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'))

  // ── Mutations ─────────────────────────────────────────────────────
  const mk = (url: string, keys: string[], numFields: string[] = []) => useMutation({
    mutationFn: () => {
      const p = { ...form }
      numFields.forEach(k => { if (p[k] !== undefined && p[k] !== '') p[k] = Number(p[k]) })
      return api.post(url, p).then(r => r.data)
    },
    onSuccess: () => { keys.forEach(k => qc.invalidateQueries({ queryKey: [k] })); closeModal() },
    onError: (e: any) => alert(e?.response?.data?.detail || 'Erro ao salvar'),
  })

  const numC = ['pro_labore_valor', 'percentual_sucesso_geral', 'fee_imob_pct', 'fee_fin_pct', 'percentual_sucesso_imob', 'percentual_sucesso_fin']
  const salvarCliente = mk('/carteira/clientes', ['carteira-clientes', 'carteira-dash'], numC)
  const atualizarCliente = useMutation({
    mutationFn: () => {
      const p = { ...form }
      numC.forEach(k => { if (p[k] !== undefined && p[k] !== '') p[k] = Number(p[k]) })
      return api.put(`/carteira/clientes/${editandoClienteId}`, p).then(r => r.data)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['carteira-clientes'] }); qc.invalidateQueries({ queryKey: ['carteira-dash'] }); closeModal() },
    onError: (e: any) => alert(e?.response?.data?.detail || 'Erro ao salvar'),
  })
  const salvarEmissao = mk('/carteira/emissoes', ['carteira-emissoes'], ['numero_emissao'])
  const salvarDebenture = mk('/carteira/debentures', ['carteira-debentures', 'carteira-dash'],
    ['cliente_id', 'emissao_id', 'valor_aplicado', 'valor_atual_estimado', 'percentual_sucesso_honor', 'numero_debentures'])
  const salvarEmpreendimento = mk('/carteira/empreendimentos', ['carteira-empreendimentos'])
  const atualizarEmpreendimento = useMutation({
    mutationFn: () => api.put(`/carteira/empreendimentos/${editandoEmpId}`, form).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['carteira-empreendimentos'] }); closeModal() },
    onError: (e: any) => alert(e?.response?.data?.detail || 'Erro ao salvar'),
  })
  const salvarImobiliario = mk('/carteira/imobiliario', ['carteira-imobiliario', 'carteira-dash'],
    ['cliente_id', 'empreendimento_id', 'valor_total_compromissado', 'valor_efetivamente_investido', 'percentual_participacao', 'percentual_sucesso_honorario'])
  const salvarFundoRef = mk('/carteira/fundos-referencia', ['carteira-fundos-ref'])
  const salvarFundo = mk('/carteira/fundos', ['carteira-fundos', 'carteira-dash'],
    ['cliente_id', 'fundo_id', 'valor_aplicado', 'valor_atual_estimado', 'percentual_sucesso_honor'])
  const salvarEstrategia = mk('/carteira/estrategias', ['carteira-estrategias'])

  // ── Abrir edições ─────────────────────────────────────────────────
  const abrirEdicaoCliente = (c: any) => {
    const nomeAtual = c.nome ?? (c.observacoes?.startsWith('[IMPORTADO XLS] ') ? c.observacoes.replace('[IMPORTADO XLS] ', '') : '')
    setForm({
      nome: nomeAtual, tipo_pessoa: c.tipo_pessoa ?? 'PF', cpf: c.cpf ?? '',
      email: c.email ?? '', telefone: c.telefone ?? '',
      pro_labore_tipo: c.pro_labore_tipo ?? '', pro_labore_valor: c.pro_labore_valor ?? '',
      fee_imob_pct: c.fee_imob_pct ?? '', fee_fin_pct: c.fee_fin_pct ?? '',
      percentual_sucesso_geral: c.percentual_sucesso_geral ?? '',
      percentual_sucesso_imob: c.percentual_sucesso_imob ?? '',
      percentual_sucesso_fin: c.percentual_sucesso_fin ?? '',
      exito_split: !!(c.percentual_sucesso_imob || c.percentual_sucesso_fin),
      cliente_uuid: c.cliente_uuid ?? '', observacoes: c.observacoes ?? '', ativo: c.ativo ?? true,
    })
    setEditandoClienteId(c.id)
    setModal('cliente')
  }

  const abrirEdicaoEmp = (e: any) => {
    setForm({
      nome_venda: e.nome_venda, prestadora_nome: e.prestadora_nome ?? 'Apex Realty',
      prestadora_cnpj: e.prestadora_cnpj ?? '', nome_razao_social: e.nome_razao_social ?? '',
      cnpj_empreendimento: e.cnpj_empreendimento ?? '', spe_nome: e.spe_nome ?? '',
      spe_cnpj: e.spe_cnpj ?? '', subveiculos: e.subveiculos ?? [],
      tipo_desenvolvimento: e.tipo_desenvolvimento ?? '', localizacao: e.localizacao ?? '',
      descricao: e.descricao ?? '', ativo: e.ativo,
    })
    setEditandoEmpId(e.id)
    setModal('empreendimento')
  }

  // ── UI helpers ────────────────────────────────────────────────────
  const clienteOptions = clientes.map((c: any) => ({ value: c.id, label: clienteNome(c.id) }))
  const emptyMsg = (msg = 'Nenhum registro') => (
    <div style={{ textAlign: 'center', padding: '40px 24px', color: '#9ca3af', fontSize: 14 }}>{msg}</div>
  )
  const statusBadge = (s: string | boolean) => {
    if (s === true || s === 'Ativo' || s === 'Ativa') return <span className={`${styles.badge} ${styles.status_ativo}`}>{s === true ? 'Ativo' : s}</span>
    if (s === false || s === 'Inativo') return <span className={`${styles.badge} ${styles.status_arquivado}`}>{s === false ? 'Inativo' : s}</span>
    if (s === 'Resgate Solicitado') return <span className={`${styles.badge} ${styles.status_suspenso}`}>{s}</span>
    if (s === 'Resgatado') return <span className={`${styles.badge} ${styles.status_encerrado}`}>{s}</span>
    return <span className={styles.badge}>{String(s)}</span>
  }
  const addBtn = (label: string, onClick: () => void) => (
    <div className={styles.pageHeader} style={{ marginBottom: 12 }}>
      <span /><button className={styles.btnPrimary} onClick={onClick}>+ {label}</button>
    </div>
  )
  const editBtn = (onClick: () => void) => (
    <button style={{ background: 'none', border: '1px solid var(--gray-border)', borderRadius: 4, padding: '3px 10px', cursor: 'pointer', fontSize: 12, color: 'var(--gray-mid)' }} onClick={onClick}>Editar</button>
  )

  // PDF export
  const exportarPdfCliente = (cid: number) => {
    window.open(`/api/carteira/cliente/${cid}/pdf`, '_blank')
  }

  return (
    <div style={{ padding: '24px 28px' }}>
      <div className={styles.pageHeader}><h1 className={styles.pageTitle}>Carteira</h1></div>

      {/* KPI Cards */}
      <div className={cs.kpiGrid}>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Clientes</span><span className={cs.kpiValue}>{dash?.total_clientes ?? 0}</span></div>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Carteira Total</span><span className={cs.kpiValue}>{brl(dash?.carteira_total)}</span></div>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Valor Atual</span><span className={cs.kpiValue}>{brl(dash?.valor_atual_total)}</span></div>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Fee Entrada (total)</span><span className={cs.kpiValue}>{brl(dash?.pro_labore_mensal)}</span></div>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Expectativa Êxito</span><span className={cs.kpiValue}>{brl(dash?.expectativa_honorarios)}</span></div>
      </div>

      {/* Tab Bar */}
      <div className={cs.tabBar}>
        <span className={cs.tabGroupLabel + ' ' + cs.tabGroupLabelCarteira}>Carteira</span>
        {TABS_POS.map(t => (
          <button key={t.key} className={`${cs.tabBtn} ${tab === t.key ? cs.tabBtnActive : ''}`} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
        <span className={cs.tabGroupLabel + ' ' + cs.tabGroupLabelRef} style={{ marginLeft: 8 }}>Referência</span>
        {TABS_REF.map(t => (
          <button key={t.key} className={`${cs.tabBtn} ${tab === t.key ? cs.tabBtnActive : ''}`} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>

      {/* ══ POSIÇÃO POR CLIENTE ═══════════════════════════════════ */}
      {tab === 'posicao-cliente' && (
        <>
          {clientesAtivos.length === 0
            ? emptyMsg('Nenhum cliente com ativos cadastrados')
            : clientesAtivos
              .map((c: any) => {
                const nome = clienteNome(c.id)
                const debs = debenturesPorCliente(c.id)
                const imobs = imobPorCliente(c.id)
                const fnds = fundosPorCliente2(c.id)
                const totalAplicado = [...debs, ...imobs, ...fnds].reduce((s, p) => s + (p.valor_aplicado ?? p.valor_total_compromissado ?? 0), 0)
                const totalAtual = [...debs, ...imobs, ...fnds].reduce((s, p) => s + (p.valor_atual_estimado ?? p.valor_efetivamente_investido ?? p.valor_aplicado ?? p.valor_total_compromissado ?? 0), 0)
                return (
                  <div key={c.id} className={cs.clientePosicaoCard}>
                    <div className={cs.clientePosicaoHeader}>
                      <div>
                        <span className={cs.clientePosicaoNome}>{nome}</span>
                        <span className={cs.clientePosicaoTotal}>
                          {brl(totalAplicado)} aplicado · {brl(totalAtual)} atual
                        </span>
                      </div>
                      <button className={styles.btnSmall} onClick={() => exportarPdfCliente(c.id)}>PDF</button>
                    </div>

                    {debs.length > 0 && (
                      <div className={cs.posicaoSecao}>
                        <div className={cs.posicaoSecaoTitulo}>Debêntures ({debs.length})</div>
                        <table className={styles.table} style={{ marginBottom: 0 }}>
                          <thead><tr><th>Cautela</th><th>Emissão</th><th>Aplicado</th><th>Atual</th><th>Status</th></tr></thead>
                          <tbody>
                            {debs.map(d => (
                              <tr key={d.id}>
                                <td>{d.numero_cautela}</td>
                                <td>{emissaoNome(d.emissao_id)}</td>
                                <td>{brl(d.valor_aplicado)}</td>
                                <td>{d.valor_atual_estimado ? brl(d.valor_atual_estimado) : '—'}</td>
                                <td>{statusBadge(d.status_resgate)}</td>
                              </tr>
                            ))}
                            <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                              <td colSpan={2}>Total debêntures</td>
                              <td>{brl(debs.reduce((s, d) => s + (d.valor_aplicado ?? 0), 0))}</td>
                              <td>{brl(debs.reduce((s, d) => s + (d.valor_atual_estimado ?? d.valor_aplicado ?? 0), 0))}</td>
                              <td />
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    )}

                    {imobs.length > 0 && (
                      <div className={cs.posicaoSecao}>
                        <div className={cs.posicaoSecaoTitulo}>Imobiliário ({imobs.length})</div>
                        <table className={styles.table} style={{ marginBottom: 0 }}>
                          <thead><tr><th>Empreendimento</th><th>Comprometido</th><th>Investido</th><th>% Part.</th></tr></thead>
                          <tbody>
                            {imobs.map(i => (
                              <tr key={i.id}>
                                <td>{empreendimentoNome(i.empreendimento_id)}</td>
                                <td>{brl(i.valor_total_compromissado)}</td>
                                <td>{brl(i.valor_efetivamente_investido)}</td>
                                <td>{pct(i.percentual_participacao)}</td>
                              </tr>
                            ))}
                            <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                              <td>Total imobiliário</td>
                              <td>{brl(imobs.reduce((s, i) => s + (i.valor_total_compromissado ?? 0), 0))}</td>
                              <td>{brl(imobs.reduce((s, i) => s + (i.valor_efetivamente_investido ?? 0), 0))}</td>
                              <td />
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    )}

                    {fnds.length > 0 && (
                      <div className={cs.posicaoSecao}>
                        <div className={cs.posicaoSecaoTitulo}>Fundos ({fnds.length})</div>
                        <table className={styles.table} style={{ marginBottom: 0 }}>
                          <thead><tr><th>Fundo</th><th>Aplicado</th><th>Atual</th><th>Recompra</th></tr></thead>
                          <tbody>
                            {fnds.map(f => (
                              <tr key={f.id}>
                                <td>{fundoNome(f.fundo_id)}</td>
                                <td>{brl(f.valor_aplicado)}</td>
                                <td>{f.valor_atual_estimado ? brl(f.valor_atual_estimado) : '—'}</td>
                                <td>{f.tem_direito_recompra ? <span className={`${styles.badge} ${styles.status_suspenso}`}>Recompra</span> : '—'}</td>
                              </tr>
                            ))}
                            <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                              <td>Total fundos</td>
                              <td>{brl(fnds.reduce((s, f) => s + (f.valor_aplicado ?? 0), 0))}</td>
                              <td>{brl(fnds.reduce((s, f) => s + (f.valor_atual_estimado ?? f.valor_aplicado ?? 0), 0))}</td>
                              <td />
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )
              })
              .sort((a: any, b: any) => (a.key > b.key ? 1 : -1))
          }
        </>
      )}

      {/* ══ DEBÊNTURES (agrupado por cliente, com filtro) ══════════ */}
      {tab === 'debentures' && (
        <>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
            {addBtn('Nova Posição', () => { setForm({ status_resgate: 'Ativo', faz_parte_honorarios: false }); setModal('debenture') })}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
              <label style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Filtrar emissão:</label>
              <select className={styles.input} style={{ width: 220 }} value={filtroDebEmissao}
                onChange={e => setFiltroDebEmissao(e.target.value ? Number(e.target.value) : '')}>
                <option value="">Todas</option>
                {emissoes.map(e => <option key={e.id} value={e.id}>{e.nome_serie} — {e.emissor}</option>)}
              </select>
            </div>
          </div>
          {clientesComDeb.length === 0
            ? emptyMsg()
            : clientesComDeb.map(g => (
              <div key={g.id} className={cs.clienteFundoGroup}>
                <div className={cs.clienteFundoNome}>{g.nome}</div>
                <table className={styles.table} style={{ marginBottom: 0 }}>
                  <thead><tr><th>Cautela</th><th>Emissão</th><th>Aplicado</th><th>Atual</th><th>Status</th><th>Êxito %</th></tr></thead>
                  <tbody>
                    {g.posicoes.map((d: any) => (
                      <tr key={d.id}>
                        <td><strong>{d.numero_cautela}</strong></td>
                        <td>{emissaoNome(d.emissao_id)}</td>
                        <td>{brl(d.valor_aplicado)}</td>
                        <td>{d.valor_atual_estimado ? brl(d.valor_atual_estimado) : '—'}</td>
                        <td>{statusBadge(d.status_resgate)}</td>
                        <td>{d.faz_parte_honorarios ? pct(d.percentual_sucesso_honor) : '—'}</td>
                      </tr>
                    ))}
                    <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                      <td colSpan={2}>Total</td>
                      <td>{brl(g.posicoes.reduce((s: number, d: any) => s + (d.valor_aplicado ?? 0), 0))}</td>
                      <td>{brl(g.posicoes.reduce((s: number, d: any) => s + (d.valor_atual_estimado ?? d.valor_aplicado ?? 0), 0))}</td>
                      <td /><td />
                    </tr>
                  </tbody>
                </table>
              </div>
            ))
          }
        </>
      )}

      {/* ══ IMOBILIÁRIO (agrupado por cliente, com filtro) ═════════ */}
      {tab === 'imobiliario' && (
        <>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
            {addBtn('Nova Posição', () => { setForm({ percentual_participacao: 100, faz_parte_honorarios: false }); setModal('imobiliario') })}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
              <label style={{ fontSize: 12, color: 'var(--gray-mid)' }}>Filtrar empreendimento:</label>
              <select className={styles.input} style={{ width: 260 }} value={filtroImobEmp}
                onChange={e => setFiltroImobEmp(e.target.value ? Number(e.target.value) : '')}>
                <option value="">Todos</option>
                {empreendimentos.map(e => <option key={e.id} value={e.id}>{e.nome_venda}</option>)}
              </select>
            </div>
          </div>
          {clientesComImob.length === 0
            ? emptyMsg()
            : clientesComImob.map(g => (
              <div key={g.id} className={cs.clienteFundoGroup}>
                <div className={cs.clienteFundoNome}>{g.nome}</div>
                <table className={styles.table} style={{ marginBottom: 0 }}>
                  <thead><tr><th>Empreendimento</th><th>Comprometido</th><th>Investido</th><th>% Part.</th><th>Êxito %</th></tr></thead>
                  <tbody>
                    {g.posicoes.map((i: any) => (
                      <tr key={i.id}>
                        <td>{empreendimentoNome(i.empreendimento_id)}</td>
                        <td>{brl(i.valor_total_compromissado)}</td>
                        <td>{brl(i.valor_efetivamente_investido)}</td>
                        <td>{pct(i.percentual_participacao)}</td>
                        <td>{i.faz_parte_honorarios ? pct(i.percentual_sucesso_honorario) : '—'}</td>
                      </tr>
                    ))}
                    <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                      <td>Total</td>
                      <td>{brl(g.posicoes.reduce((s: number, i: any) => s + (i.valor_total_compromissado ?? 0), 0))}</td>
                      <td>{brl(g.posicoes.reduce((s: number, i: any) => s + (i.valor_efetivamente_investido ?? 0), 0))}</td>
                      <td /><td />
                    </tr>
                  </tbody>
                </table>
              </div>
            ))
          }
        </>
      )}

      {/* ══ FUNDOS (agrupado por cliente, com totais) ══════════════ */}
      {tab === 'fundos' && (
        <>
          {addBtn('Nova Posição', () => { setForm({ faz_parte_honorarios: false }); setModal('fundo') })}
          {clientesComFundos.length === 0
            ? emptyMsg()
            : clientesComFundos.map(g => (
              <div key={g.id} className={cs.clienteFundoGroup}>
                <div className={cs.clienteFundoNome}>{g.nome}</div>
                <table className={styles.table} style={{ marginBottom: 0 }}>
                  <thead><tr><th>Fundo</th><th>Aplicado</th><th>Atual</th><th>Data</th><th>Recompra</th><th>Êxito %</th></tr></thead>
                  <tbody>
                    {g.posicoes.map((f: any) => (
                      <tr key={f.id}>
                        <td><strong>{fundoNome(f.fundo_id)}</strong></td>
                        <td>{brl(f.valor_aplicado)}</td>
                        <td>{f.valor_atual_estimado ? brl(f.valor_atual_estimado) : '—'}</td>
                        <td>{f.data_aplicacao ?? '—'}</td>
                        <td>{f.tem_direito_recompra ? <span className={`${styles.badge} ${styles.status_suspenso}`}>Recompra</span> : '—'}</td>
                        <td>{f.faz_parte_honorarios ? pct(f.percentual_sucesso_honor) : '—'}</td>
                      </tr>
                    ))}
                    <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                      <td>Total</td>
                      <td>{brl(g.posicoes.reduce((s: number, f: any) => s + (f.valor_aplicado ?? 0), 0))}</td>
                      <td>{brl(g.posicoes.reduce((s: number, f: any) => s + (f.valor_atual_estimado ?? f.valor_aplicado ?? 0), 0))}</td>
                      <td colSpan={3} />
                    </tr>
                  </tbody>
                </table>
              </div>
            ))
          }
        </>
      )}

      {/* ══ CLIENTES (referência) ══════════════════════════════════ */}
      {tab === 'clientes' && (
        <>
          {addBtn('Novo Cliente', () => { setForm({ pro_labore_tipo: '', tipo_pessoa: 'PF', exito_split: false }); setEditandoClienteId(null); setModal('cliente') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead><tr><th>Nome</th><th>Tipo</th><th>CPF/CNPJ</th><th>Fee entrada</th><th>% Êxito</th><th>Status</th><th /></tr></thead>
              <tbody>
                {clientes.length === 0
                  ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : clientes.map((c: any) => {
                    const temFee = c.pro_labore_tipo && c.pro_labore_tipo !== 'nenhum'
                    const feeLabel = c.pro_labore_tipo === 'percentual'
                      ? (c.fee_imob_pct || c.fee_fin_pct ? `${c.fee_imob_pct ?? 0}% imob / ${c.fee_fin_pct ?? 0}% fin` : `${c.pro_labore_valor ?? 0}%`)
                      : c.pro_labore_valor ? brl(c.pro_labore_valor) : '—'
                    const exitoLabel = c.percentual_sucesso_imob || c.percentual_sucesso_fin
                      ? `${c.percentual_sucesso_imob ?? 0}% imob / ${c.percentual_sucesso_fin ?? 0}% fin`
                      : c.percentual_sucesso_geral ? pct(c.percentual_sucesso_geral) : '—'
                    return (
                      <tr key={c.id}>
                        <td><strong>{clienteNome(c.id)}</strong></td>
                        <td><span className={styles.badge}>{c.tipo_pessoa ?? 'PF'}</span></td>
                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{c.cpf ?? '—'}</td>
                        <td>{temFee ? feeLabel : '—'}</td>
                        <td>{exitoLabel}</td>
                        <td>{statusBadge(c.ativo)}</td>
                        <td>{editBtn(() => abrirEdicaoCliente(c))}</td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ══ EMISSÕES ══════════════════════════════════════════════ */}
      {tab === 'emissoes' && (
        <>
          {addBtn('Nova Emissão', () => { setForm({ numero_emissao: 1 }); setModal('emissao') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead><tr><th>Série</th><th>Nº</th><th>Emissor</th><th>Indexador</th><th>Vencimento</th><th>Status</th></tr></thead>
              <tbody>
                {emissoes.length === 0
                  ? <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : emissoes.map((e: any) => (
                    <tr key={e.id}>
                      <td><strong>{e.nome_serie}</strong></td><td>{e.numero_emissao}ª</td>
                      <td>{e.emissor}</td>
                      <td>{e.indexador}{e.taxa_adicional ? ` + ${e.taxa_adicional}` : ''}</td>
                      <td>{e.data_vencimento_previsto ?? '—'}</td><td>{statusBadge(e.ativo)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ══ EMPREENDIMENTOS ═══════════════════════════════════════ */}
      {tab === 'empreendimentos' && (
        <>
          {addBtn('Novo Empreendimento', () => { setForm({ prestadora_nome: 'Apex Realty', subveiculos: [] }); setEditandoEmpId(null); setModal('empreendimento') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead><tr><th>Projeto</th><th>Veículo (Razão Social)</th><th>CNPJ Veículo</th><th>Prestadora</th><th>Sub-veículos</th><th>Status</th><th /></tr></thead>
              <tbody>
                {empreendimentos.length === 0
                  ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : empreendimentos.map((e: any) => (
                    <tr key={e.id}>
                      <td><strong>{e.nome_venda}</strong></td>
                      <td style={{ fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.nome_razao_social ?? '—'}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{e.cnpj_empreendimento ?? '—'}</td>
                      <td style={{ fontSize: 12 }}>{e.prestadora_nome ?? 'Apex Realty'}</td>
                      <td style={{ fontSize: 12 }}>{(e.subveiculos?.length ?? 0) > 0 ? `${e.subveiculos.length} sub-veículo(s)` : '—'}</td>
                      <td>{statusBadge(e.ativo)}</td>
                      <td>{editBtn(() => abrirEdicaoEmp(e))}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ══ FUNDOS REF ════════════════════════════════════════════ */}
      {tab === 'fundos-ref' && (
        <>
          {addBtn('Novo Fundo', () => { setForm({}); setModal('fundo-ref') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead><tr><th>Nome</th><th>CNPJ</th><th>Gestora</th><th>Tipo</th><th>Indexador</th><th>Status</th></tr></thead>
              <tbody>
                {fundosRef.length === 0
                  ? <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : fundosRef.map((f: any) => (
                    <tr key={f.id}>
                      <td><strong>{f.nome_fundo}</strong></td><td>{f.cnpj_fundo ?? '—'}</td>
                      <td>{f.gestora ?? '—'}</td><td>{f.tipo_fundo ?? '—'}</td>
                      <td>{f.indexador ?? '—'}</td><td>{statusBadge(f.ativo)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ══ ESTRATÉGIAS ═══════════════════════════════════════════ */}
      {tab === 'estrategias' && (
        <>
          {addBtn('Nova Estratégia', () => { setForm({ publico: true }); setModal('estrategia') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead><tr><th>Nome</th><th>Descrição</th><th>Usos</th><th>Status</th></tr></thead>
              <tbody>
                {estrategias.length === 0
                  ? <tr><td colSpan={4} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : estrategias.map((e: any) => (
                    <tr key={e.id}>
                      <td><strong>{e.nome}</strong></td>
                      <td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.descricao ?? '—'}</td>
                      <td>{e.usuarios_count ?? 0}</td><td>{statusBadge(e.ativo)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ════════════════ MODAIS ════════════════════════════════════ */}

      {/* ── MODAL CLIENTE ────────────────────────────────────────── */}
      {modal === 'cliente' && (
        <Modal title={editandoClienteId ? `Editar — ${clienteNome(editandoClienteId)}` : 'Novo cliente na carteira'} onClose={closeModal} width={580}>

          {/* Vincular cliente */}
          <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 6, padding: '10px 14px', marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>
              Vincular a cliente do sistema ou carteira
            </div>
            {/* combobox clientes já na carteira */}
            <div style={{ marginBottom: 6 }}>
              <ComboSelect
                value={null}
                onChange={v => {
                  const c = clientes.find((x: any) => x.id === Number(v))
                  if (!c) return
                  const n = c.nome ?? (c.observacoes?.startsWith('[IMPORTADO XLS] ') ? c.observacoes.replace('[IMPORTADO XLS] ', '') : '')
                  setForm(f => ({ ...f, nome: n || f.nome, cpf: c.cpf ?? f.cpf, email: c.email ?? f.email, telefone: c.telefone ?? f.telefone, tipo_pessoa: c.tipo_pessoa ?? f.tipo_pessoa, cliente_uuid: c.cliente_uuid ?? f.cliente_uuid }))
                }}
                options={clienteOptions}
                placeholder="Selecionar cliente já cadastrado na carteira..."
              />
            </div>
            {/* busca sistema principal */}
            <SystemClientCombo onSelect={c => {
              setForm(f => ({
                ...f,
                nome: c.nome ?? f.nome, cpf: c.cpf_cnpj ?? f.cpf,
                email: c.email ?? f.email, telefone: c.telefone ?? f.telefone,
                tipo_pessoa: c.tipo === 'PF' ? 'PF' : 'PJ', cliente_uuid: c.id,
              }))
            }} />
            {form.cliente_uuid && (
              <div style={{ fontSize: 11, color: 'var(--teal, #0d9488)', marginTop: 4 }}>
                ✓ Vinculado ao sistema
                <button style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-mid)', fontSize: 11 }} onClick={() => inp('cliente_uuid', '')}>remover</button>
              </div>
            )}
          </div>

          {fl('Nome completo *', fi('nome', 'text', 'Nome do investidor'))}
          {fl('Tipo pessoa', fs('tipo_pessoa', [{ value: 'PF', label: 'PF — Pessoa Física' }, { value: 'PJ', label: 'PJ — Pessoa Jurídica' }]))}
          {fl(form.tipo_pessoa === 'PJ' ? 'CNPJ' : 'CPF', fi('cpf', 'text', form.tipo_pessoa === 'PJ' ? '00.000.000/0001-00' : '000.000.000-00'))}
          {form.tipo_pessoa !== 'PJ' && fl('Estado civil', fs('estado_civil', [
            { value: 'solteiro', label: 'Solteiro(a)' }, { value: 'casado', label: 'Casado(a)' },
            { value: 'uniao_estavel', label: 'União estável' }, { value: 'divorciado', label: 'Divorciado(a)' }, { value: 'viuvo', label: 'Viúvo(a)' },
          ]))}
          {form.tipo_pessoa !== 'PJ' && fl('Profissão', fi('profissao', 'text', 'Ex: Empresário, Médico'))}
          {form.tipo_pessoa === 'PJ' && fl('Representante legal', fi('representante_nome'))}
          {fl('E-mail', fi('email', 'email'))}
          {fl('Telefone', fi('telefone', 'text', '(27) 9 9999-9999'))}

          {/* Fee de entrada */}
          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '12px 0 0', paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Fee de entrada</div>
            {fl('Tipo de fee', fs('pro_labore_tipo', [
              { value: '', label: 'Sem fee de entrada' },
              { value: 'fixo', label: 'Valor fixo (R$)' },
              { value: 'percentual', label: 'Percentual do investimento (%)' },
            ]))}
            {form.pro_labore_tipo === 'fixo' && fl('Valor (R$)', fi('pro_labore_valor', 'number', 'Ex: 10000'))}
            {form.pro_labore_tipo === 'percentual' && (
              <>
                {fl('% sobre ativos imobiliários', fi('fee_imob_pct', 'number', 'Ex: 2'))}
                {fl('% sobre ativos financeiros (deb./fundos)', fi('fee_fin_pct', 'number', 'Ex: 2'))}
              </>
            )}
          </div>

          {/* Fee de êxito */}
          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '12px 0 0', paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Honorários de êxito</div>
            <div className={styles.formRow}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={!!form.exito_split} onChange={e => inp('exito_split', e.target.checked)} />
                % diferente por tipo de ativo
              </label>
            </div>
            {!form.exito_split && fl('% êxito (geral)', fi('percentual_sucesso_geral', 'number', 'Ex: 20'))}
            {form.exito_split && (
              <>
                {fl('% êxito imobiliário', fi('percentual_sucesso_imob', 'number', 'Ex: 20'))}
                {fl('% êxito financeiro (deb./fundos)', fi('percentual_sucesso_fin', 'number', 'Ex: 20'))}
              </>
            )}
          </div>

          <div style={{ marginTop: 12 }}>
            {fl('Observações', fta('observacoes', 2))}
            {editandoClienteId && fl('Status', fs('ativo', [{ value: 'true', label: 'Ativo' }, { value: 'false', label: 'Inativo' }]))}
          </div>

          <button className={styles.btnPrimary}
            onClick={() => editandoClienteId ? atualizarCliente.mutate() : salvarCliente.mutate()}
            disabled={salvarCliente.isPending || atualizarCliente.isPending}>
            {(salvarCliente.isPending || atualizarCliente.isPending) ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {/* ── MODAL EMPREENDIMENTO ─────────────────────────────────── */}
      {modal === 'empreendimento' && (
        <Modal title={editandoEmpId ? `Editar — ${form.nome_venda}` : 'Novo Empreendimento'} onClose={closeModal} width={600}>
          {fl('Nome do projeto *', fi('nome_venda', 'text', 'Ex: Apex Realty I | Tranche 1'))}

          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>Cadeia estrutural</div>
            {fl('Prestadora de serviços', fi('prestadora_nome', 'text', 'Apex Realty'))}
            {fl('CNPJ da prestadora', fi('prestadora_cnpj', 'text', '00.000.000/0001-00'))}
            {fl('Razão social do veículo (ABMPARSE)', fi('nome_razao_social', 'text', 'ABMPARSPE 12 PARTICIPACOES LTDA'))}
            {fl('CNPJ do veículo', fi('cnpj_empreendimento', 'text', '00.000.000/0001-00'))}
            {fl('SPE executora (se diferente do veículo)', fi('spe_nome', 'text', 'Nome da SPE'))}
            {fl('CNPJ da SPE', fi('spe_cnpj', 'text', '00.000.000/0001-00'))}
          </div>

          {/* Sub-veículos (SCPs, cotas etc.) */}
          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                Sub-veículos ({(form.subveiculos ?? []).length})
              </span>
              <button className={styles.btnSmall} onClick={() => inp('subveiculos', [...(form.subveiculos ?? []), { nome: '', cnpj: '', tipo: 'SCP' }])}>
                + Adicionar
              </button>
            </div>
            {(form.subveiculos ?? []).map((sv: any, idx: number) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 120px 32px', gap: 6, marginBottom: 6, alignItems: 'end' }}>
                <div><label style={{ fontSize: 11, color: 'var(--gray-mid)' }}>Nome</label>
                  <input className={styles.input} value={sv.nome} placeholder="Nome do sub-veículo"
                    onChange={e => { const s = [...form.subveiculos]; s[idx] = { ...sv, nome: e.target.value }; inp('subveiculos', s) }} /></div>
                <div><label style={{ fontSize: 11, color: 'var(--gray-mid)' }}>CNPJ</label>
                  <input className={styles.input} value={sv.cnpj} placeholder="00.000.000/0001-00"
                    onChange={e => { const s = [...form.subveiculos]; s[idx] = { ...sv, cnpj: e.target.value }; inp('subveiculos', s) }} /></div>
                <div><label style={{ fontSize: 11, color: 'var(--gray-mid)' }}>Tipo</label>
                  <select className={styles.input} value={sv.tipo}
                    onChange={e => { const s = [...form.subveiculos]; s[idx] = { ...sv, tipo: e.target.value }; inp('subveiculos', s) }}>
                    <option value="SCP">SCP</option><option value="SPE">SPE</option>
                    <option value="Cota">Cota</option><option value="Outro">Outro</option>
                  </select></div>
                <button style={{ background: 'none', border: '1px solid var(--red, #ef4444)', color: 'var(--red, #ef4444)', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 12 }}
                  onClick={() => inp('subveiculos', form.subveiculos.filter((_: any, i: number) => i !== idx))}>✕</button>
              </div>
            ))}
          </div>

          {fl('Tipo desenvolvimento', fi('tipo_desenvolvimento', 'text', 'Ex: Residencial, Loteamento'))}
          {fl('Localização', fi('localizacao', 'text', 'Ex: Vitória, ES'))}
          {fl('Descrição', fta('descricao', 2))}

          <button className={styles.btnPrimary}
            onClick={() => editandoEmpId ? atualizarEmpreendimento.mutate() : salvarEmpreendimento.mutate()}
            disabled={salvarEmpreendimento.isPending || atualizarEmpreendimento.isPending}>
            {(salvarEmpreendimento.isPending || atualizarEmpreendimento.isPending) ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {/* ── MODAL EMISSÃO ─────────────────────────────────────────── */}
      {modal === 'emissao' && (
        <Modal title="Nova Emissão de Debênture" onClose={closeModal} width={520}>
          {fl('Nome da Série *', fi('nome_serie', 'text', 'Ex: APEX I'))}
          {fl('Nº da Emissão *', fi('numero_emissao', 'number'))}
          {fl('Emissor *', fi('emissor', 'text', 'Razão social do emissor'))}
          {fl('CNPJ Emissor', fi('cnpj_emissor', 'text', '00.000.000/0001-00'))}
          {fl('Indexador', fi('indexador', 'text', 'Ex: CDI, IPCA'))}
          {fl('Taxa Adicional', fi('taxa_adicional', 'text', 'Ex: + 2% a.a.'))}
          {fl('Data Início', fi('data_inicio_emissao', 'date'))}
          {fl('Data Vencimento Previsto', fi('data_vencimento_previsto', 'date'))}
          <button className={styles.btnPrimary} onClick={() => salvarEmissao.mutate()} disabled={salvarEmissao.isPending}>{salvarEmissao.isPending ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}

      {/* ── MODAL DEBÊNTURE ──────────────────────────────────────── */}
      {modal === 'debenture' && (
        <Modal title="Nova Posição — Debênture" onClose={closeModal} width={520}>
          {fl('Cliente *', <ComboSelect value={form.cliente_id} onChange={v => inp('cliente_id', Number(v))} options={clienteOptions} placeholder="Selecione o cliente..." />)}
          {fl('Emissão *', <ComboSelect value={form.emissao_id} onChange={v => inp('emissao_id', Number(v))} options={emissoes.map((e: any) => ({ value: e.id, label: `${e.nome_serie} — ${e.emissor}` }))} placeholder="Selecione a emissão..." />)}
          {fl('Nº Cautela *', fi('numero_cautela', 'text', 'Ex: CAU-001'))}
          {fl('Valor Aplicado (R$) *', fi('valor_aplicado', 'number'))}
          {fl('Data de Aquisição *', fi('data_aquisicao', 'date'))}
          {fl('Valor Atual Estimado (R$)', fi('valor_atual_estimado', 'number'))}
          {fl('Status Resgate', fs('status_resgate', [{ value: 'Ativo', label: 'Ativo' }, { value: 'Resgate Solicitado', label: 'Resgate Solicitado' }, { value: 'Resgatado', label: 'Resgatado' }]))}
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} />
              Faz parte de honorários de êxito
            </label>
          </div>
          {form.faz_parte_honorarios && fl('% Êxito', fi('percentual_sucesso_honor', 'number', 'Ex: 20'))}
          <button className={styles.btnPrimary} onClick={() => salvarDebenture.mutate()} disabled={salvarDebenture.isPending}>{salvarDebenture.isPending ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}

      {/* ── MODAL IMOBILIÁRIO ────────────────────────────────────── */}
      {modal === 'imobiliario' && (
        <Modal title="Nova Posição — Imobiliário" onClose={closeModal} width={520}>
          {fl('Cliente *', <ComboSelect value={form.cliente_id} onChange={v => inp('cliente_id', Number(v))} options={clienteOptions} placeholder="Selecione o cliente..." />)}
          {fl('Empreendimento *', <ComboSelect value={form.empreendimento_id} onChange={v => inp('empreendimento_id', Number(v))} options={empreendimentos.map((e: any) => ({ value: e.id, label: e.nome_venda }))} placeholder="Selecione o empreendimento..." />)}
          {fl('Valor Total Comprometido (R$) *', fi('valor_total_compromissado', 'number'))}
          {fl('Valor Efetivamente Investido (R$) *', fi('valor_efetivamente_investido', 'number'))}
          {fl('% Participação', fi('percentual_participacao', 'number', '100'))}
          {fl('Data Primeiro Aporte', fi('data_primeiro_aporte', 'date'))}
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} />
              Faz parte de honorários de êxito
            </label>
          </div>
          {form.faz_parte_honorarios && fl('% Êxito', fi('percentual_sucesso_honorario', 'number'))}
          <button className={styles.btnPrimary} onClick={() => salvarImobiliario.mutate()} disabled={salvarImobiliario.isPending}>{salvarImobiliario.isPending ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}

      {/* ── MODAL FUNDO REF ──────────────────────────────────────── */}
      {modal === 'fundo-ref' && (
        <Modal title="Novo Fundo de Referência" onClose={closeModal} width={480}>
          {fl('Nome do Fundo *', fi('nome_fundo'))}
          {fl('CNPJ do Fundo', fi('cnpj_fundo'))}
          {fl('Gestora', fi('gestora'))}
          {fl('Administradora', fi('administradora'))}
          {fl('Tipo', fi('tipo_fundo', 'text', 'Ex: FII, FIA, Multimercado, FIDC'))}
          {fl('Indexador', fi('indexador', 'text', 'Ex: CDI, IPCA'))}
          <button className={styles.btnPrimary} onClick={() => salvarFundoRef.mutate()} disabled={salvarFundoRef.isPending}>{salvarFundoRef.isPending ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}

      {/* ── MODAL FUNDO POSIÇÃO ──────────────────────────────────── */}
      {modal === 'fundo' && (
        <Modal title="Nova Posição — Fundo" onClose={closeModal} width={520}>
          {fl('Cliente *', <ComboSelect value={form.cliente_id} onChange={v => inp('cliente_id', Number(v))} options={clienteOptions} placeholder="Selecione o cliente..." />)}
          {fl('Fundo *', <ComboSelect value={form.fundo_id} onChange={v => inp('fundo_id', Number(v))} options={fundosRef.map((f: any) => ({ value: f.id, label: f.nome_fundo }))} placeholder="Selecione o fundo..." />)}
          {fl('Valor Aplicado (R$) *', fi('valor_aplicado', 'number'))}
          {fl('Data de Aplicação *', fi('data_aplicacao', 'date'))}
          {fl('Valor Atual Estimado (R$)', fi('valor_atual_estimado', 'number'))}
          {fl('Nº Conta (opcional)', fi('numero_conta'))}
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} />
              Faz parte de honorários de êxito
            </label>
          </div>
          {form.faz_parte_honorarios && fl('% Êxito', fi('percentual_sucesso_honor', 'number'))}
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.tem_direito_recompra} onChange={e => inp('tem_direito_recompra', e.target.checked)} />
              Tem direito de recompra
            </label>
          </div>
          {form.tem_direito_recompra && fl('Data vencimento recompra', fi('data_vencimento_recompra', 'date'))}
          <button className={styles.btnPrimary} onClick={() => salvarFundo.mutate()} disabled={salvarFundo.isPending}>{salvarFundo.isPending ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}

      {/* ── MODAL ESTRATÉGIA ─────────────────────────────────────── */}
      {modal === 'estrategia' && (
        <Modal title="Nova Estratégia" onClose={closeModal}>
          {fl('Nome *', fi('nome', 'text', 'Ex: Conservadora, ABM-PARSE'))}
          {fl('Descrição', fta('descricao', 4))}
          <button className={styles.btnPrimary} onClick={() => salvarEstrategia.mutate()} disabled={salvarEstrategia.isPending}>{salvarEstrategia.isPending ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}
    </div>
  )
}
