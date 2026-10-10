import React, { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/api/client'
import Modal from '@/components/Modal'
import { useAuth } from '@/contexts/AuthContext'
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
  { key: 'emissoes', label: 'Emissões DB' },
  { key: 'empreendimentos', label: 'Empreendimentos' },
  { key: 'fundos-ref', label: 'Fundos Ref.' },
  { key: 'estrategias', label: 'Estratégias' },
]

// ── ComboSelect (síncrono, fecha ao selecionar) ─────────────────────
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

// ── MultiSelect dropdown (fica aberto ao marcar) ─────────────────────
function MultiSelect({
  values, onChange, options, placeholder,
}: {
  values: (string | number)[]
  onChange: (vs: (string | number)[]) => void
  options: { value: string | number; label: string }[]
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const filtered = search.length > 0
    ? options.filter(o => o.label.toLowerCase().includes(search.toLowerCase()))
    : options
  const label = values.length === 0
    ? (placeholder ?? 'Todos')
    : values.length === 1
    ? (options.find(o => String(o.value) === String(values[0]))?.label ?? '')
    : `${values.length} selecionados`
  const toggle = (v: string | number) => {
    const sv = String(v)
    onChange(values.map(String).includes(sv) ? values.filter(x => String(x) !== sv) : [...values, v])
  }

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <div className={styles.input}
        style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingRight: 28, userSelect: 'none', minHeight: 34 }}
        onClick={() => setOpen(o => !o)} tabIndex={0}>
        <span style={{ color: values.length === 0 ? 'var(--gray-mid)' : 'inherit', fontSize: 13 }}>{label}</span>
        <span style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', fontSize: 10 }}>{open ? '▴' : '▾'}</span>
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200, background: 'var(--white)', border: '1px solid var(--gray-border)', borderRadius: 6, maxHeight: 260, overflowY: 'auto', boxShadow: '0 8px 24px rgba(0,0,0,0.12)' }}>
          <div style={{ padding: '6px 8px', borderBottom: '1px solid var(--gray-border)', position: 'sticky', top: 0, background: 'var(--white)', zIndex: 1 }}>
            <input className={styles.input} style={{ fontSize: 12, padding: '4px 8px' }} placeholder="Buscar..." value={search}
              onChange={e => setSearch(e.target.value)} onClick={e => e.stopPropagation()} autoFocus />
          </div>
          {values.length > 0 && (
            <div style={{ padding: '6px 14px', cursor: 'pointer', fontSize: 12, color: 'var(--teal)', borderBottom: '1px solid var(--gray-border)' }}
              onClick={() => onChange([])}>✕ Limpar seleção</div>
          )}
          {filtered.length === 0
            ? <div style={{ padding: '10px 14px', color: 'var(--gray-mid)', fontSize: 13 }}>Sem resultados</div>
            : filtered.slice(0, 40).map(o => {
              const sel = values.map(String).includes(String(o.value))
              return (
                <div key={o.value}
                  style={{ padding: '7px 14px', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, background: sel ? 'var(--teal-light, #f0fdfa)' : undefined, borderBottom: '1px solid var(--gray-light, #f3f4f6)' }}
                  onClick={() => toggle(o.value)}>
                  <input type="checkbox" readOnly checked={sel} style={{ cursor: 'pointer', accentColor: 'var(--teal)' }} />
                  {o.label}
                </div>
              )
            })
          }
        </div>
      )}
    </div>
  )
}

// ── Busca unificada: carteira (local) + sistema principal (async) — portal ──
function UnifiedClientCombo({
  onSelect,
  localClientes,
}: {
  onSelect: (c: { nome: string; cpf?: string; email?: string; telefone?: string; tipo_pessoa?: string; cliente_uuid?: any }) => void
  localClientes: { id: number; nome: string; cpf?: string; email?: string; telefone?: string; tipo_pessoa?: string; cliente_uuid?: any }[]
}) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [sistemResults, setSistemResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const inputRef = useRef<HTMLInputElement>(null)
  const [dropStyle, setDropStyle] = useState<React.CSSProperties>({})

  const localFiltered = search.length >= 2
    ? localClientes.filter(c => c.nome.toLowerCase().includes(search.toLowerCase())).slice(0, 6)
    : []

  const buscar = async (s: string) => {
    if (s.length < 2) { setSistemResults([]); return }
    setLoading(true)
    try {
      const r = await api.get('/clientes/', { params: { busca: s, limit: 20 } })
      const data = Array.isArray(r.data) ? r.data : (r.data?.data ?? [])
      const localCpfs = new Set(localClientes.map(c => c.cpf).filter(Boolean))
      setSistemResults(data.filter((x: any) => !localCpfs.has(x.cpf_cnpj)))
    } catch { setSistemResults([]) }
    finally { setLoading(false) }
  }

  const calcStyle = () => {
    if (!inputRef.current) return
    const rect = inputRef.current.getBoundingClientRect()
    setDropStyle({ position: 'fixed', top: rect.bottom + 2, left: rect.left, width: Math.max(rect.width, 320), zIndex: 9999, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, maxHeight: 320, overflowY: 'auto', boxShadow: '0 8px 24px rgba(0,0,0,0.14)' })
  }

  const handleChange = (s: string) => {
    setSearch(s); calcStyle(); setOpen(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => buscar(s), 300)
  }

  return (
    <>
      <input ref={inputRef} className={styles.input} value={search}
        placeholder="Buscar cliente por nome (carteira + sistema)..."
        onChange={e => handleChange(e.target.value)}
        onFocus={() => { if (search.length >= 2) { calcStyle(); setOpen(true) } }}
        onBlur={() => setTimeout(() => setOpen(false), 200)} />
      {open && createPortal(
        <div style={dropStyle}>
          {search.length < 2 && <div style={{ padding: '10px 14px', color: '#6b7280', fontSize: 12 }}>Digite pelo menos 2 letras</div>}
          {localFiltered.length > 0 && (
            <>
              <div style={{ padding: '3px 14px', fontSize: 10, fontWeight: 700, color: '#0d9488', textTransform: 'uppercase', letterSpacing: '0.06em', background: '#f0fdfa', borderBottom: '1px solid #e5e7eb' }}>Carteira</div>
              {localFiltered.map(c => (
                <div key={`loc-${c.id}`}
                  style={{ padding: '7px 14px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid #f3f4f6', display: 'flex', gap: 8, alignItems: 'baseline' }}
                  onMouseDown={() => { onSelect({ nome: c.nome, cpf: c.cpf, email: c.email, telefone: c.telefone, tipo_pessoa: c.tipo_pessoa, cliente_uuid: c.cliente_uuid }); setSearch(''); setOpen(false); setSistemResults([]) }}>
                  <strong>{c.nome}</strong>
                  {c.cpf && <span style={{ color: '#6b7280', fontSize: 11 }}>{c.cpf}</span>}
                </div>
              ))}
            </>
          )}
          {loading && <div style={{ padding: '10px 14px', color: '#6b7280', fontSize: 13 }}>Buscando no sistema...</div>}
          {!loading && sistemResults.length > 0 && (
            <>
              <div style={{ padding: '3px 14px', fontSize: 10, fontWeight: 700, color: '#6366f1', textTransform: 'uppercase', letterSpacing: '0.06em', background: '#f5f3ff', borderBottom: '1px solid #e5e7eb' }}>Sistema</div>
              {sistemResults.map((c: any) => (
                <div key={`sis-${c.id}`}
                  style={{ padding: '7px 14px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid #f3f4f6', display: 'flex', gap: 8, alignItems: 'baseline' }}
                  onMouseDown={() => { onSelect({ nome: c.nome, cpf: c.cpf_cnpj, email: c.email, telefone: c.telefone, tipo_pessoa: c.tipo === 'PF' ? 'PF' : 'PJ', cliente_uuid: c.id }); setSearch(''); setOpen(false); setSistemResults([]) }}>
                  <strong>{c.nome}</strong>
                  {c.cpf_cnpj && <span style={{ color: '#6b7280', fontSize: 11 }}>{c.cpf_cnpj}</span>}
                </div>
              ))}
            </>
          )}
          {!loading && search.length >= 2 && localFiltered.length === 0 && sistemResults.length === 0 && (
            <div style={{ padding: '10px 14px', color: '#6b7280', fontSize: 13 }}>Nenhum resultado para "{search}"</div>
          )}
        </div>,
        document.body
      )}
    </>
  )
}

// ── Chips de estratégia por linha de posição ──────────────────────
function EstrategiaChips({
  ids, estrategias, onUpdate,
}: {
  ids: number[]; estrategias: any[]; onUpdate: (newIds: number[]) => void
}) {
  const [showAdd, setShowAdd] = useState(false)
  const [selectedEst, setSelectedEst] = useState<any | null>(null)
  const [dropStyle, setDropStyle] = useState<React.CSSProperties>({})
  const btnRef = useRef<HTMLButtonElement>(null)

  const current = ids.map(id => estrategias.find(e => e.id === id)).filter(Boolean)
  const available = estrategias.filter(e => !ids.includes(e.id))

  const openAdd = () => {
    if (!btnRef.current) return
    const rect = btnRef.current.getBoundingClientRect()
    setDropStyle({ position: 'fixed', top: rect.bottom + 2, left: rect.left, minWidth: 200, maxWidth: 300, zIndex: 9999, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, maxHeight: 200, overflowY: 'auto', boxShadow: '0 8px 24px rgba(0,0,0,0.12)' })
    setShowAdd(s => !s)
  }

  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center' }}>
        {current.map((est: any) => (
          <span key={est.id}
            title={est.descricao || est.nome}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 2, background: '#f0fdfa', border: '1px solid #0d9488', borderRadius: 10, padding: '1px 7px 1px 8px', fontSize: 10, cursor: 'pointer', color: '#0d6b63', whiteSpace: 'nowrap' }}
            onClick={() => setSelectedEst(est)}>
            {est.nome_chip || est.nome}
            <button
              style={{ marginLeft: 2, cursor: 'pointer', fontSize: 13, color: '#6b7280', lineHeight: 1, background: 'none', border: 'none', padding: '0 1px', borderRadius: 2 }}
              onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); onUpdate(ids.filter(x => x !== est.id)) }}>×</button>
          </span>
        ))}
        <button ref={btnRef}
          style={{ background: 'none', border: '1px dashed #d1d5db', borderRadius: 10, padding: '1px 7px', fontSize: 10, cursor: 'pointer', color: '#9ca3af', lineHeight: 1.5 }}
          onClick={openAdd}>+</button>
      </div>
      {showAdd && createPortal(
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 9998 }} onClick={() => setShowAdd(false)} />
          <div style={dropStyle}>
            {available.length === 0
              ? <div style={{ padding: '10px 14px', color: '#9ca3af', fontSize: 12 }}>Todas selecionadas</div>
              : available.map((e: any) => (
                <div key={e.id}
                  style={{ padding: '8px 14px', cursor: 'pointer', fontSize: 12, borderBottom: '1px solid #f3f4f6', display: 'flex', flexDirection: 'column' }}
                  onMouseDown={() => { onUpdate([...ids, e.id]); setShowAdd(false) }}>
                  <strong>{e.nome}</strong>
                  {e.descricao && <span style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{e.descricao}</span>}
                </div>
              ))
            }
          </div>
        </>,
        document.body
      )}
      {selectedEst && (
        <Modal title={selectedEst.nome} onClose={() => setSelectedEst(null)} width={380}>
          <p style={{ fontSize: 13, lineHeight: 1.6 }}>{selectedEst.descricao || 'Sem descrição cadastrada.'}</p>
        </Modal>
      )}
    </>
  )
}

// ────────────────────────────────────────────────────────────────────
export default function CarteiraPage() {
  const [tab, setTab] = useState<Tab>('posicao-cliente')
  const [modal, setModal] = useState<string | null>(null)
  const [form, setForm] = useState<Record<string, any>>({})
  const [editandoClienteId, setEditandoClienteId] = useState<number | null>(null)
  const [editandoEmpId, setEditandoEmpId] = useState<number | null>(null)
  const [editandoDebId, setEditandoDebId] = useState<number | null>(null)
  const [editandoImobId, setEditandoImobId] = useState<number | null>(null)
  const [editandoFundoId, setEditandoFundoId] = useState<number | null>(null)
  // Filtros multi-select por ativo
  const [filtroDebEmissoes, setFiltroDebEmissoes] = useState<(string | number)[]>([])
  const [filtroImobEmps, setFiltroImobEmps] = useState<(string | number)[]>([])
  const [filtroFundosFundos, setFiltroFundosFundos] = useState<(string | number)[]>([])
  // Filtros por cliente
  const [filtroClienteDeb, setFiltroClienteDeb] = useState('')
  const [filtroClienteImob, setFiltroClienteImob] = useState('')
  const [filtroClienteFundos, setFiltroClienteFundos] = useState('')
  const [filtroClientePos, setFiltroClientePos] = useState('')
  // Filtro tipo de ativo em Posição por Cliente
  const [mostrarDebs, setMostrarDebs] = useState(true)
  const [mostrarImob, setMostrarImob] = useState(true)
  const [mostrarFundosPOS, setMostrarFundosPOS] = useState(true)
  // Debênture info modal
  const [debInfoId, setDebInfoId] = useState<number | null>(null)
  // Edit states for reference tabs
  const [editandoEmissaoId, setEditandoEmissaoId] = useState<number | null>(null)
  const [editandoFundoRefId, setEditandoFundoRefId] = useState<number | null>(null)
  const [editandoEstrategiaId, setEditandoEstrategiaId] = useState<number | null>(null)
  // Resgate antecipado modal
  const [resgateDebId, setResgateDebId] = useState<number | null>(null)
  // Drive modal
  const [driveClienteId, setDriveClienteId] = useState<number | null>(null)
  const [driveArquivos, setDriveArquivos] = useState<any[]>([])
  const [driveCarregando, setDriveCarregando] = useState(false)
  // Cadeia societária modal
  const [cadeiaEmpId, setCadeiaEmpId] = useState<number | null>(null)

  const { isSuperAdmin } = useAuth()
  const qc = useQueryClient()
  const inp = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }))
  const closeModal = () => {
    setModal(null); setForm({})
    setEditandoClienteId(null); setEditandoEmpId(null)
    setEditandoDebId(null); setEditandoImobId(null); setEditandoFundoId(null)
    setEditandoEmissaoId(null); setEditandoFundoRefId(null); setEditandoEstrategiaId(null)
  }

  // ── Render helpers ────────────────────────────────────────────────
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

  // ── KPIs calculados no frontend ────────────────────────────────────
  const calcularHonorarios = (c: any) => {
    const debs = debentures.filter(d => d.cliente_id === c.id)
    const imobs = imobiliario.filter(i => i.cliente_id === c.id)
    const fnds = fundos.filter(f => f.cliente_id === c.id)
    const totalFin = [...debs, ...fnds].reduce((s, p) => s + (p.valor_aplicado ?? 0), 0)
    const totalImob = imobs.reduce((s, p) => s + (p.valor_total_compromissado ?? 0), 0)
    const totalGeral = totalFin + totalImob
    let feeEntrada = 0
    if (c.pro_labore_tipo === 'fixo') feeEntrada = c.pro_labore_valor ?? 0
    else if (c.pro_labore_tipo === 'percentual')
      feeEntrada = totalImob * ((c.fee_imob_pct ?? 0) / 100) + totalFin * ((c.fee_fin_pct ?? 0) / 100)
    let exito = 0
    if (c.percentual_sucesso_imob || c.percentual_sucesso_fin)
      exito = totalImob * ((c.percentual_sucesso_imob ?? 0) / 100) + totalFin * ((c.percentual_sucesso_fin ?? 0) / 100)
    else if (c.percentual_sucesso_geral)
      exito = totalGeral * ((c.percentual_sucesso_geral ?? 0) / 100)
    return { totalGeral, totalFin, totalImob, feeEntrada, exito }
  }

  const kpiImob = imobiliario.reduce((s, i) => s + (i.valor_total_compromissado ?? 0), 0)
  const kpiFin = [...debentures, ...fundos].reduce((s, p) => s + (p.valor_aplicado ?? 0), 0)
  const kpiTotal = kpiImob + kpiFin
  const kpiFeeEntrada = clientes.reduce((s, c) => s + calcularHonorarios(c).feeEntrada, 0)
  const kpiExito = clientes.reduce((s, c) => s + calcularHonorarios(c).exito, 0)

  // ── CNPJ duplicado em empreendimentos ──────────────────────────────
  const cnpjCount: Record<string, number> = {}
  empreendimentos.forEach(e => {
    if (e.cnpj_empreendimento) cnpjCount[e.cnpj_empreendimento] = (cnpjCount[e.cnpj_empreendimento] || 0) + 1
  })

  // ── Filtros ────────────────────────────────────────────────────────
  const filtrarPorNome = (nome: string, busca: string) =>
    !busca || nome.toLowerCase().includes(busca.toLowerCase())

  const debsFiltradas = debentures.filter(d =>
    filtroDebEmissoes.length === 0 || filtroDebEmissoes.map(String).includes(String(d.emissao_id))
  )
  const imobFiltrado = imobiliario.filter(i =>
    filtroImobEmps.length === 0 || filtroImobEmps.map(String).includes(String(i.empreendimento_id))
  )
  const fundosFiltrados = fundos.filter(f =>
    filtroFundosFundos.length === 0 || filtroFundosFundos.map(String).includes(String(f.fundo_id))
  )

  const clientesComDeb = [...new Set(debsFiltradas.map(d => d.cliente_id))]
    .map(cid => ({ id: cid, nome: clienteNome(cid), posicoes: debsFiltradas.filter(d => d.cliente_id === cid) }))
    .filter(g => filtrarPorNome(g.nome, filtroClienteDeb))
    .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'))

  const clientesComImob = [...new Set(imobFiltrado.map(i => i.cliente_id))]
    .map(cid => ({ id: cid, nome: clienteNome(cid), posicoes: imobFiltrado.filter(i => i.cliente_id === cid) }))
    .filter(g => filtrarPorNome(g.nome, filtroClienteImob))
    .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'))

  const clientesComFundos = [...new Set(fundosFiltrados.map(f => f.cliente_id))]
    .map(cid => ({ id: cid, nome: clienteNome(cid), posicoes: fundosFiltrados.filter(f => f.cliente_id === cid) }))
    .filter(g => filtrarPorNome(g.nome, filtroClienteFundos))
    .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'))

  const clientesAtivos = clientes
    .filter((c: any) =>
      debentures.some(d => d.cliente_id === c.id) ||
      imobiliario.some(i => i.cliente_id === c.id) ||
      fundos.some(f => f.cliente_id === c.id)
    )
    .filter((c: any) => filtrarPorNome(clienteNome(c.id), filtroClientePos))
    .sort((a: any, b: any) => clienteNome(a.id).localeCompare(clienteNome(b.id), 'pt-BR'))

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
  const mkPut = (urlFn: () => string, keys: string[], numFields: string[] = []) => useMutation({
    mutationFn: () => {
      const p = { ...form }
      numFields.forEach(k => { if (p[k] !== undefined && p[k] !== '') p[k] = Number(p[k]) })
      return api.put(urlFn(), p).then(r => r.data)
    },
    onSuccess: () => { keys.forEach(k => qc.invalidateQueries({ queryKey: [k] })); closeModal() },
    onError: (e: any) => alert(e?.response?.data?.detail || 'Erro ao salvar'),
  })

  const numC = ['pro_labore_valor', 'percentual_sucesso_geral', 'fee_imob_pct', 'fee_fin_pct', 'percentual_sucesso_imob', 'percentual_sucesso_fin']
  const salvarCliente = mk('/carteira/clientes', ['carteira-clientes'], numC)
  const atualizarCliente = mkPut(() => `/carteira/clientes/${editandoClienteId}`, ['carteira-clientes'], numC)

  const salvarEmissao = mk('/carteira/emissoes', ['carteira-emissoes'], ['numero_emissao'])

  const numDeb = ['cliente_id', 'emissao_id', 'valor_aplicado', 'valor_atual_estimado', 'percentual_sucesso_honor', 'numero_debentures', 'valor_pago']
  const salvarDebenture = mk('/carteira/debentures', ['carteira-debentures'], numDeb)
  const atualizarDebenture = mkPut(() => `/carteira/debentures/${editandoDebId}`, ['carteira-debentures'], numDeb)

  const salvarEmpreendimento = mk('/carteira/empreendimentos', ['carteira-empreendimentos'])
  const atualizarEmpreendimento = mkPut(() => `/carteira/empreendimentos/${editandoEmpId}`, ['carteira-empreendimentos'])

  const numImob = ['cliente_id', 'empreendimento_id', 'valor_total_compromissado', 'valor_efetivamente_investido', 'percentual_participacao', 'percentual_sucesso_honorario']
  const salvarImobiliario = mk('/carteira/imobiliario', ['carteira-imobiliario'], numImob)
  const atualizarImobiliario = mkPut(() => `/carteira/imobiliario/${editandoImobId}`, ['carteira-imobiliario'], numImob)

  const salvarFundoRef = mk('/carteira/fundos-referencia', ['carteira-fundos-ref'])

  const numFundo = ['cliente_id', 'fundo_id', 'valor_aplicado', 'valor_atual_estimado', 'percentual_sucesso_honor']
  const salvarFundo = mk('/carteira/fundos', ['carteira-fundos'], numFundo)
  const atualizarFundo = mkPut(() => `/carteira/fundos/${editandoFundoId}`, ['carteira-fundos'], numFundo)

  const salvarEstrategia = mk('/carteira/estrategias', ['carteira-estrategias'])
  const atualizarEmissao = mkPut(() => `/carteira/emissoes/${editandoEmissaoId}`, ['carteira-emissoes'], ['numero_emissao'])
  const atualizarFundoRef = mkPut(() => `/carteira/fundos-referencia/${editandoFundoRefId}`, ['carteira-fundos-ref'])
  const atualizarEstrategia = mkPut(() => `/carteira/estrategias/${editandoEstrategiaId}`, ['carteira-estrategias'])

  const patchEstratDeb = useMutation({
    mutationFn: ({ id, ids }: { id: number; ids: number[] }) =>
      api.put(`/carteira/debentures/${id}`, { estrategia_ids: ids }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['carteira-debentures'] }),
  })
  const patchEstratImob = useMutation({
    mutationFn: ({ id, ids }: { id: number; ids: number[] }) =>
      api.put(`/carteira/imobiliario/${id}`, { estrategia_ids: ids }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['carteira-imobiliario'] }),
  })
  const patchEstratFundo = useMutation({
    mutationFn: ({ id, ids }: { id: number; ids: number[] }) =>
      api.put(`/carteira/fundos/${id}`, { estrategia_ids: ids }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['carteira-fundos'] }),
  })

  const processarDocumento = useMutation({
    mutationFn: ({ file, tipo }: { file: File; tipo: string }) => {
      const fd = new FormData(); fd.append('file', file)
      return api.post(`/carteira/processar-documento?tipo=${tipo}`, fd).then(r => r.data)
    },
    onSuccess: (data) => {
      if (data.dados_extraidos) setForm(f => ({ ...f, ...data.dados_extraidos }))
      alert('Documento processado! Verifique os campos preenchidos.')
    },
    onError: (e: any) => alert(e?.response?.data?.detail || 'Erro ao processar documento'),
  })

  const criarPastaDrive = useMutation({
    mutationFn: (clienteId: number) =>
      api.post(`/carteira/criar-pasta-drive?cliente_id=${clienteId}`).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['carteira-clientes'] }) },
    onError: (e: any) => alert(e?.response?.data?.detail || 'Erro ao criar pasta Drive'),
  })

  const carregarArquivosDrive = async (clienteId: number) => {
    setDriveCarregando(true)
    try {
      const r = await api.get(`/carteira/listar-arquivos-drive?cliente_id=${clienteId}`)
      setDriveArquivos(r.data.arquivos ?? [])
    } catch {
      setDriveArquivos([])
    } finally {
      setDriveCarregando(false)
    }
  }

  const uploadDriveFile = async (clienteId: number, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    await api.post(`/carteira/upload-para-drive?cliente_id=${clienteId}`, fd)
    await carregarArquivosDrive(clienteId)
  }

  const exportarXlsx = async () => {
    const ids = clientes.map((c: any) => c.id)
    const res = await api.post('/carteira/exportar-qualificacao?formato=xlsx', ids, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = 'qualificacao_carteira.xlsx'; a.click()
    URL.revokeObjectURL(url)
  }

  // ── Abrir edições ─────────────────────────────────────────────────
  const abrirEdicaoCliente = (c: any) => {
    const nome = c.nome ?? (c.observacoes?.startsWith('[IMPORTADO XLS] ') ? c.observacoes.replace('[IMPORTADO XLS] ', '') : '')
    setForm({
      nome, tipo_pessoa: c.tipo_pessoa ?? 'PF', cpf: c.cpf ?? '',
      email: c.email ?? '', telefone: c.telefone ?? '',
      rg: c.rg ?? '', nacionalidade: c.nacionalidade ?? '',
      estado_civil: c.estado_civil ?? '', profissao: c.profissao ?? '', endereco: c.endereco ?? '',
      representante_nome: c.representante_nome ?? '', representante_cpf: c.representante_cpf ?? '',
      representante_rg: c.representante_rg ?? '', representante_nacionalidade: c.representante_nacionalidade ?? '',
      representante_estado_civil: c.representante_estado_civil ?? '', representante_profissao: c.representante_profissao ?? '',
      representante_endereco: c.representante_endereco ?? '',
      pro_labore_tipo: c.pro_labore_tipo ?? '', pro_labore_valor: c.pro_labore_valor ?? '',
      fee_imob_pct: c.fee_imob_pct ?? '', fee_fin_pct: c.fee_fin_pct ?? '',
      percentual_sucesso_geral: c.percentual_sucesso_geral ?? '',
      percentual_sucesso_imob: c.percentual_sucesso_imob ?? '', percentual_sucesso_fin: c.percentual_sucesso_fin ?? '',
      exito_split: !!(c.percentual_sucesso_imob || c.percentual_sucesso_fin),
      cliente_uuid: c.cliente_uuid ?? '', observacoes: c.observacoes ?? '', ativo: c.ativo ?? true,
    })
    setEditandoClienteId(c.id); setModal('cliente')
  }
  const abrirEdicaoEmp = (e: any) => {
    setForm({ nome_venda: e.nome_venda, prestadora_nome: e.prestadora_nome ?? 'Apex Realty',
      prestadora_cnpj: e.prestadora_cnpj ?? '', nome_razao_social: e.nome_razao_social ?? '',
      cnpj_empreendimento: e.cnpj_empreendimento ?? '', spe_nome: e.spe_nome ?? '', spe_cnpj: e.spe_cnpj ?? '',
      subveiculos: e.subveiculos ?? [], tipo_desenvolvimento: e.tipo_desenvolvimento ?? '',
      localizacao: e.localizacao ?? '', descricao: e.descricao ?? '', ativo: e.ativo })
    setEditandoEmpId(e.id); setModal('empreendimento')
  }
  const pctExitoFin = (clienteId: number) => {
    const c = clientes.find((x: any) => x.id === clienteId)
    return c ? (c.percentual_sucesso_fin ?? c.percentual_sucesso_geral ?? '') : ''
  }
  const pctExitoImob = (clienteId: number) => {
    const c = clientes.find((x: any) => x.id === clienteId)
    return c ? (c.percentual_sucesso_imob ?? c.percentual_sucesso_geral ?? '') : ''
  }

  const abrirEdicaoDeb = (d: any) => {
    setForm({ ...d, faz_parte_honorarios: !!d.faz_parte_honorarios, foi_pago: !!d.foi_pago,
      percentual_sucesso_honor: pctExitoFin(d.cliente_id) })
    setEditandoDebId(d.id); setModal('debenture')
  }
  const abrirEdicaoImob = (i: any) => {
    setForm({ ...i, faz_parte_honorarios: !!i.faz_parte_honorarios,
      percentual_sucesso_honorario: pctExitoImob(i.cliente_id) })
    setEditandoImobId(i.id); setModal('imobiliario')
  }
  const abrirEdicaoFundo = (f: any) => {
    setForm({ ...f, faz_parte_honorarios: !!f.faz_parte_honorarios, tem_direito_recompra: !!f.tem_direito_recompra,
      percentual_sucesso_honor: pctExitoFin(f.cliente_id) })
    setEditandoFundoId(f.id); setModal('fundo')
  }

  const abrirEdicaoEmissao = (e: any) => {
    setForm({ ...e })
    setEditandoEmissaoId(e.id); setModal('emissao')
  }
  const abrirEdicaoFundoRef = (f: any) => {
    setForm({ ...f })
    setEditandoFundoRefId(f.id); setModal('fundo-ref')
  }
  const abrirEdicaoEstrategia = (e: any) => {
    setForm({ ...e })
    setEditandoEstrategiaId(e.id); setModal('estrategia')
  }

  // ── Qualificação para clipboard ────────────────────────────────────
  const qualificacaoTexto = (c: any): string => {
    const nome = clienteNome(c.id)
    if (c.tipo_pessoa === 'PJ') {
      const repParts = [
        c.representante_nome,
        c.representante_nacionalidade,
        c.representante_estado_civil,
        c.representante_profissao,
        c.representante_cpf ? `portador do CPF n. ${c.representante_cpf}` : null,
        c.representante_rg ? `e da Carteira de Identidade n. ${c.representante_rg}` : null,
        c.representante_endereco ? `residente e domiciliado(a) na ${c.representante_endereco}` : null,
      ].filter(Boolean).join(', ')
      return `${nome}, pessoa jurídica de direito privado, registrada sob o CNPJ n. ${c.cpf ?? '—'}, com endereço comercial na ${c.endereco ?? '—'}, representada por ${repParts || '—'}, de email ${c.email ?? '—'}.`
    }
    return [
      nome,
      c.nacionalidade,
      c.estado_civil,
      c.profissao,
      c.cpf ? `portador do CPF n. ${c.cpf}` : null,
      c.rg ? `e da Carteira de Identidade n. ${c.rg}` : null,
      c.endereco ? `residente e domiciliado(a) na ${c.endereco}` : null,
      c.email ? `de email ${c.email}` : null,
    ].filter(Boolean).join(', ') + '.'
  }

  // ── Helpers UI ─────────────────────────────────────────────────────
  const clienteOptions = clientes.map((c: any) => ({ value: c.id, label: clienteNome(c.id) }))

  const localClientesCombos = clientes.map((c: any) => ({
    id: c.id, nome: clienteNome(c.id), cpf: c.cpf ?? '', email: c.email ?? '',
    telefone: c.telefone ?? '', tipo_pessoa: c.tipo_pessoa ?? 'PF', cliente_uuid: c.cliente_uuid ?? null,
  }))

  const resgateAntBadge = (d: any) => {
    const em = emissoes.find(e => e.id === d.emissao_id)
    const emLivre = em?.resgate_antecipado_emissao && em?.resgate_antecipado_tipo === 'desvinculado_lastro'
    const cautelaLivre = d.resgate_antecipado_cautela && d.resgate_antecipado_tipo_cautela === 'desvinculado_lastro'
    if (!em?.resgate_antecipado_emissao && !d.resgate_antecipado_cautela) return null
    const bothFree = emLivre && cautelaLivre
    const oneFree = emLivre || cautelaLivre
    const cor = bothFree ? '#16a34a' : oneFree ? '#d97706' : '#dc2626'
    const bg = bothFree ? '#f0fdf4' : oneFree ? '#fffbeb' : '#fef2f2'
    const label = bothFree ? 'RA✓✓' : oneFree ? 'RA⚠' : 'RA✗'
    const title = bothFree ? 'Resgate antecipado desvinculado do lastro — ambos documentos'
      : oneFree ? 'Resgate antecipado: apenas um documento autoriza desvinculado do lastro'
      : 'Resgate antecipado: nenhum documento autoriza independente do lastro'
    return (
      <span title={title}
        style={{ display: 'inline-block', background: bg, color: cor, border: `1px solid ${cor}`, borderRadius: 8, padding: '1px 6px', fontSize: 9, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}
        onClick={e => { e.stopPropagation(); setResgateDebId(d.id) }}>
        {label}
      </span>
    )
  }

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
  const quickAddBtn = (label: string, onClick: () => void) => (
    <button style={{ background: 'none', border: '1px solid var(--teal)', borderRadius: 4, padding: '2px 8px', cursor: 'pointer', fontSize: 11, color: 'var(--teal)', marginLeft: 6 }} onClick={onClick}>+ {label}</button>
  )

  const filterBar = (extra: React.ReactNode, clienteBusca: string, setClienteBusca: (v: string) => void) => (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 14, flexWrap: 'wrap' }}>
      {extra}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <label style={{ fontSize: 12, color: 'var(--gray-mid)', whiteSpace: 'nowrap' }}>Cliente:</label>
        <input className={styles.input} style={{ width: 200 }} placeholder="Filtrar por nome..." value={clienteBusca} onChange={e => setClienteBusca(e.target.value)} />
      </div>
    </div>
  )

  const emptyGroup = () => (
    <div style={{ textAlign: 'center', padding: '40px 24px', color: '#9ca3af', fontSize: 14 }}>Nenhum registro encontrado</div>
  )

  // Colgroups fixos para alinhamento — Cautela|Emissão|RA|Aplic|Atual|Status|Êxito%|Estratégia|Actions
  const colsDeb = () => (
    <colgroup><col style={{ width: 110 }} /><col /><col style={{ width: 46 }} /><col style={{ width: 130 }} /><col style={{ width: 130 }} /><col style={{ width: 110 }} /><col style={{ width: 65 }} /><col style={{ width: 140 }} /><col style={{ width: 72 }} /></colgroup>
  )
  const colsImob = () => (
    <colgroup><col /><col style={{ width: 140 }} /><col style={{ width: 140 }} /><col style={{ width: 70 }} /><col style={{ width: 65 }} /><col style={{ width: 140 }} /><col style={{ width: 60 }} /></colgroup>
  )
  const colsFundos = () => (
    <colgroup><col /><col style={{ width: 130 }} /><col style={{ width: 130 }} /><col style={{ width: 95 }} /><col style={{ width: 80 }} /><col style={{ width: 65 }} /><col style={{ width: 140 }} /><col style={{ width: 60 }} /></colgroup>
  )
  const thR = (label: string) => <th style={{ textAlign: 'right' }}>{label}</th>

  return (
    <div style={{ padding: '24px 28px' }}>
      <div className={styles.pageHeader}><h1 className={styles.pageTitle}>Carteira</h1></div>

      {/* KPI Cards */}
      <div className={cs.kpiGrid} style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Clientes</span><span className={cs.kpiValue}>{clientes.length}</span></div>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Total Geral</span><span className={cs.kpiValue}>{brl(kpiTotal)}</span></div>
        <div className={cs.kpiCard} style={{ borderTop: '3px solid var(--amber, #f59e0b)' }}><span className={cs.kpiLabel}>Imobiliário</span><span className={cs.kpiValue}>{brl(kpiImob)}</span></div>
        <div className={cs.kpiCard} style={{ borderTop: '3px solid var(--teal)' }}><span className={cs.kpiLabel}>Financeiro</span><span className={cs.kpiValue}>{brl(kpiFin)}</span></div>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Fee Entrada (esp.)</span><span className={cs.kpiValue}>{isSuperAdmin ? brl(kpiFeeEntrada) : '🔒'}</span></div>
        <div className={cs.kpiCard}><span className={cs.kpiLabel}>Expectativa Êxito</span><span className={cs.kpiValue}>{isSuperAdmin ? brl(kpiExito) : '🔒'}</span></div>
      </div>

      {/* Tab Bar */}
      <div className={cs.tabBar}>
        <span className={`${cs.tabGroupLabel} ${cs.tabGroupLabelCarteira}`}>Carteira</span>
        {TABS_POS.map(t => (
          <button key={t.key} className={`${cs.tabBtn} ${tab === t.key ? cs.tabBtnActive : ''}`} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
        <span className={`${cs.tabGroupLabel} ${cs.tabGroupLabelRef}`} style={{ marginLeft: 8 }}>Referência</span>
        {TABS_REF.map(t => (
          <button key={t.key} className={`${cs.tabBtn} ${tab === t.key ? cs.tabBtnActive : ''}`} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>

      {/* ══ POSIÇÃO POR CLIENTE ═══════════════════════════════════ */}
      {tab === 'posicao-cliente' && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 14, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <input className={styles.input} style={{ width: 220 }} placeholder="Filtrar por cliente..." value={filtroClientePos} onChange={e => setFiltroClientePos(e.target.value)} />
              <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, cursor: 'pointer' }}>
                <input type="checkbox" checked={mostrarDebs} onChange={e => setMostrarDebs(e.target.checked)} style={{ accentColor: 'var(--teal)' }} /> Debêntures
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, cursor: 'pointer' }}>
                <input type="checkbox" checked={mostrarImob} onChange={e => setMostrarImob(e.target.checked)} style={{ accentColor: 'var(--amber, #f59e0b)' }} /> Imobiliário
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, cursor: 'pointer' }}>
                <input type="checkbox" checked={mostrarFundosPOS} onChange={e => setMostrarFundosPOS(e.target.checked)} style={{ accentColor: 'var(--blue, #3b82f6)' }} /> Fundos
              </label>
            </div>
            <button className={styles.btnSmall} onClick={exportarXlsx}>Exportar XLSX</button>
          </div>
          {clientesAtivos.length === 0
            ? emptyGroup()
            : clientesAtivos.map((c: any) => {
              const nome = clienteNome(c.id)
              const debs = debentures.filter(d => d.cliente_id === c.id)
              const imobs = imobiliario.filter(i => i.cliente_id === c.id)
              const fnds = fundos.filter(f => f.cliente_id === c.id)
              const { feeEntrada, exito } = calcularHonorarios(c)
              const totalApl = debs.reduce((s, d) => s + (d.valor_aplicado ?? 0), 0) +
                imobs.reduce((s, i) => s + (i.valor_total_compromissado ?? 0), 0) +
                fnds.reduce((s, f) => s + (f.valor_aplicado ?? 0), 0)
              return (
                <div key={c.id} className={cs.clientePosicaoCard}>
                  <div className={cs.clientePosicaoHeader}>
                    <div>
                      <span className={cs.clientePosicaoNome}>{nome}
                        {quickAddBtn('Deb', () => { setForm({ cliente_id: c.id, status_resgate: 'Ativo', faz_parte_honorarios: false, percentual_sucesso_honor: pctExitoFin(c.id) }); setEditandoDebId(null); setModal('debenture') })}
                        {quickAddBtn('Imob', () => { setForm({ cliente_id: c.id, percentual_participacao: 100, faz_parte_honorarios: false, percentual_sucesso_honorario: pctExitoImob(c.id) }); setEditandoImobId(null); setModal('imobiliario') })}
                        {quickAddBtn('Fundo', () => { setForm({ cliente_id: c.id, faz_parte_honorarios: false, percentual_sucesso_honor: pctExitoFin(c.id) }); setEditandoFundoId(null); setModal('fundo') })}
                      </span>
                      <span className={cs.clientePosicaoTotal}>
                        {brl(totalApl)} aplicado
                        {isSuperAdmin && feeEntrada > 0 && ` · Fee: ${brl(feeEntrada)}`}
                        {isSuperAdmin && exito > 0 && ` · Êxito esp.: ${brl(exito)}`}
                      </span>
                    </div>
                    <button className={styles.btnSmall} onClick={() => window.open(`/api/carteira/cliente/${c.id}/pdf`, '_blank')}>PDF</button>
                  </div>

                  {mostrarDebs && debs.length > 0 && (
                    <div className={cs.posicaoSecao}>
                      <div className={cs.posicaoSecaoTitulo}>Debêntures ({debs.length}) · {brl(debs.reduce((s, d) => s + (d.valor_aplicado ?? 0), 0))}</div>
                      <table className={styles.table} style={{ marginBottom: 0 }}>
                        {colsDeb()}
                        <thead><tr><th>Cautela</th><th>Emissão</th><th>RA</th>{thR('Aplicado')}{thR('Atual')}<th>Status</th><th>{isSuperAdmin ? 'Êxito%' : '🔒'}</th><th>Estratégia</th><th /></tr></thead>
                        <tbody>
                          {debs.map(d => (
                            <tr key={d.id}>
                              <td>{d.numero_cautela}</td><td>{emissaoNome(d.emissao_id)}</td>
                              <td>{resgateAntBadge(d)}</td>
                              <td style={{ textAlign: 'right' }}>{brl(d.valor_aplicado)}</td>
                              <td style={{ textAlign: 'right' }}>{d.valor_atual_estimado ? brl(d.valor_atual_estimado) : '—'}</td>
                              <td>{statusBadge(d.status_resgate)}</td>
                              <td>{isSuperAdmin ? (d.faz_parte_honorarios ? pct(d.percentual_sucesso_honor) : '—') : '🔒'}</td>
                              <td><EstrategiaChips ids={d.estrategia_ids ?? []} estrategias={estrategias} onUpdate={ids => patchEstratDeb.mutate({ id: d.id, ids })} /></td>
                              <td style={{ whiteSpace: 'nowrap' }}>
                                <button title="Detalhes" style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#6b7280', padding: '0 3px' }} onClick={() => setDebInfoId(d.id)}>ⓘ</button>
                                {editBtn(() => abrirEdicaoDeb(d))}
                              </td>
                            </tr>
                          ))}
                          <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                            <td colSpan={2}>Total</td>
                            <td />
                            <td style={{ textAlign: 'right' }}>{brl(debs.reduce((s, d) => s + (d.valor_aplicado ?? 0), 0))}</td>
                            <td style={{ textAlign: 'right' }}>{brl(debs.reduce((s, d) => s + (d.valor_atual_estimado ?? d.valor_aplicado ?? 0), 0))}</td>
                            <td /><td /><td /><td />
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  )}

                  {mostrarImob && imobs.length > 0 && (
                    <div className={cs.posicaoSecao}>
                      <div className={cs.posicaoSecaoTitulo}>Imobiliário ({imobs.length}) · {brl(imobs.reduce((s, i) => s + (i.valor_total_compromissado ?? 0), 0))}</div>
                      <table className={styles.table} style={{ marginBottom: 0 }}>
                        {colsImob()}
                        <thead><tr><th>Empreendimento</th>{thR('Comprometido')}{thR('Investido')}<th>% Part.</th><th>{isSuperAdmin ? 'Êxito%' : '🔒'}</th><th>Estratégia</th><th /></tr></thead>
                        <tbody>
                          {imobs.map(i => (
                            <tr key={i.id}>
                              <td>{empreendimentoNome(i.empreendimento_id)}</td>
                              <td style={{ textAlign: 'right' }}>{brl(i.valor_total_compromissado)}</td>
                              <td style={{ textAlign: 'right' }}>{brl(i.valor_efetivamente_investido)}</td>
                              <td>{pct(i.percentual_participacao)}</td>
                              <td>{isSuperAdmin ? (i.faz_parte_honorarios ? pct(i.percentual_sucesso_honorario) : '—') : '🔒'}</td>
                              <td><EstrategiaChips ids={i.estrategia_ids ?? []} estrategias={estrategias} onUpdate={ids => patchEstratImob.mutate({ id: i.id, ids })} /></td>
                              <td>{editBtn(() => abrirEdicaoImob(i))}</td>
                            </tr>
                          ))}
                          <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                            <td>Total</td>
                            <td style={{ textAlign: 'right' }}>{brl(imobs.reduce((s, i) => s + (i.valor_total_compromissado ?? 0), 0))}</td>
                            <td style={{ textAlign: 'right' }}>{brl(imobs.reduce((s, i) => s + (i.valor_efetivamente_investido ?? 0), 0))}</td>
                            <td /><td /><td /><td />
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  )}

                  {mostrarFundosPOS && fnds.length > 0 && (
                    <div className={cs.posicaoSecao}>
                      <div className={cs.posicaoSecaoTitulo}>Fundos ({fnds.length}) · {brl(fnds.reduce((s, f) => s + (f.valor_aplicado ?? 0), 0))}</div>
                      <table className={styles.table} style={{ marginBottom: 0 }}>
                        {colsFundos()}
                        <thead><tr><th>Fundo</th>{thR('Aplicado')}{thR('Atual')}<th>Data</th><th>Recompra</th><th>{isSuperAdmin ? 'Êxito%' : '🔒'}</th><th>Estratégia</th><th /></tr></thead>
                        <tbody>
                          {fnds.map(f => (
                            <tr key={f.id}>
                              <td>{fundoNome(f.fundo_id)}</td>
                              <td style={{ textAlign: 'right' }}>{brl(f.valor_aplicado)}</td>
                              <td style={{ textAlign: 'right' }}>{f.valor_atual_estimado ? brl(f.valor_atual_estimado) : '—'}</td>
                              <td>{f.data_aplicacao ?? '—'}</td>
                              <td>{f.tem_direito_recompra ? <span className={`${styles.badge} ${styles.status_suspenso}`}>Sim</span> : '—'}</td>
                              <td>{isSuperAdmin ? (f.faz_parte_honorarios ? pct(f.percentual_sucesso_honor) : '—') : '🔒'}</td>
                              <td><EstrategiaChips ids={f.estrategia_ids ?? []} estrategias={estrategias} onUpdate={ids => patchEstratFundo.mutate({ id: f.id, ids })} /></td>
                              <td>{editBtn(() => abrirEdicaoFundo(f))}</td>
                            </tr>
                          ))}
                          <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                            <td>Total</td>
                            <td style={{ textAlign: 'right' }}>{brl(fnds.reduce((s, f) => s + (f.valor_aplicado ?? 0), 0))}</td>
                            <td style={{ textAlign: 'right' }}>{brl(fnds.reduce((s, f) => s + (f.valor_atual_estimado ?? f.valor_aplicado ?? 0), 0))}</td>
                            <td colSpan={5} />
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )
            })
          }
        </>
      )}

      {/* ══ DEBÊNTURES ═══════════════════════════════════════════ */}
      {tab === 'debentures' && (
        <>
          {addBtn('Nova Posição', () => { setForm({ status_resgate: 'Ativo', faz_parte_honorarios: false }); setEditandoDebId(null); setModal('debenture') })}
          {filterBar(
            <><label style={{ fontSize: 12, color: 'var(--gray-mid)', whiteSpace: 'nowrap' }}>Emissão:</label>
            <div style={{ width: 260 }}>
              <MultiSelect values={filtroDebEmissoes} onChange={setFiltroDebEmissoes}
                options={emissoes.map(e => ({ value: e.id, label: `${e.nome_serie} — ${e.emissor}` }))} placeholder="Todas as emissões" />
            </div></>,
            filtroClienteDeb, setFiltroClienteDeb,
          )}
          {clientesComDeb.length === 0 ? emptyGroup() : clientesComDeb.map(g => (
            <div key={g.id} className={cs.clienteFundoGroup}>
              <div className={cs.clienteFundoNome} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingRight: 12 }}>
                <span>{g.nome}</span>
                {quickAddBtn('+ Posição', () => { setForm({ cliente_id: g.id, status_resgate: 'Ativo', faz_parte_honorarios: false, percentual_sucesso_honor: pctExitoFin(g.id) }); setEditandoDebId(null); setModal('debenture') })}
              </div>
              <table className={styles.table} style={{ marginBottom: 0 }}>
                {colsDeb()}
                <thead><tr><th>Cautela</th><th>Emissão</th><th>RA</th>{thR('Aplicado')}{thR('Atual')}<th>Status</th><th>{isSuperAdmin ? 'Êxito%' : '🔒'}</th><th>Estratégia</th><th /></tr></thead>
                <tbody>
                  {g.posicoes.map((d: any) => (
                    <tr key={d.id}>
                      <td><strong>{d.numero_cautela}</strong></td><td>{emissaoNome(d.emissao_id)}</td>
                      <td>{resgateAntBadge(d)}</td>
                      <td style={{ textAlign: 'right' }}>{brl(d.valor_aplicado)}</td>
                      <td style={{ textAlign: 'right' }}>{d.valor_atual_estimado ? brl(d.valor_atual_estimado) : '—'}</td>
                      <td>{statusBadge(d.status_resgate)}</td>
                      <td>{isSuperAdmin ? (d.faz_parte_honorarios ? pct(d.percentual_sucesso_honor) : '—') : '🔒'}</td>
                      <td><EstrategiaChips ids={d.estrategia_ids ?? []} estrategias={estrategias} onUpdate={ids => patchEstratDeb.mutate({ id: d.id, ids })} /></td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <button title="Detalhes" style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#6b7280', padding: '0 3px' }} onClick={() => setDebInfoId(d.id)}>ⓘ</button>
                        {editBtn(() => abrirEdicaoDeb(d))}
                      </td>
                    </tr>
                  ))}
                  <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                    <td colSpan={2}>Total</td>
                    <td />
                    <td style={{ textAlign: 'right' }}>{brl(g.posicoes.reduce((s: number, d: any) => s + (d.valor_aplicado ?? 0), 0))}</td>
                    <td style={{ textAlign: 'right' }}>{brl(g.posicoes.reduce((s: number, d: any) => s + (d.valor_atual_estimado ?? d.valor_aplicado ?? 0), 0))}</td>
                    <td /><td /><td /><td />
                  </tr>
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}

      {/* ══ IMOBILIÁRIO ════════════════════════════════════════════ */}
      {tab === 'imobiliario' && (
        <>
          {addBtn('Nova Posição', () => { setForm({ percentual_participacao: 100, faz_parte_honorarios: false }); setEditandoImobId(null); setModal('imobiliario') })}
          {filterBar(
            <><label style={{ fontSize: 12, color: 'var(--gray-mid)', whiteSpace: 'nowrap' }}>Empreendimento:</label>
            <div style={{ width: 280 }}>
              <MultiSelect values={filtroImobEmps} onChange={setFiltroImobEmps}
                options={empreendimentos.map(e => ({ value: e.id, label: e.nome_venda }))} placeholder="Todos" />
            </div></>,
            filtroClienteImob, setFiltroClienteImob,
          )}
          {clientesComImob.length === 0 ? emptyGroup() : clientesComImob.map(g => (
            <div key={g.id} className={cs.clienteFundoGroup}>
              <div className={cs.clienteFundoNome} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingRight: 12 }}>
                <span>{g.nome}</span>
                {quickAddBtn('+ Posição', () => { setForm({ cliente_id: g.id, percentual_participacao: 100, faz_parte_honorarios: false, percentual_sucesso_honorario: pctExitoImob(g.id) }); setEditandoImobId(null); setModal('imobiliario') })}
              </div>
              <table className={styles.table} style={{ marginBottom: 0 }}>
                {colsImob()}
                <thead><tr><th>Empreendimento</th>{thR('Comprometido')}{thR('Investido')}<th>% Part.</th><th>{isSuperAdmin ? 'Êxito%' : '🔒'}</th><th>Estratégia</th><th /></tr></thead>
                <tbody>
                  {g.posicoes.map((i: any) => (
                    <tr key={i.id}>
                      <td>{empreendimentoNome(i.empreendimento_id)}</td>
                      <td style={{ textAlign: 'right' }}>{brl(i.valor_total_compromissado)}</td>
                      <td style={{ textAlign: 'right' }}>{brl(i.valor_efetivamente_investido)}</td>
                      <td>{pct(i.percentual_participacao)}</td>
                      <td>{isSuperAdmin ? (i.faz_parte_honorarios ? pct(i.percentual_sucesso_honorario) : '—') : '🔒'}</td>
                      <td><EstrategiaChips ids={i.estrategia_ids ?? []} estrategias={estrategias} onUpdate={ids => patchEstratImob.mutate({ id: i.id, ids })} /></td>
                      <td>{editBtn(() => abrirEdicaoImob(i))}</td>
                    </tr>
                  ))}
                  <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                    <td>Total</td>
                    <td style={{ textAlign: 'right' }}>{brl(g.posicoes.reduce((s: number, i: any) => s + (i.valor_total_compromissado ?? 0), 0))}</td>
                    <td style={{ textAlign: 'right' }}>{brl(g.posicoes.reduce((s: number, i: any) => s + (i.valor_efetivamente_investido ?? 0), 0))}</td>
                    <td /><td /><td /><td />
                  </tr>
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}

      {/* ══ FUNDOS ═════════════════════════════════════════════════ */}
      {tab === 'fundos' && (
        <>
          {addBtn('Nova Posição', () => { setForm({ faz_parte_honorarios: false }); setEditandoFundoId(null); setModal('fundo') })}
          {filterBar(
            <><label style={{ fontSize: 12, color: 'var(--gray-mid)', whiteSpace: 'nowrap' }}>Fundo:</label>
            <div style={{ width: 260 }}>
              <MultiSelect values={filtroFundosFundos} onChange={setFiltroFundosFundos}
                options={fundosRef.map(f => ({ value: f.id, label: f.nome_fundo }))} placeholder="Todos" />
            </div></>,
            filtroClienteFundos, setFiltroClienteFundos,
          )}
          {clientesComFundos.length === 0 ? emptyGroup() : clientesComFundos.map(g => (
            <div key={g.id} className={cs.clienteFundoGroup}>
              <div className={cs.clienteFundoNome} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingRight: 12 }}>
                <span>{g.nome}</span>
                {quickAddBtn('+ Posição', () => { setForm({ cliente_id: g.id, faz_parte_honorarios: false, percentual_sucesso_honor: pctExitoFin(g.id) }); setEditandoFundoId(null); setModal('fundo') })}
              </div>
              <table className={styles.table} style={{ marginBottom: 0 }}>
                {colsFundos()}
                <thead><tr><th>Fundo</th>{thR('Aplicado')}{thR('Atual')}<th>Data</th><th>Recompra</th><th>{isSuperAdmin ? 'Êxito%' : '🔒'}</th><th>Estratégia</th><th /></tr></thead>
                <tbody>
                  {g.posicoes.map((f: any) => (
                    <tr key={f.id}>
                      <td><strong>{fundoNome(f.fundo_id)}</strong></td>
                      <td style={{ textAlign: 'right' }}>{brl(f.valor_aplicado)}</td>
                      <td style={{ textAlign: 'right' }}>{f.valor_atual_estimado ? brl(f.valor_atual_estimado) : '—'}</td>
                      <td>{f.data_aplicacao ?? '—'}</td>
                      <td>{f.tem_direito_recompra ? <span className={`${styles.badge} ${styles.status_suspenso}`}>Sim</span> : '—'}</td>
                      <td>{isSuperAdmin ? (f.faz_parte_honorarios ? pct(f.percentual_sucesso_honor) : '—') : '🔒'}</td>
                      <td><EstrategiaChips ids={f.estrategia_ids ?? []} estrategias={estrategias} onUpdate={ids => patchEstratFundo.mutate({ id: f.id, ids })} /></td>
                      <td>{editBtn(() => abrirEdicaoFundo(f))}</td>
                    </tr>
                  ))}
                  <tr style={{ background: 'var(--gray-light, #f8f9fa)', fontWeight: 600 }}>
                    <td>Total</td>
                    <td style={{ textAlign: 'right' }}>{brl(g.posicoes.reduce((s: number, f: any) => s + (f.valor_aplicado ?? 0), 0))}</td>
                    <td style={{ textAlign: 'right' }}>{brl(g.posicoes.reduce((s: number, f: any) => s + (f.valor_atual_estimado ?? f.valor_aplicado ?? 0), 0))}</td>
                    <td colSpan={5} />
                  </tr>
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}

      {/* ══ CLIENTES (referência) ══════════════════════════════════ */}
      {tab === 'clientes' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <span /><button className={styles.btnPrimary} onClick={() => { setForm({ pro_labore_tipo: '', tipo_pessoa: 'PF', exito_split: false }); setEditandoClienteId(null); setModal('cliente') }}>+ Novo Cliente</button>
          </div>
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <colgroup><col /><col style={{ width: 60 }} /><col style={{ width: 140 }} /><col style={{ width: 160 }} /><col style={{ width: 150 }} /><col style={{ width: 150 }} /><col style={{ width: 80 }} /><col style={{ width: 36 }} /><col style={{ width: 36 }} /><col style={{ width: 60 }} /></colgroup>
              <thead><tr><th>Nome</th><th>Tipo</th><th>CPF/CNPJ</th><th>{isSuperAdmin ? 'Fee entrada' : '🔒 Fee'}</th>{thR(isSuperAdmin ? 'Fee (R$ esp.)' : '🔒')}{thR(isSuperAdmin ? 'Êxito (R$ esp.)' : '🔒')}<th>Status</th><th /><th title="Drive" /></tr></thead>
              <tbody>
                {clientes.length === 0
                  ? <tr><td colSpan={10} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : clientes.map((c: any) => {
                    const { feeEntrada, exito } = calcularHonorarios(c)
                    const feeLbl = c.pro_labore_tipo === 'fixo' ? brl(c.pro_labore_valor)
                      : c.pro_labore_tipo === 'percentual'
                        ? (c.fee_imob_pct || c.fee_fin_pct ? `${c.fee_imob_pct ?? 0}%i/${c.fee_fin_pct ?? 0}%f` : `${c.pro_labore_valor ?? 0}%`)
                        : '—'
                    return (
                      <tr key={c.id}>
                        <td><strong>{clienteNome(c.id)}</strong></td>
                        <td><span className={styles.badge}>{c.tipo_pessoa ?? 'PF'}</span></td>
                        <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{c.cpf ?? '—'}</td>
                        <td>{isSuperAdmin ? feeLbl : '🔒'}</td>
                        <td style={{ textAlign: 'right' }}>{isSuperAdmin ? (feeEntrada > 0 ? brl(feeEntrada) : '—') : '🔒'}</td>
                        <td style={{ textAlign: 'right' }}>{isSuperAdmin ? (exito > 0 ? brl(exito) : '—') : '🔒'}</td>
                        <td>{statusBadge(c.ativo)}</td>
                        <td>
                          <button title="Copiar qualificação" style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: '#374151', padding: '0 4px' }}
                            onClick={() => navigator.clipboard.writeText(qualificacaoTexto(c)).then(() => alert('Qualificação copiada!')).catch(() => alert('Erro ao copiar'))}>⎘</button>
                        </td>
                        <td>
                          <button
                            title={c.folder_drive_principal_id ? 'Ver pasta Drive' : 'Criar pasta no Drive'}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 15, color: c.folder_drive_principal_id ? '#16a34a' : '#9ca3af', padding: '0 4px' }}
                            onClick={() => { setDriveClienteId(c.id); if (c.folder_drive_principal_id) carregarArquivosDrive(c.id) }}
                          >📁</button>
                        </td>
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
              <thead><tr><th>Série</th><th>Nº</th><th>Emissor</th><th>Indexador</th><th>Vencimento</th><th>Status</th><th /></tr></thead>
              <tbody>
                {emissoes.length === 0
                  ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : emissoes.map((e: any) => (
                    <tr key={e.id}><td><strong>{e.nome_serie}</strong></td><td>{e.numero_emissao}ª</td>
                      <td>{e.emissor}</td><td>{e.indexador}{e.taxa_adicional ? ` + ${e.taxa_adicional}` : ''}</td>
                      <td>{e.data_vencimento_previsto ?? '—'}</td><td>{statusBadge(e.ativo)}</td>
                      <td>{editBtn(() => abrirEdicaoEmissao(e))}</td>
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
              <thead><tr><th>Projeto</th><th>Razão Social do Veículo</th><th>CNPJ</th><th>Sub-veículos</th><th>Status</th><th title="Cadeia" /><th /></tr></thead>
              <tbody>
                {empreendimentos.length === 0
                  ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : empreendimentos.map((e: any) => {
                    const isDup = e.cnpj_empreendimento && (cnpjCount[e.cnpj_empreendimento] ?? 0) > 1
                    return (
                      <tr key={e.id}>
                        <td><strong>{e.nome_venda}</strong></td>
                        <td style={{ fontSize: 12 }}>{e.nome_razao_social ?? '—'}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: 11 }}>
                          {e.cnpj_empreendimento ?? '—'}
                          {isDup && <span style={{ marginLeft: 6, color: 'var(--red, #ef4444)', fontSize: 10, fontWeight: 700 }} title="CNPJ repetido">⚠ dup.</span>}
                        </td>
                        <td style={{ fontSize: 12 }}>{(e.subveiculos?.length ?? 0) > 0 ? e.subveiculos.length : '—'}</td>
                        <td>{statusBadge(e.ativo)}</td>
                        <td>
                          <button title="Cadeia Societária" style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#6366f1', padding: '0 4px' }}
                            onClick={() => setCadeiaEmpId(e.id)}>⬡</button>
                        </td>
                        <td>{editBtn(() => abrirEdicaoEmp(e))}</td>
                      </tr>
                    )
                  })}
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
              <thead><tr><th>Nome</th><th>CNPJ</th><th>Gestora</th><th>Tipo</th><th>Status</th><th /></tr></thead>
              <tbody>
                {fundosRef.length === 0
                  ? <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : fundosRef.map((f: any) => (
                    <tr key={f.id}><td><strong>{f.nome_fundo}</strong></td><td>{f.cnpj_fundo ?? '—'}</td><td>{f.gestora ?? '—'}</td><td>{f.tipo_fundo ?? '—'}</td><td>{statusBadge(f.ativo)}</td><td>{editBtn(() => abrirEdicaoFundoRef(f))}</td></tr>
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
              <thead><tr><th>Nome</th><th>Chip</th><th>Descrição</th><th>Usos</th><th>Status</th><th /></tr></thead>
              <tbody>
                {estrategias.length === 0
                  ? <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>Nenhum registro</td></tr>
                  : estrategias.map((e: any) => (
                    <tr key={e.id}>
                      <td><strong>{e.nome}</strong></td>
                      <td style={{ fontSize: 12, color: '#6b7280' }}>{e.nome_chip ?? '—'}</td>
                      <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.descricao ?? '—'}</td>
                      <td>{e.usuarios_count ?? 0}</td><td>{statusBadge(e.ativo)}</td>
                      <td>{editBtn(() => abrirEdicaoEstrategia(e))}</td>
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
          <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 6, padding: '10px 14px', marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>Pré-preencher de cliente existente</div>
            <UnifiedClientCombo
              localClientes={localClientesCombos}
              onSelect={c => setForm(f => ({ ...f, nome: c.nome ?? f.nome, cpf: c.cpf ?? f.cpf, email: c.email ?? f.email, telefone: c.telefone ?? f.telefone, tipo_pessoa: c.tipo_pessoa ?? f.tipo_pessoa, cliente_uuid: c.cliente_uuid ?? f.cliente_uuid }))}
            />
            {form.cliente_uuid && (
              <div style={{ fontSize: 11, color: 'var(--teal)', marginTop: 4 }}>✓ Vinculado
                <button style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-mid)', fontSize: 11 }} onClick={() => inp('cliente_uuid', '')}>remover</button>
              </div>
            )}
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 12, color: 'var(--gray-mid)', display: 'block', marginBottom: 4 }}>Preencher via documento (IA) — contrato de honorários, procuração, doc pessoal:</label>
            <input type="file" accept=".pdf,.jpg,.png,.jpeg" style={{ fontSize: 12 }}
              onChange={e => { const f = e.target.files?.[0]; if (f) processarDocumento.mutate({ file: f, tipo: 'cliente' }) }} />
            {processarDocumento.isPending && <span style={{ fontSize: 11, color: 'var(--teal)', marginLeft: 8 }}>Processando...</span>}
          </div>
          {fl('Nome completo *', fi('nome', 'text', 'Nome do investidor'))}
          {fl('Tipo pessoa', fs('tipo_pessoa', [{ value: 'PF', label: 'PF — Pessoa Física' }, { value: 'PJ', label: 'PJ — Pessoa Jurídica' }]))}
          {fl(form.tipo_pessoa === 'PJ' ? 'CNPJ' : 'CPF', fi('cpf', 'text'))}
          {form.tipo_pessoa !== 'PJ' && (
            <>
              {fl('Nacionalidade', fi('nacionalidade', 'text', 'brasileiro(a)'))}
              {fl('Estado civil', fs('estado_civil', [
                { value: 'solteiro', label: 'Solteiro(a)' }, { value: 'casado', label: 'Casado(a)' }, { value: 'uniao_estavel', label: 'União estável' }, { value: 'divorciado', label: 'Divorciado(a)' }, { value: 'viuvo', label: 'Viúvo(a)' },
              ]))}
              {fl('Profissão', fi('profissao'))}
              {fl('RG', fi('rg', 'text', 'Número do RG'))}
              {fl('Endereço', fi('endereco', 'text', 'Rua, número, bairro, cidade/UF'))}
            </>
          )}
          {form.tipo_pessoa === 'PJ' && (
            <>
              {fl('Endereço comercial', fi('endereco', 'text', 'Rua, número, bairro, cidade/UF'))}
              <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--indigo, #6366f1)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>Representante legal</div>
                {fl('Nome', fi('representante_nome'))}
                {fl('CPF', fi('representante_cpf'))}
                {fl('RG', fi('representante_rg'))}
                {fl('Nacionalidade', fi('representante_nacionalidade', 'text', 'brasileiro(a)'))}
                {fl('Estado civil', fs('representante_estado_civil', [
                  { value: 'solteiro', label: 'Solteiro(a)' }, { value: 'casado', label: 'Casado(a)' }, { value: 'uniao_estavel', label: 'União estável' }, { value: 'divorciado', label: 'Divorciado(a)' }, { value: 'viuvo', label: 'Viúvo(a)' },
                ]))}
                {fl('Profissão', fi('representante_profissao'))}
                {fl('Endereço', fi('representante_endereco', 'text', 'Rua, número, bairro, cidade/UF'))}
              </div>
            </>
          )}
          {fl('E-mail', fi('email', 'email'))}
          {fl('Telefone', fi('telefone'))}
          {isSuperAdmin && (
            <div style={{ borderTop: '1px solid var(--gray-border)', margin: '12px 0 0', paddingTop: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Fee de entrada</div>
              {fl('Tipo de fee', fs('pro_labore_tipo', [{ value: '', label: 'Sem fee de entrada' }, { value: 'fixo', label: 'Valor fixo (R$)' }, { value: 'percentual', label: 'Percentual do investimento (%)' }]))}
              {form.pro_labore_tipo === 'fixo' && fl('Valor (R$)', fi('pro_labore_valor', 'number'))}
              {form.pro_labore_tipo === 'percentual' && (
                <>{fl('% sobre ativos imobiliários', fi('fee_imob_pct', 'number'))}
                  {fl('% sobre ativos financeiros', fi('fee_fin_pct', 'number'))}</>
              )}
            </div>
          )}
          {isSuperAdmin && (
            <div style={{ borderTop: '1px solid var(--gray-border)', margin: '12px 0 0', paddingTop: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Honorários de êxito</div>
              <div className={styles.formRow}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                  <input type="checkbox" checked={!!form.exito_split} onChange={e => inp('exito_split', e.target.checked)} />
                  % diferente por tipo de ativo
                </label>
              </div>
              {!form.exito_split && fl('% êxito (geral)', fi('percentual_sucesso_geral', 'number'))}
              {form.exito_split && (
                <>{fl('% êxito imobiliário', fi('percentual_sucesso_imob', 'number'))}
                  {fl('% êxito financeiro', fi('percentual_sucesso_fin', 'number'))}</>
              )}
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            {fl('Observações', fta('observacoes', 2))}
            {editandoClienteId && fl('Status', fs('ativo', [{ value: 'true', label: 'Ativo' }, { value: 'false', label: 'Inativo' }]))}
          </div>
          <button className={styles.btnPrimary} onClick={() => editandoClienteId ? atualizarCliente.mutate() : salvarCliente.mutate()} disabled={salvarCliente.isPending || atualizarCliente.isPending}>
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
            {fl('Prestadora', fi('prestadora_nome', 'text', 'Apex Realty'))}
            {fl('CNPJ prestadora', fi('prestadora_cnpj'))}
            {fl('Razão social do veículo', fi('nome_razao_social'))}
            {fl('CNPJ do veículo', fi('cnpj_empreendimento'))}
            {fl('SPE executora', fi('spe_nome'))}
            {fl('CNPJ SPE', fi('spe_cnpj'))}
          </div>
          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Sub-veículos ({(form.subveiculos ?? []).length})</span>
              <button className={styles.btnSmall} onClick={() => inp('subveiculos', [...(form.subveiculos ?? []), { nome: '', cnpj: '', tipo: 'SCP' }])}>+ Adicionar</button>
            </div>
            {(form.subveiculos ?? []).map((sv: any, idx: number) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 120px 32px', gap: 6, marginBottom: 6, alignItems: 'end' }}>
                <div><label style={{ fontSize: 11, color: 'var(--gray-mid)' }}>Nome</label>
                  <input className={styles.input} value={sv.nome} placeholder="Nome" onChange={e => { const s = [...form.subveiculos]; s[idx] = { ...sv, nome: e.target.value }; inp('subveiculos', s) }} /></div>
                <div><label style={{ fontSize: 11, color: 'var(--gray-mid)' }}>CNPJ</label>
                  <input className={styles.input} value={sv.cnpj} placeholder="00.000.000/0001-00" onChange={e => { const s = [...form.subveiculos]; s[idx] = { ...sv, cnpj: e.target.value }; inp('subveiculos', s) }} /></div>
                <div><label style={{ fontSize: 11, color: 'var(--gray-mid)' }}>Tipo</label>
                  <select className={styles.input} value={sv.tipo} onChange={e => { const s = [...form.subveiculos]; s[idx] = { ...sv, tipo: e.target.value }; inp('subveiculos', s) }}>
                    <option value="SCP">SCP</option><option value="SPE">SPE</option><option value="Cota">Cota</option><option value="Outro">Outro</option>
                  </select></div>
                <button style={{ background: 'none', border: '1px solid var(--red, #ef4444)', color: 'var(--red, #ef4444)', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 12 }}
                  onClick={() => inp('subveiculos', form.subveiculos.filter((_: any, i: number) => i !== idx))}>✕</button>
              </div>
            ))}
          </div>
          {fl('Tipo desenvolvimento', fi('tipo_desenvolvimento'))}
          {fl('Localização', fi('localizacao'))}
          {fl('Descrição', fta('descricao', 2))}
          <button className={styles.btnPrimary} onClick={() => editandoEmpId ? atualizarEmpreendimento.mutate() : salvarEmpreendimento.mutate()} disabled={salvarEmpreendimento.isPending || atualizarEmpreendimento.isPending}>
            {(salvarEmpreendimento.isPending || atualizarEmpreendimento.isPending) ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {/* ── MODAL EMISSÃO ────────────────────────────────────────── */}
      {modal === 'emissao' && (
        <Modal title={editandoEmissaoId ? 'Editar Emissão' : 'Nova Emissão de Debênture'} onClose={closeModal} width={560}>
          <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 6, padding: '8px 12px', marginBottom: 10 }}>
            <label style={{ fontSize: 12, color: 'var(--teal)', fontWeight: 600, display: 'block', marginBottom: 4 }}>Extração IA — escritura de emissão / termo de securitização:</label>
            <input type="file" accept=".pdf,.jpg,.png,.jpeg" style={{ fontSize: 12 }}
              onChange={e => { const f = e.target.files?.[0]; if (f) processarDocumento.mutate({ file: f, tipo: 'emissao' }) }} />
            {processarDocumento.isPending && <span style={{ fontSize: 11, color: 'var(--teal)', marginLeft: 8 }}>Processando...</span>}
          </div>
          {fl('Nome da Série *', fi('nome_serie', 'text', 'Ex: APEX I'))}
          {fl('Nº da Emissão *', fi('numero_emissao', 'number'))}
          {fl('Emissor *', fi('emissor'))}
          {fl('CNPJ Emissor', fi('cnpj_emissor'))}
          {fl('Indexador', fi('indexador', 'text', 'CDI, IPCA...'))}
          {fl('Taxa Adicional', fi('taxa_adicional', 'text', '+ 2% a.a.'))}
          {fl('Data Início', fi('data_inicio_emissao', 'date'))}
          {fl('Data Vencimento Previsto', fi('data_vencimento_previsto', 'date'))}
          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>Resgate e liquidez</div>
            <div className={styles.formRow}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={!!form.resgate_antecipado_emissao} onChange={e => inp('resgate_antecipado_emissao', e.target.checked)} />
                Emissão prevê resgate antecipado
              </label>
            </div>
            {form.resgate_antecipado_emissao && fl('Tipo de resgate', fs('resgate_antecipado_tipo', [
              { value: 'vinculado_lastro', label: 'Vinculado ao recebimento do lastro' },
              { value: 'desvinculado_lastro', label: 'Desvinculado do recebimento do lastro' },
            ]))}
            {form.resgate_antecipado_emissao && fl('Cláusulas identificadas pela IA', fta('clausulas_resgate', 3))}
            {fl('Prazo carência (meses)', fi('prazo_carencia_meses', 'number', '0'))}
            {fl('Prazo pgto após pedido de saque', fi('prazo_pgto_pos_resgate', 'text', 'Ex: 30 dias'))}
          </div>
          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>Garantias</div>
            {fl('Tipos de garantia', fta('tipos_garantia', 2))}
          </div>
          <button className={styles.btnPrimary} onClick={() => editandoEmissaoId ? atualizarEmissao.mutate() : salvarEmissao.mutate()} disabled={salvarEmissao.isPending || atualizarEmissao.isPending}>{(salvarEmissao.isPending || atualizarEmissao.isPending) ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}

      {/* ── MODAL DEBÊNTURE ──────────────────────────────────────── */}
      {modal === 'debenture' && (
        <Modal title={editandoDebId ? 'Editar Debênture' : 'Nova Posição — Debênture'} onClose={closeModal} width={560}>
          <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 6, padding: '8px 12px', marginBottom: 10 }}>
            <label style={{ fontSize: 12, color: 'var(--indigo, #6366f1)', fontWeight: 600, display: 'block', marginBottom: 4 }}>Extração IA — escritura de emissão / termo de adesão:</label>
            <input type="file" accept=".pdf,.jpg,.png,.jpeg" style={{ fontSize: 12 }}
              onChange={e => { const f = e.target.files?.[0]; if (f) processarDocumento.mutate({ file: f, tipo: 'debenture' }) }} />
            {processarDocumento.isPending && <span style={{ fontSize: 11, color: 'var(--teal)', marginLeft: 8 }}>Processando...</span>}
          </div>
          {fl('Cliente *', <ComboSelect value={form.cliente_id} onChange={v => inp('cliente_id', Number(v))} options={clienteOptions} placeholder="Selecione o cliente..." />)}
          {fl('Emissão *', <ComboSelect value={form.emissao_id} onChange={v => inp('emissao_id', Number(v))} options={emissoes.map((e: any) => ({ value: e.id, label: `${e.nome_serie} — ${e.emissor}` }))} placeholder="Selecione a emissão..." />)}
          {fl('Nº Cautela *', fi('numero_cautela', 'text', 'CAU-001'))}
          {fl('Nº de Debêntures', fi('numero_debentures', 'number'))}
          {fl('Valor Aplicado (R$) *', fi('valor_aplicado', 'number'))}
          {fl('Data de Aquisição *', fi('data_aquisicao', 'date'))}
          {fl('Valor Atual Estimado (R$)', fi('valor_atual_estimado', 'number'))}
          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>Resgate</div>
            {fl('Status', fs('status_resgate', [{ value: 'Ativo', label: 'Ativo' }, { value: 'Resgate Solicitado', label: 'Resgate Solicitado' }, { value: 'Resgatado', label: 'Resgatado' }]))}
            {(form.status_resgate === 'Resgate Solicitado' || form.status_resgate === 'Resgatado') && (
              <>{fl('Data pedido de resgate', fi('data_pedido_resgate', 'date'))}
                {fl('Resposta Rhino / emissor', fta('resposta_rhino', 2))}</>
            )}
            {form.status_resgate === 'Resgatado' && (
              <>
                <div className={styles.formRow}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                    <input type="checkbox" checked={!!form.foi_pago} onChange={e => inp('foi_pago', e.target.checked)} /> Pagamento efetuado
                  </label>
                </div>
                {form.foi_pago && (
                  <>{fl('Valor pago (R$)', fi('valor_pago', 'number'))}{fl('Data do pagamento', fi('data_pagamento', 'date'))}</>
                )}
              </>
            )}
          </div>
          <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
            <div className={styles.formRow}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={!!form.resgate_antecipado_cautela} onChange={e => inp('resgate_antecipado_cautela', e.target.checked)} />
                Termo/cautela prevê resgate antecipado
              </label>
            </div>
            {form.resgate_antecipado_cautela && fl('Tipo de resgate (cautela)', fs('resgate_antecipado_tipo_cautela', [
              { value: 'vinculado_lastro', label: 'Vinculado ao recebimento do lastro' },
              { value: 'desvinculado_lastro', label: 'Desvinculado do recebimento do lastro' },
            ]))}
            {form.resgate_antecipado_cautela && fl('Cláusulas do termo de cautela', fta('clausulas_resgate_cautela', 3))}
          </div>
          {isSuperAdmin && (
            <div style={{ borderTop: '1px solid var(--gray-border)', margin: '10px 0', paddingTop: 10 }}>
              <div className={styles.formRow}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                  <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} /> Faz parte de honorários de êxito
                </label>
              </div>
              {form.faz_parte_honorarios && fl('% Êxito', fi('percentual_sucesso_honor', 'number'))}
            </div>
          )}
          <button className={styles.btnPrimary} onClick={() => editandoDebId ? atualizarDebenture.mutate() : salvarDebenture.mutate()} disabled={salvarDebenture.isPending || atualizarDebenture.isPending}>
            {(salvarDebenture.isPending || atualizarDebenture.isPending) ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {/* ── MODAL IMOBILIÁRIO ────────────────────────────────────── */}
      {modal === 'imobiliario' && (
        <Modal title={editandoImobId ? 'Editar posição imobiliária' : 'Nova Posição — Imobiliário'} onClose={closeModal} width={520}>
          <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 6, padding: '8px 12px', marginBottom: 10 }}>
            <label style={{ fontSize: 12, color: 'var(--amber, #b45309)', fontWeight: 600, display: 'block', marginBottom: 4 }}>Extração IA — contrato SCP / contrato de prestação / ficha do ativo:</label>
            <input type="file" accept=".pdf,.jpg,.png,.jpeg" style={{ fontSize: 12 }}
              onChange={e => { const f = e.target.files?.[0]; if (f) processarDocumento.mutate({ file: f, tipo: 'imobiliario' }) }} />
            {processarDocumento.isPending && <span style={{ fontSize: 11, color: 'var(--teal)', marginLeft: 8 }}>Processando...</span>}
          </div>
          {fl('Cliente *', <ComboSelect value={form.cliente_id} onChange={v => inp('cliente_id', Number(v))} options={clienteOptions} placeholder="Selecione o cliente..." />)}
          {fl('Empreendimento *', <ComboSelect value={form.empreendimento_id} onChange={v => inp('empreendimento_id', Number(v))} options={empreendimentos.map((e: any) => ({ value: e.id, label: e.nome_venda }))} placeholder="Selecione o empreendimento..." />)}
          {fl('Valor Total Comprometido (R$) *', fi('valor_total_compromissado', 'number'))}
          {fl('Valor Efetivamente Investido (R$)', fi('valor_efetivamente_investido', 'number'))}
          {fl('% Participação', fi('percentual_participacao', 'number', '100'))}
          {fl('Data Primeiro Aporte', fi('data_primeiro_aporte', 'date'))}
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} /> Faz parte de honorários de êxito
            </label>
          </div>
          {form.faz_parte_honorarios && fl('% Êxito', fi('percentual_sucesso_honorario', 'number'))}
          <button className={styles.btnPrimary} onClick={() => editandoImobId ? atualizarImobiliario.mutate() : salvarImobiliario.mutate()} disabled={salvarImobiliario.isPending || atualizarImobiliario.isPending}>
            {(salvarImobiliario.isPending || atualizarImobiliario.isPending) ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {/* ── MODAL FUNDO REF ──────────────────────────────────────── */}
      {modal === 'fundo-ref' && (
        <Modal title={editandoFundoRefId ? 'Editar Fundo de Referência' : 'Novo Fundo de Referência'} onClose={closeModal} width={480}>
          {fl('Nome do Fundo *', fi('nome_fundo'))}
          {fl('CNPJ', fi('cnpj_fundo'))}
          {fl('Gestora', fi('gestora'))}
          {fl('Administradora', fi('administradora'))}
          {fl('Tipo', fi('tipo_fundo', 'text', 'FII, FIA, Multimercado...'))}
          {fl('Indexador', fi('indexador'))}
          <button className={styles.btnPrimary} onClick={() => editandoFundoRefId ? atualizarFundoRef.mutate() : salvarFundoRef.mutate()} disabled={salvarFundoRef.isPending || atualizarFundoRef.isPending}>{(salvarFundoRef.isPending || atualizarFundoRef.isPending) ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}

      {/* ── MODAL FUNDO POSIÇÃO ──────────────────────────────────── */}
      {modal === 'fundo' && (
        <Modal title={editandoFundoId ? 'Editar posição — Fundo' : 'Nova Posição — Fundo'} onClose={closeModal} width={520}>
          <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 6, padding: '8px 12px', marginBottom: 10 }}>
            <label style={{ fontSize: 12, color: 'var(--blue, #1d4ed8)', fontWeight: 600, display: 'block', marginBottom: 4 }}>Extração IA — lâmina do fundo / regulamento:</label>
            <input type="file" accept=".pdf,.jpg,.png,.jpeg" style={{ fontSize: 12 }}
              onChange={e => { const f = e.target.files?.[0]; if (f) processarDocumento.mutate({ file: f, tipo: 'fundo' }) }} />
            {processarDocumento.isPending && <span style={{ fontSize: 11, color: 'var(--teal)', marginLeft: 8 }}>Processando...</span>}
          </div>
          {fl('Cliente *', <ComboSelect value={form.cliente_id} onChange={v => inp('cliente_id', Number(v))} options={clienteOptions} placeholder="Selecione o cliente..." />)}
          {fl('Fundo *', <ComboSelect value={form.fundo_id} onChange={v => inp('fundo_id', Number(v))} options={fundosRef.map((f: any) => ({ value: f.id, label: f.nome_fundo }))} placeholder="Selecione o fundo..." />)}
          {fl('Valor Aplicado (R$) *', fi('valor_aplicado', 'number'))}
          {fl('Data de Aplicação *', fi('data_aplicacao', 'date'))}
          {fl('Valor Atual Estimado (R$)', fi('valor_atual_estimado', 'number'))}
          {fl('Nº Conta', fi('numero_conta'))}
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.faz_parte_honorarios} onChange={e => inp('faz_parte_honorarios', e.target.checked)} /> Faz parte de honorários de êxito
            </label>
          </div>
          {form.faz_parte_honorarios && fl('% Êxito', fi('percentual_sucesso_honor', 'number'))}
          <div className={styles.formRow}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!form.tem_direito_recompra} onChange={e => inp('tem_direito_recompra', e.target.checked)} /> Tem direito de recompra
            </label>
          </div>
          {form.tem_direito_recompra && fl('Data vencimento recompra', fi('data_vencimento_recompra', 'date'))}
          <button className={styles.btnPrimary} onClick={() => editandoFundoId ? atualizarFundo.mutate() : salvarFundo.mutate()} disabled={salvarFundo.isPending || atualizarFundo.isPending}>
            {(salvarFundo.isPending || atualizarFundo.isPending) ? 'Salvando...' : 'Salvar'}
          </button>
        </Modal>
      )}

      {/* ── MODAL ESTRATÉGIA ─────────────────────────────────────── */}
      {modal === 'estrategia' && (
        <Modal title={editandoEstrategiaId ? 'Editar Estratégia' : 'Nova Estratégia'} onClose={closeModal}>
          {fl('Nome *', fi('nome', 'text', 'Ex: Conservadora, ABM-PARSE'))}
          {fl('Nome do chip (3-4 palavras)', fi('nome_chip', 'text', 'Ex: Cons. Capital'))}
          {fl('Descrição', fta('descricao', 4))}
          <button className={styles.btnPrimary} onClick={() => editandoEstrategiaId ? atualizarEstrategia.mutate() : salvarEstrategia.mutate()} disabled={salvarEstrategia.isPending || atualizarEstrategia.isPending}>{(salvarEstrategia.isPending || atualizarEstrategia.isPending) ? 'Salvando...' : 'Salvar'}</button>
        </Modal>
      )}

      {/* ── MODAL RESGATE ANTECIPADO ─────────────────────────────── */}
      {resgateDebId !== null && (() => {
        const d = debentures.find(x => x.id === resgateDebId)
        const em = d ? emissoes.find(e => e.id === d.emissao_id) : null
        if (!d) return null
        const tipoLabel = (t: string | null | undefined) => t === 'desvinculado_lastro' ? 'Desvinculado do lastro (independe de pgto)' : t === 'vinculado_lastro' ? 'Vinculado ao lastro' : '—'
        return (
          <Modal title="Resgate Antecipado — Cláusulas contratuais" onClose={() => setResgateDebId(null)} width={520}>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', marginBottom: 6 }}>Escritura de Emissão</div>
              <div style={{ fontSize: 12, marginBottom: 6 }}>
                Prevê resgate antecipado: <strong>{em?.resgate_antecipado_emissao ? 'Sim' : 'Não'}</strong>
                {em?.resgate_antecipado_tipo && <> — <strong>{tipoLabel(em.resgate_antecipado_tipo)}</strong></>}
              </div>
              {em?.clausulas_resgate
                ? <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 4, padding: '8px 12px', fontSize: 12, whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{em.clausulas_resgate}</div>
                : <div style={{ fontSize: 12, color: 'var(--gray-mid)', fontStyle: 'italic' }}>Cláusulas não identificadas. Faça upload via IA ao editar a emissão.</div>}
            </div>
            <div style={{ borderTop: '1px solid var(--gray-border)', paddingTop: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', marginBottom: 6 }}>Termo de Securitização / Cautela</div>
              <div style={{ fontSize: 12, marginBottom: 6 }}>
                Prevê resgate antecipado: <strong>{d.resgate_antecipado_cautela ? 'Sim' : 'Não'}</strong>
                {d.resgate_antecipado_tipo_cautela && <> — <strong>{tipoLabel(d.resgate_antecipado_tipo_cautela)}</strong></>}
              </div>
              {d.clausulas_resgate_cautela
                ? <div style={{ background: 'var(--gray-light, #f8f9fa)', borderRadius: 4, padding: '8px 12px', fontSize: 12, whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{d.clausulas_resgate_cautela}</div>
                : <div style={{ fontSize: 12, color: 'var(--gray-mid)', fontStyle: 'italic' }}>Cláusulas não identificadas. Preencha ao editar a posição.</div>}
            </div>
          </Modal>
        )
      })()}

      {/* ── MODAL DETALHES DEBÊNTURE ─────────────────────────────── */}
      {debInfoId !== null && (() => {
        const d = debentures.find(x => x.id === debInfoId)
        const em = d ? emissoes.find(e => e.id === d.emissao_id) : null
        if (!d) return null
        const sim_nao = (v: any) => v ? 'Sim' : 'Não'
        const infoRow = (label: string, value: string | number | React.ReactNode) => (
          <div style={{ display: 'flex', gap: 12, padding: '6px 0', borderBottom: '1px solid var(--gray-light, #f3f4f6)', fontSize: 13 }}>
            <span style={{ minWidth: 220, color: 'var(--gray-mid)', fontSize: 12, fontWeight: 500 }}>{label}</span>
            <span style={{ fontWeight: 500 }}>{value ?? '—'}</span>
          </div>
        )
        return (
          <Modal title={`Detalhes — ${d.numero_cautela ?? emissaoNome(d.emissao_id)}`} onClose={() => setDebInfoId(null)} width={480}>
            <div style={{ marginBottom: 8 }}>
              {infoRow('Emissão', emissaoNome(d.emissao_id))}
              {infoRow('Data de aquisição', d.data_aquisicao ?? '—')}
              {em && infoRow('Data de vencimento previsto', em.data_vencimento_previsto ?? '—')}
              {em && infoRow('Indexador', em.indexador ? `${em.indexador}${em.taxa_adicional ? ` + ${em.taxa_adicional}` : ''}` : '—')}
              <div style={{ borderTop: '2px solid var(--gray-border)', margin: '10px 0 6px', paddingTop: 6 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', marginBottom: 4 }}>Resgate</div>
              </div>
              {em && infoRow('Resgate antecipado — emissão prevê?', sim_nao(em.resgate_antecipado_emissao))}
              {infoRow('Resgate antecipado — termo/cautela prevê?', sim_nao(d.resgate_antecipado_cautela))}
              {em && infoRow('Prazo carência', em.prazo_carencia_meses != null ? `${em.prazo_carencia_meses} meses` : '—')}
              {em && infoRow('Prazo pgto após pedido de saque', em.prazo_pgto_pos_resgate != null ? `${em.prazo_pgto_pos_resgate} dias` : '—')}
              {em && em.tipos_garantia && (
                <>
                  <div style={{ borderTop: '2px solid var(--gray-border)', margin: '10px 0 6px', paddingTop: 6 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', marginBottom: 4 }}>Garantias</div>
                  </div>
                  <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{em.tipos_garantia}</div>
                </>
              )}
            </div>
          </Modal>
        )
      })()}

      {/* ── MODAL DRIVE ─────────────────────────────────────────── */}
      {driveClienteId !== null && (() => {
        const c = clientes.find((x: any) => x.id === driveClienteId)
        if (!c) return null
        const nome = clienteNome(c.id)
        const temPasta = !!c.folder_drive_principal_id
        return (
          <Modal title={`Drive — ${nome}`} onClose={() => { setDriveClienteId(null); setDriveArquivos([]) }} width={480}>
            {!temPasta ? (
              <div style={{ textAlign: 'center', padding: '24px 0' }}>
                <div style={{ fontSize: 13, color: 'var(--gray-mid)', marginBottom: 16 }}>
                  Nenhuma pasta Drive vinculada a este cliente.
                </div>
                <button
                  className={styles.btnPrimary}
                  disabled={criarPastaDrive.isPending}
                  onClick={() => criarPastaDrive.mutate(driveClienteId)}
                >
                  {criarPastaDrive.isPending ? 'Criando...' : '📁 Criar pasta no Drive'}
                </button>
              </div>
            ) : (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, padding: '8px 12px', background: 'var(--gray-light, #f3f4f6)', borderRadius: 6 }}>
                  <span style={{ fontSize: 18 }}>📁</span>
                  <a href={c.folder_drive_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, color: 'var(--teal)', fontWeight: 600 }}>
                    Abrir pasta no Drive
                  </a>
                </div>
                <div style={{ marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--gray-dark)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Arquivos</span>
                  <label style={{ cursor: 'pointer', fontSize: 12, color: 'var(--teal)', fontWeight: 600 }}>
                    ⬆ Upload
                    <input type="file" style={{ display: 'none' }} onChange={async e => {
                      const f = e.target.files?.[0]; if (f) await uploadDriveFile(driveClienteId, f)
                    }} />
                  </label>
                </div>
                {driveCarregando
                  ? <div style={{ fontSize: 12, color: 'var(--gray-mid)', padding: 12 }}>Carregando...</div>
                  : driveArquivos.length === 0
                    ? <div style={{ fontSize: 12, color: 'var(--gray-mid)', fontStyle: 'italic', padding: '8px 0' }}>Nenhum arquivo ainda.</div>
                    : driveArquivos.map((f: any) => (
                      <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--gray-border, #e5e7eb)', fontSize: 12 }}>
                        <span style={{ flex: 1 }}>{f.name}</span>
                        <a href={f.webViewLink} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--teal)', fontWeight: 600, whiteSpace: 'nowrap' }}>Ver</a>
                      </div>
                    ))
                }
              </div>
            )}
          </Modal>
        )
      })()}

      {/* ── MODAL CADEIA SOCIETÁRIA ──────────────────────────────── */}
      {cadeiaEmpId !== null && (() => {
        const e = empreendimentos.find((x: any) => x.id === cadeiaEmpId)
        if (!e) return null
        const nodeStyle: React.CSSProperties = {
          border: '2px solid var(--teal, #0d9488)', borderRadius: 8, padding: '10px 16px',
          minWidth: 200, maxWidth: 260, background: 'var(--bg-card, white)',
          textAlign: 'center', fontSize: 12,
        }
        const labelStyle: React.CSSProperties = {
          fontSize: 10, fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase',
          letterSpacing: '0.07em', marginBottom: 2,
        }
        const arrowStyle: React.CSSProperties = {
          textAlign: 'center', fontSize: 18, color: 'var(--gray-mid, #9ca3af)', margin: '4px 0', lineHeight: 1,
        }
        const nodeBox = (label: string, nome: string | null | undefined, cnpj: string | null | undefined, borderColor?: string) => (
          nome ? (
            <div style={{ ...nodeStyle, ...(borderColor ? { border: `2px solid ${borderColor}` } : {}) }}>
              <div style={{ ...labelStyle, ...(borderColor ? { color: borderColor } : {}) }}>{label}</div>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{nome}</div>
              {cnpj && <div style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--gray-mid)' }}>{cnpj}</div>}
            </div>
          ) : null
        )
        const subvs: any[] = e.subveiculos ?? []
        const temCadeia = e.prestadora_nome || e.nome_razao_social || e.spe_nome || subvs.length > 0
        return (
          <Modal title={`Cadeia Societária — ${e.nome_venda}`} onClose={() => setCadeiaEmpId(null)} width={520}>
            {!temCadeia ? (
              <div style={{ fontSize: 13, color: 'var(--gray-mid)', fontStyle: 'italic', padding: '24px 0', textAlign: 'center' }}>
                Cadeia não preenchida. Edite o empreendimento para adicionar Prestadora, Veículo, SPE e Sub-veículos.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0, padding: '8px 0' }}>
                {nodeBox('Prestadora de Serviços', e.prestadora_nome ?? 'Apex Realty', e.prestadora_cnpj, '#6366f1')}
                {e.nome_razao_social && <div style={arrowStyle}>↓</div>}
                {nodeBox('Veículo Imobiliário', e.nome_razao_social, e.cnpj_empreendimento)}
                {e.spe_nome && <><div style={arrowStyle}>↓</div>{nodeBox('SPE', e.spe_nome, e.spe_cnpj, '#0891b2')}</>}
                {subvs.length > 0 && (
                  <>
                    <div style={arrowStyle}>↓</div>
                    <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Sub-veículos ({subvs.length})</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
                      {subvs.map((sv: any, i: number) => (
                        <div key={i} style={{ ...nodeStyle, minWidth: 140, maxWidth: 180, border: '1.5px solid #a5b4fc' }}>
                          <div style={{ ...labelStyle, color: '#6366f1' }}>{sv.tipo ?? 'Sub-veículo'}</div>
                          <div style={{ fontWeight: 600, fontSize: 12 }}>{sv.nome}</div>
                          {sv.cnpj && <div style={{ fontFamily: 'monospace', fontSize: 10, color: 'var(--gray-mid)' }}>{sv.cnpj}</div>}
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </Modal>
        )
      })()}
    </div>
  )
}
