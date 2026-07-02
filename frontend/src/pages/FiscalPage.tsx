import React, { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fiscalApi } from '../api/fiscal'
import type { NotaFiscalOut, NotaFiscalResumo, EmitirNFSeIn, StatusNF } from '../api/fiscal'
import { clientesApi } from '../api/clientes'
import type { Cliente } from '../api/clientes'
import { pagantesApi } from '../api/pagantes'
import type { PaganteOut } from '../api/pagantes'
import { contratosApi } from '../api/contratos'
import { processosApi } from '../api/processos'
import { configFiscalApi } from '../api/configFiscal'
import { backofficeApi, type SugestaoNF } from '../api/backoffice'
import { financeiroApi } from '../api/financeiro'
import { reembolsosApi } from '../api/reembolsos'
import { mascaraDocumento, validaDocumento, mascaraTelefone, soDigitos, soAlfanum } from '../utils/documentos'
import styles from './Page.module.css'
import cs from './FiscalPage.module.css'

// ─── Constantes ──────────────────────────────────────────────────────────────

const PRESTADOR = {
  cnpj: '10.901.611/0001-64',
  nome: 'Pimenta Judice Sociedade Individual de Advocacia',
  municipio: 'Vitória/ES',
  regime: 'Simples Nacional',
  cnaePrincipal: '6911-7/01 — Atividades jurídicas exceto contencioso',
}

const TEMPLATES_DESCRICAO = [
  {
    tipo: 'processo',
    label: 'Processo judicial',
    texto: (cliente: string, extra?: string) =>
      `Honorários advocatícios referentes à prestação de serviços advocatícios${extra ? ` — ${extra}` : ''} — cliente ${cliente}`,
  },
  {
    tipo: 'consultoria',
    label: 'Consultoria jurídica',
    texto: (cliente: string) =>
      `Serviços de consultoria e assessoria jurídica prestados ao cliente ${cliente}`,
  },
  {
    tipo: 'planejamento',
    label: 'Planejamento jurídico-societário',
    texto: (cliente: string) =>
      `Serviços de planejamento jurídico-societário e patrimonial prestados ao cliente ${cliente}`,
  },
  {
    tipo: 'exito',
    label: 'Honorários de êxito',
    texto: (cliente: string, extra?: string) =>
      `Honorários advocatícios de êxito referentes${extra ? ` ao Processo nº ${extra}` : ''} — cliente ${cliente}`,
  },
]

// ─── Formatação R$ ────────────────────────────────────────────────────────────

function fmtBRL(v: number) {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function fmtCompetencia(c: string) {
  const [ano, mes] = c.split('-')
  const m = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
  return `${m[parseInt(mes) - 1]}/${ano}`
}

function fmtData(d?: string) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

function parseBRL(s: string): number {
  // "1.500,00" → 1500.00
  return parseFloat(s.replace(/\./g, '').replace(',', '.')) || 0
}

function toBRLInput(n: number): string {
  if (!n && n !== 0) return ''
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function mesAtual() {
  return new Date().toISOString().slice(0, 7)
}

// ─── Status ───────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<StatusNF, string> = {
  rascunho: 'Rascunho', emitida: 'Emitida', cancelada: 'Cancelada', erro: 'Erro',
  substituida: 'Substituída',
}
const STATUS_CLASS: Record<StatusNF, string> = {
  emitida: cs.badgeEmitida, rascunho: cs.badgeRascunho,
  cancelada: cs.badgeCancelada, erro: cs.badgeErro,
  substituida: cs.badgeCancelada,
}

// ─── Input R$ formatado ───────────────────────────────────────────────────────

function CurrencyField({
  label, value, onChange, required,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  required?: boolean
}) {
  const [raw, setRaw] = useState(toBRLInput(value))

  useEffect(() => {
    setRaw(toBRLInput(value))
  }, [value])

  return (
    <div>
      <label className={cs.formLabel}>{label}{required && ' *'}</label>
      <div className={cs.currencyWrap}>
        <span className={cs.currencyPrefix}>R$</span>
        <input
          className={cs.inputCurrency}
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          onBlur={() => {
            const parsed = parseBRL(raw)
            onChange(parsed)
            setRaw(toBRLInput(parsed))
          }}
          placeholder="0,00"
          inputMode="decimal"
        />
      </div>
    </div>
  )
}

// ─── Dropdown com descrição ───────────────────────────────────────────────────

interface OpcaoDesc { valor: string; label: string; descricao: string }

function SelectComDesc({
  label, value, onChange, opcoes, info,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  opcoes: OpcaoDesc[]
  info?: string
}) {
  const selecionada = opcoes.find((o) => o.valor === value)
  return (
    <div>
      <label className={cs.formLabel}>{label}</label>
      <select className={cs.input} value={value} onChange={(e) => onChange(e.target.value)}>
        {opcoes.map((o) => (
          <option key={o.valor} value={o.valor}>{o.label}</option>
        ))}
      </select>
      {selecionada && (
        <p className={cs.fieldHint}>{selecionada.descricao}</p>
      )}
      {info && <p className={cs.fieldHint} style={{ color: '#6b7280' }}>{info}</p>}
    </div>
  )
}

// ─── Busca de cliente com auto-fill ──────────────────────────────────────────

function ClienteSearch({
  value, onSelect, label = 'Nome / Razão Social do Tomador *', placeholder,
  incluirPagantes = false, onSelectPagante,
}: {
  value: string
  onSelect: (c: Cliente | null, nomeRaw: string) => void
  label?: string
  placeholder?: string
  incluirPagantes?: boolean
  onSelectPagante?: (p: PaganteOut) => void
}) {
  const [q, setQ] = useState(value)
  const [aberto, setAberto] = useState(false)

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: clientesApi.listar,
    staleTime: 60_000,
  })
  const { data: pagantes = [] } = useQuery({
    queryKey: ['pagantes'],
    queryFn: () => pagantesApi.listar(),
    staleTime: 60_000,
    enabled: incluirPagantes,
  })

  const filtrados = useMemo(() => {
    if (!q) return clientes.slice(0, 20)  // sem texto: mostra os primeiros 20
    const lower = q.toLowerCase()
    const digits = q.replace(/\D/g, '')
    const matched = clientes.filter((c) =>
      c.nome.toLowerCase().includes(lower) ||
      (digits && (c.cpf_cnpj || '').replace(/\D/g, '').includes(digits))
    )
    matched.sort((a, b) => {
      const aStarts = a.nome.toLowerCase().startsWith(lower) ? 0 : 1
      const bStarts = b.nome.toLowerCase().startsWith(lower) ? 0 : 1
      return aStarts - bStarts || a.nome.localeCompare(b.nome)
    })
    return matched.slice(0, 20)
  }, [q, clientes])

  // Pagantes a exibir (dedup só por CPF/CNPJ igual a um cliente já listado —
  // NÃO por cliente_id, que na compensação aponta para o beneficiário, não para
  // o próprio pagante). Assim pagantes não-clientes (ex.: Ana Maria) aparecem.
  const pagantesFiltrados = useMemo(() => {
    if (!incluirPagantes) return []
    const docsClientes = new Set(clientes.map((c) => (c.cpf_cnpj || '').replace(/\D/g, '')).filter(Boolean))
    const nomesClientes = new Set(clientes.map((c) => c.nome.toLowerCase()))
    const lower = q.toLowerCase()
    const digits = q.replace(/\D/g, '')
    return pagantes
      .filter((p) => {
        const doc = (p.cpf_cnpj || '').replace(/\D/g, '')
        // esconde se já é cliente (mesmo doc, ou mesmo nome quando sem doc)
        if (doc && docsClientes.has(doc)) return false
        if (!doc && nomesClientes.has(p.nome.toLowerCase())) return false
        return true
      })
      .filter((p) => !q || p.nome.toLowerCase().includes(lower) ||
        (digits && (p.cpf_cnpj || '').includes(digits)))
      .slice(0, 12)
  }, [incluirPagantes, pagantes, clientes, q])

  return (
    <div className={cs.searchWrap}>
      <label className={cs.formLabel}>{label}</label>
      <input
        className={cs.input}
        value={q}
        onChange={(e) => { setQ(e.target.value); setAberto(true); onSelect(null, e.target.value) }}
        onFocus={() => setAberto(true)}
        onBlur={() => setTimeout(() => setAberto(false), 180)}
        placeholder={placeholder ?? 'Digite para buscar cliente cadastrado…'}
        autoComplete="off"
      />
      {aberto && (filtrados.length > 0 || pagantesFiltrados.length > 0) && (
        <ul className={cs.dropdown}>
          {filtrados.map((c) => (
            <li key={c.id} className={cs.dropdownItem}
              onMouseDown={() => { setQ(c.nome); setAberto(false); onSelect(c, c.nome) }}>
              <span className={cs.dropdownNome}>{c.nome}</span>
              {c.cpf_cnpj && <span className={cs.dropdownDoc}>{c.cpf_cnpj}</span>}
              {c.email && <span className={cs.dropdownEmail}>{c.email}</span>}
            </li>
          ))}
          {pagantesFiltrados.length > 0 && (
            <li style={{ padding: '4px 10px', fontSize: 10, color: '#9ca3af', fontWeight: 600, background: '#f9fafb' }}>
              PAGANTES (não-clientes)
            </li>
          )}
          {pagantesFiltrados.map((p) => (
            <li key={p.id} className={cs.dropdownItem}
              onMouseDown={() => { setQ(p.nome); setAberto(false); onSelectPagante?.(p) }}>
              <span className={cs.dropdownNome}>{p.nome} <span style={{ fontSize: 10, color: '#1d4ed8' }}>• pagante</span></span>
              {p.cpf_cnpj && <span className={cs.dropdownDoc}>{p.cpf_cnpj}</span>}
              {p.email && <span className={cs.dropdownEmail}>{p.email}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ─── Formulário principal de emissão ─────────────────────────────────────────

const EMPTY: EmitirNFSeIn = {
  competencia: mesAtual(),
  serie: '1',
  tomador_cpf_cnpj: '',
  tomador_nome: '',
  tomador_email: '',
  tomador_telefone: '',
  tomador_no_exterior: false,
  descricao_servico: '',
  cod_tributacao_nacional: '171401',
  natureza_operacao: '1',
  regime_tributario: '1',
  reg_apuracao_sn: '3',
  valor_servicos: 0,
  retencao_ir: 0,
  retencao_inss: 0,
  retencao_csll: 0,
  retencao_cofins: 0,
  retencao_pis: 0,
  iss_retido: false,
  cliente_compensacao_id: undefined,
  contrato_compensacao_id: undefined,
  valor_compensacao: undefined,
}

// Cache de CPF/email de pagadores (localStorage: "pagador:{nome}" → {cpf, email})
function getCachePagador(nome: string) {
  try {
    const cached = localStorage.getItem(`pagador:${nome}`)
    return cached ? JSON.parse(cached) : null
  } catch { return null }
}
function setCachePagador(nome: string, cpf: string, email?: string) {
  try {
    localStorage.setItem(`pagador:${nome}`, JSON.stringify({ cpf, email }))
  } catch {}
}

function EmissaoModal({
  inicial,
  onClose,
  onSucesso,
}: {
  inicial?: Partial<EmitirNFSeIn>
  onClose: () => void
  onSucesso: (nf: NotaFiscalOut) => void
}) {
  const [form, setForm] = useState<EmitirNFSeIn>({ ...EMPTY, ...inicial })
  const [mostrarRetencoes, setMostrarRetencoes] = useState(false)
  const [mostrarEmitente, setMostrarEmitente] = useState(false)
  const [mostrarIntermed, setMostrarIntermed] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [clienteSelecionado, setClienteSelecionado] = useState<Cliente | null>(null)
  const [vincularOutro, setVincularOutro] = useState(false)
  const [clienteVinculadoNome, setClienteVinculadoNome] = useState<string>('')
  const [temCompensacao, setTemCompensacao] = useState(false)
  const [nomeClienteCompensacao, setNomeClienteCompensacao] = useState<string>('')
  const [paganteSelNome, setPaganteSelNome] = useState<string | null>(null)

  // Ao mudar tomador_nome, prefill com cache
  useEffect(() => {
    if (form.tomador_nome && !form.tomador_cpf_cnpj) {
      const cached = getCachePagador(form.tomador_nome)
      if (cached) {
        set('tomador_cpf_cnpj', cached.cpf)
        if (cached.email) set('tomador_email', cached.email)
      }
    }
  }, [form.tomador_nome])

  // Honorários em aberto do beneficiário (para compensação)
  const { data: honorariosBenef = [] } = useQuery({
    queryKey: ['honorarios-benef', form.cliente_compensacao_id],
    queryFn: () => financeiroApi.listarHonorarios({ cliente_id: form.cliente_compensacao_id! }),
    enabled: !!form.cliente_compensacao_id,
  })

  const { data: codigosBackend = [] } = useQuery({
    queryKey: ['fiscal-codigos-trib'],
    queryFn: fiscalApi.listarCodigosTributacao,
    staleTime: Infinity,
  })
  const { data: cfgFiscal } = useQuery({
    queryKey: ['config-fiscal'], queryFn: configFiscalApi.obter, staleTime: 60_000,
  })
  // Templates: do Config se houver, senão os padrões
  const templates = (cfgFiscal?.templates_descricao?.length
    ? cfgFiscal.templates_descricao
    : TEMPLATES_DESCRICAO.map((t) => ({ tipo: t.tipo, label: t.label, texto: '' })))
  // Códigos: favoritos do Config se houver, senão os do backend
  const codigosTrib = (cfgFiscal?.codigos_favoritos?.length
    ? cfgFiscal.codigos_favoritos.map((c) => ({ codigo: c.codigo, label: c.label, descricao: c.descricao || '' }))
    : codigosBackend)

  const { data: naturezasOp = [] } = useQuery({
    queryKey: ['fiscal-natureza-op'],
    queryFn: fiscalApi.listarNaturezaOperacao,
    staleTime: Infinity,
  })

  const { data: regApSN = [] } = useQuery({
    queryKey: ['fiscal-reg-ap-sn'],
    queryFn: fiscalApi.listarRegApuracaoSN,
    staleTime: Infinity,
  })

  // Contratos do cliente selecionado como sugestões de valor/descrição
  const { data: contratos = [] } = useQuery({
    queryKey: ['contratos-cliente', clienteSelecionado?.id],
    queryFn: () => contratosApi.listar({ cliente_id: clienteSelecionado!.id }),
    enabled: !!clienteSelecionado,
  })

  // Processos do cliente selecionado (para vincular)
  const { data: processos = [] } = useQuery({
    queryKey: ['processos-cliente', clienteSelecionado?.id],
    queryFn: () => processosApi.listar({ cliente_id: clienteSelecionado!.id }),
    enabled: !!clienteSelecionado,
  })

  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: fiscalApi.emitir,
    retry: false, // POST não faz retry automático (risco de duplicação)
    onSuccess: (nf) => {
      // Cache CPF/email do pagador para próximas emissões
      setCachePagador(form.tomador_nome, form.tomador_cpf_cnpj, form.tomador_email)
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      onSucesso(nf)
    },
    onError: (err: any) => {
      const d = err?.response?.data?.detail
      if (typeof d === 'object') setErro(`[${d.codigo ?? '?'}] ${d.detalhe ?? d.message}`)
      else setErro(String(d ?? err?.message ?? 'Erro desconhecido'))
    },
  })

  function set<K extends keyof EmitirNFSeIn>(k: K, v: EmitirNFSeIn[K]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  const [erroCadastro, setErroCadastro] = useState<string | null>(null)
  const criarClienteMut = useMutation({
    mutationFn: () => clientesApi.criar({
      nome: form.tomador_nome,
      tipo: (form.tomador_cpf_cnpj || '').replace(/\D/g, '').length === 14 ? 'PJ' : 'PF',
      cpf_cnpj: form.tomador_cpf_cnpj || undefined,
      email: form.tomador_email || undefined,
      telefone: form.tomador_telefone || undefined,
    } as any),
    onSuccess: (c: Cliente) => {
      setErroCadastro(null)
      setClienteSelecionado(c)
      set('cliente_id', c.id)
      qc.invalidateQueries({ queryKey: ['clientes'] })
    },
    onError: (err: any) => {
      const d = err?.response?.data?.detail
      setErroCadastro(typeof d === 'string' ? d : (d?.message || err?.message || 'Falha ao cadastrar cliente'))
    },
  })
  const criarPaganteMut = useMutation({
    mutationFn: () => pagantesApi.criar({
      nome: form.tomador_nome,
      cpf_cnpj: form.tomador_cpf_cnpj || undefined,
      email: form.tomador_email || undefined,
      telefone: form.tomador_telefone || undefined,
    }),
    onSuccess: () => {
      setErroCadastro(null)
      setPaganteSelNome(form.tomador_nome)  // resolve o tomador → esconde o banner
      qc.invalidateQueries({ queryKey: ['pagantes'] })
    },
    onError: (err: any) => {
      const d = err?.response?.data?.detail
      setErroCadastro(typeof d === 'string' ? d : (d?.message || err?.message || 'Falha ao cadastrar pagante'))
    },
  })

  function aplicarTemplate(tipo: string) {
    const nome = form.tomador_nome || 'cliente'
    const cfgT = cfgFiscal?.templates_descricao?.find((t) => t.tipo === tipo)
    if (cfgT && cfgT.texto) {
      set('descricao_servico', cfgT.texto.replace(/\{cliente\}/g, nome))
      return
    }
    const tpl = TEMPLATES_DESCRICAO.find((t) => t.tipo === tipo)
    if (tpl) set('descricao_servico', tpl.texto(nome))
  }

  function handleClienteSelect(c: Cliente | null, nome: string) {
    setClienteSelecionado(c)
    setPaganteSelNome(null)  // ao mexer no tomador, limpa flag de pagante selecionado
    if (c) {
      setForm((f) => ({
        ...f,
        cliente_id: c.id,
        tomador_nome: c.nome,
        tomador_cpf_cnpj: (c.cpf_cnpj || '').replace(/\D/g, ''),
        tomador_email: c.email || f.tomador_email,
        tomador_telefone: (c.telefone || '').replace(/\D/g, '') || f.tomador_telefone,
      }))
    } else {
      setForm((f) => ({ ...f, cliente_id: undefined, tomador_nome: nome }))
    }
  }

  // Selecionou um pagante não-cliente: preenche tomador com dados do pagante (inclui endereço)
  function handlePaganteSelect(p: PaganteOut) {
    setClienteSelecionado(null)
    setPaganteSelNome(p.nome)
    setForm((f) => ({
      ...f,
      cliente_id: p.cliente_id || undefined,
      tomador_nome: p.nome,
      tomador_cpf_cnpj: (p.cpf_cnpj || '').replace(/\D/g, ''),
      tomador_email: p.email || f.tomador_email,
      tomador_telefone: (p.telefone || '').replace(/\D/g, '') || f.tomador_telefone,
      tomador_endereco: (p.logradouro || p.cep) ? {
        logradouro: p.logradouro || '',
        numero: p.numero || '',
        bairro: p.bairro || '',
        cod_municipio: p.cod_municipio || '',
        cep: p.cep || '',
        complemento: p.complemento || undefined,
      } : f.tomador_endereco,
    }))
  }

  function aplicarContrato(c: any) {
    if (c.valor_honorarios_num != null) set('valor_servicos', c.valor_honorarios_num)
    const desc = (c as any).objeto_texto_livre || c.descricao || ''
    if (desc) {
      set('descricao_servico',
        `Honorários advocatícios — ${desc.slice(0, 200)} — cliente ${form.tomador_nome}`)
    }
    set('contrato_id', c.id)
  }

  const temPrefill = !!(inicial?.tomador_nome)

  return (
    <div className={cs.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={cs.modal}>
        <button className={cs.closeBtn} onClick={onClose}>✕</button>
        <div className={cs.modalTitle}>
          {form.substitui_chave ? '📝 Emitir NFS-e de Substituição' : '🧾 Emitir NFS-e'}
        </div>

        {form.substitui_chave && (
          <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '10px 12px', marginBottom: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#1d4ed8' }}>Nota de substituição</div>
            <div style={{ fontSize: 12, color: '#374151', marginTop: 2 }}>
              Esta NF substituirá a anterior (chave …{form.substitui_chave.slice(-8)}). Corrija os dados
              que estavam errados e emita. A nota antiga será marcada como <b>substituída</b> automaticamente.
            </div>
          </div>
        )}

        {temPrefill && !form.substitui_chave && (
          <div className={cs.prefillBanner}>
            ✅ Dados pré-preenchidos do honorário. Revise e confirme antes de emitir.
          </div>
        )}

        {/* ── Dados do Emitente (colapsível) ─────────────────────────── */}
        <div className={cs.secaoColapsavel}>
          <button className={cs.colapsarBtn} onClick={() => setMostrarEmitente((v) => !v)}>
            {mostrarEmitente ? '▲' : '▶'} Dados do Emitente
            <span className={cs.colapsarLabel}>(Pimenta Judice — {PRESTADOR.cnpj})</span>
          </button>
          {mostrarEmitente && (
            <div className={cs.emitenteCaixa}>
              <div className={cs.emitenteRow}><b>CNPJ:</b> {PRESTADOR.cnpj}</div>
              <div className={cs.emitenteRow}><b>Nome:</b> {PRESTADOR.nome}</div>
              <div className={cs.emitenteRow}><b>Município:</b> {PRESTADOR.municipio}</div>
              <div className={cs.emitenteRow}><b>Regime:</b> {PRESTADOR.regime}</div>
              <div className={cs.emitenteRow}><b>CNAE:</b> {PRESTADOR.cnaePrincipal}</div>
              <p className={cs.fieldHint}>Para alterar os dados do emitente, acesse Configurações → Dados Fiscais.</p>
            </div>
          )}
        </div>

        <div className={cs.formGrid}>

          {/* ── Competência e Série ─────────────────────────────────── */}
          <div>
            <label className={cs.formLabel}>Competência *</label>
            <input type="month" className={cs.input} value={form.competencia}
              onChange={(e) => set('competencia', e.target.value)} />
          </div>
          <div>
            <label className={cs.formLabel}>Série</label>
            <input className={cs.input} value={form.serie}
              onChange={(e) => set('serie', e.target.value)}
              title="Normalmente '1'. Aumenta automaticamente a cada emissão." />
            <p className={cs.fieldHint}>Série "1" padrão. Número sequencial gerado automaticamente.</p>
          </div>

          {/* ── Tomador ─────────────────────────────────────────────── */}
          <div className={cs.formGridFull}>
            <div className={cs.secaoTitulo}>👤 Tomador do Serviço</div>
          </div>

          <div className={cs.formGridFull}>
            <ClienteSearch value={form.tomador_nome} onSelect={handleClienteSelect}
              incluirPagantes onSelectPagante={handlePaganteSelect} />

            {/* Tomador novo → cadastrar como cliente OU pagante */}
            {!clienteSelecionado && paganteSelNome !== form.tomador_nome && form.tomador_nome.trim().length > 2 && (
              <div className={cs.prefillBanner} style={{ marginTop: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                  <span>Tomador "<b>{form.tomador_nome.slice(0, 30)}</b>" não cadastrado. Cadastrar como:</span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button type="button" className={cs.templateBtn}
                      disabled={criarClienteMut.isPending || criarPaganteMut.isPending}
                      onClick={() => criarClienteMut.mutate()}
                      title="Cliente: entidade principal, com processos/contratos">
                      {criarClienteMut.isPending ? 'Criando…' : '👤 Cliente'}
                    </button>
                    <button type="button" className={cs.templateBtn}
                      disabled={criarClienteMut.isPending || criarPaganteMut.isPending}
                      onClick={() => criarPaganteMut.mutate()}
                      title="Pagante: quem paga a NF sem ser cliente (ex.: Ana Maria pagando pela Mangrove)">
                      {criarPaganteMut.isPending ? 'Criando…' : '💳 Pagante'}
                    </button>
                  </div>
                </div>
                {criarPaganteMut.isSuccess && (
                  <div style={{ fontSize: 11, color: '#15803d', marginTop: 6 }}>
                    ✓ Pagante cadastrado. Ele já aparece na busca de tomador.
                  </div>
                )}
                {erroCadastro && (
                  <div style={{ fontSize: 12, color: '#b91c1c', marginTop: 6 }}>⚠️ {erroCadastro}</div>
                )}
              </div>
            )}

            {/* Vínculo interno (NF contra empresa Y, mas organizar sob cliente X) */}
            <div style={{ marginTop: 6 }}>
              {clienteSelecionado && form.cliente_id === clienteSelecionado.id && !vincularOutro && (
                <button type="button" className={cs.colapsarBtn}
                  onClick={() => setVincularOutro(true)}>
                  🔗 Vincular a outro cliente (interno)
                  <span className={cs.colapsarLabel}>— NF contra empresa Y, organizada sob cliente X</span>
                </button>
              )}
              {clienteVinculadoNome && form.cliente_id !== clienteSelecionado?.id && (
                <div className={cs.fieldHint} style={{ color: '#065f46' }}>
                  🔗 Vinculada internamente a: <b>{clienteVinculadoNome}</b>{' '}
                  <button type="button" className={cs.templateBtn} style={{ marginLeft: 6 }}
                    onClick={() => { setVincularOutro(false); setClienteVinculadoNome(''); set('cliente_id', clienteSelecionado?.id) }}>
                    desfazer
                  </button>
                </div>
              )}
              {vincularOutro && (
                <div style={{ marginTop: 6 }}>
                  <ClienteSearch
                    value=""
                    label="Cliente vinculado (interno)"
                    placeholder="Buscar o cliente X para organizar a NF…"
                    onSelect={(c) => {
                      if (c) { set('cliente_id', c.id); setClienteVinculadoNome(c.nome); setVincularOutro(false) }
                    }}
                  />
                </div>
              )}
            </div>

            {/* ── COMPENSAÇÃO: pagamento por terceiro ─────────────────── */}
            {/* Caso: Ana Maria paga parte de recebível da Mangrove
                A NF é emitida contra Ana Maria (tomadora), mas o recebimento
                é creditado ao contrato da Mangrove. Cross-menu: Financeiro, Reembolsos, Lançamentos */}
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
              <label className={cs.checkboxLabel} style={{ marginBottom: 12, cursor: 'pointer' }}>
                <input type="checkbox"
                  checked={temCompensacao}
                  onChange={(e) => {
                    setTemCompensacao(e.target.checked)
                    if (!e.target.checked) {
                      set('cliente_compensacao_id', undefined)
                      set('contrato_compensacao_id', undefined)
                      set('honorario_compensacao_id', undefined)
                      set('valor_compensacao', undefined)
                      setNomeClienteCompensacao('')
                    }
                  }} />
                Esta NF compensa recebível de outro cliente (pessoa X paga por pessoa Y)
              </label>

              {temCompensacao && (
                <>
                  <div className={cs.fieldHint} style={{ background: '#f0fdf4', padding: 10, borderRadius: 6, marginBottom: 12 }}>
                    💡 <b>Cenário de compensação:</b> A NF é emitida contra <b>{form.tomador_nome || 'o pagante'}</b> (quem paga),
                    mas o crédito quita um recebível do <b>beneficiário</b>. <br/>Ex: Lucas paga e quita a dívida da Mangrove.
                    Ao marcar a NF como <b>paga</b>, o saldo devedor do recebível abaixo é reduzido.
                  </div>

                  <ClienteSearch
                    label="1) Cliente beneficiário (dono do recebível) *"
                    value={nomeClienteCompensacao}
                    placeholder="Buscar cliente Mangrove ou similar…"
                    onSelect={(c, nome) => {
                      setNomeClienteCompensacao(nome)
                      set('cliente_compensacao_id', c ? c.id : undefined)
                      set('honorario_compensacao_id', undefined)
                    }}
                  />

                  {form.cliente_compensacao_id && (
                    <div style={{ marginTop: 10 }}>
                      <label className={cs.formLabel}>2) Recebível (honorário) que será quitado *</label>
                      {honorariosBenef.filter(h => h.status !== 'pago' && h.status !== 'cancelado').length === 0 ? (
                        <p className={cs.fieldHint} style={{ color: '#b45309' }}>
                          Este cliente não tem honorários em aberto. Cadastre um no Financeiro primeiro.
                        </p>
                      ) : (
                        <select className={cs.input}
                          value={form.honorario_compensacao_id || ''}
                          onChange={(e) => {
                            const h = honorariosBenef.find(x => x.id === e.target.value)
                            set('honorario_compensacao_id', e.target.value || undefined)
                            // sugere o valor da compensação = menor entre valor da NF e saldo do recebível
                            if (h) set('valor_compensacao', Math.min(Number(form.valor_servicos) || h.saldo_pendente, h.saldo_pendente))
                          }}>
                          <option value="">— escolha o recebível —</option>
                          {honorariosBenef
                            .filter(h => h.status !== 'pago' && h.status !== 'cancelado')
                            .map(h => (
                              <option key={h.id} value={h.id}>
                                {h.descricao} — saldo {fmtBRL(h.saldo_pendente)}
                              </option>
                            ))}
                        </select>
                      )}
                    </div>
                  )}

                  {form.honorario_compensacao_id && (
                    <div style={{ marginTop: 10 }}>
                      <CurrencyField
                        label="Valor a compensar (quanto desta NF abate o recebível)"
                        value={Number(form.valor_compensacao) || 0}
                        onChange={(v) => set('valor_compensacao', v)} />
                      <p className={cs.fieldHint} style={{ marginTop: 6, fontSize: 12 }}>
                        Ao marcar esta NF como paga, será lançado um recebimento de {fmtBRL(Number(form.valor_compensacao) || 0)}{' '}
                        no recebível do beneficiário (aparece no Financeiro e no cadastro do cliente).
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          <div>
            <label className={cs.formLabel}>CPF / CNPJ *</label>
            <input className={cs.input}
              placeholder="CPF ou CNPJ"
              value={mascaraDocumento(form.tomador_cpf_cnpj)}
              onChange={(e) => set('tomador_cpf_cnpj', soAlfanum(e.target.value))}
              maxLength={18} />
            {form.tomador_cpf_cnpj && !form.tomador_no_exterior && (() => {
              const d = soAlfanum(form.tomador_cpf_cnpj)
              if (d.length !== 11 && d.length !== 14)
                return <p className={cs.fieldHint} style={{ color: '#b45309' }}>Documento incompleto</p>
              const { valido, tipo } = validaDocumento(form.tomador_cpf_cnpj)
              return valido
                ? <p className={cs.fieldHint} style={{ color: '#15803d' }}>✓ {tipo} válido</p>
                : <p className={cs.fieldHint} style={{ color: '#b91c1c' }}>✕ {tipo} inválido (confira os dígitos)</p>
            })()}
          </div>

          <div>
            <label className={cs.formLabel}>
              <input type="checkbox" checked={form.tomador_no_exterior}
                onChange={(e) => set('tomador_no_exterior', e.target.checked)}
                style={{ marginRight: 6 }} />
              Tomador no Exterior
            </label>
            {form.tomador_no_exterior && (
              <p className={cs.fieldHint} style={{ color: '#c2410c' }}>
                Para tomador exterior, informe o NIF e o código do país no endereço.
              </p>
            )}
          </div>

          <div>
            <label className={cs.formLabel}>E-mail</label>
            <input type="email" className={cs.input} placeholder="Para envio da NF pelo portal"
              value={form.tomador_email ?? ''} onChange={(e) => set('tomador_email', e.target.value)} />
          </div>

          <div>
            <label className={cs.formLabel}>Telefone</label>
            <input className={cs.input} placeholder="(27) 99999-9999"
              value={mascaraTelefone(form.tomador_telefone ?? '')}
              onChange={(e) => set('tomador_telefone', soDigitos(e.target.value))}
              maxLength={16} />
          </div>

          {/* ── Sugestões de contratos ──────────────────────────────── */}
          {contratos.length > 0 && (
            <div className={cs.formGridFull}>
              <div className={cs.secaoTitulo} style={{ color: '#065f46' }}>
                📄 Contratos vinculados — clique para pré-preencher valor e descrição
              </div>
              <div className={cs.contratosList}>
                {contratos.slice(0, 4).map((c) => (
                  <button key={c.id} className={cs.contratoChip}
                    type="button" onClick={() => aplicarContrato(c)}>
                    <span>{c.descricao || (c as any).objeto_texto_livre || 'Contrato'}</span>
                    {(c as any).valor_honorarios_num != null && (
                      <span className={cs.contratoValor}>{fmtBRL((c as any).valor_honorarios_num)}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── Vínculos (processo / contrato) ──────────────────────── */}
          {clienteSelecionado && (processos.length > 0 || contratos.length > 0) && (
            <>
              {processos.length > 0 && (
                <div>
                  <label className={cs.formLabel}>Vincular a Processo (opcional)</label>
                  <select className={cs.input}
                    value={form.processo_id ?? ''}
                    onChange={(e) => {
                      const pid = e.target.value || undefined
                      set('processo_id', pid)
                      const p = processos.find((x) => x.id === pid)
                      if (p) set('descricao_servico',
                        `Honorários advocatícios referentes ao Processo nº ${p.numero_cnj} — cliente ${form.tomador_nome}`)
                    }}>
                    <option value="">— Nenhum —</option>
                    {processos.map((p) => (
                      <option key={p.id} value={p.id}>{p.numero_cnj}</option>
                    ))}
                  </select>
                </div>
              )}
              {contratos.length > 0 && (
                <div>
                  <label className={cs.formLabel}>Vincular a Contrato (opcional)</label>
                  <select className={cs.input}
                    value={form.contrato_id ?? ''}
                    onChange={(e) => {
                      const cid = e.target.value || undefined
                      const ct = contratos.find((x) => x.id === cid)
                      if (ct) aplicarContrato(ct)
                      else set('contrato_id', undefined)
                    }}>
                    <option value="">— Nenhum —</option>
                    {contratos.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.descricao || (c as any).objeto_texto_livre || 'Contrato'}
                        {(c as any).valor_honorarios_num != null ? ` — ${fmtBRL((c as any).valor_honorarios_num)}` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </>
          )}

          {/* ── Serviço ─────────────────────────────────────────────── */}
          <div className={cs.formGridFull}>
            <div className={cs.secaoTitulo}>🔧 Serviço Prestado</div>
          </div>

          <div className={cs.formGridFull}>
            <SelectComDesc
              label="Código de Tributação Nacional"
              value={form.cod_tributacao_nacional ?? '171401'}
              onChange={(v) => set('cod_tributacao_nacional', v)}
              opcoes={codigosTrib.map((c) => ({ valor: c.codigo, label: `${c.codigo} — ${c.label}`, descricao: c.descricao }))}
              info="Código que define o tipo de serviço para fins fiscais (LC 116/2003). Para advocacia, use 171401."
            />
          </div>

          <div className={cs.formGridFull}>
            <label className={cs.formLabel}>Descrição do Serviço *</label>
            <div className={cs.templatesBtns}>
              {templates.filter((t) => t.label).map((t) => (
                <button key={t.tipo} type="button" className={cs.templateBtn}
                  onClick={() => aplicarTemplate(t.tipo)}>
                  {t.label}
                </button>
              ))}
            </div>
            <textarea className={cs.textarea} rows={3}
              value={form.descricao_servico}
              onChange={(e) => set('descricao_servico', e.target.value)}
              placeholder="Clique em um modelo acima ou escreva livremente…" />
          </div>

          {/* ── Valores ─────────────────────────────────────────────── */}
          <div className={cs.formGridFull}>
            <div className={cs.secaoTitulo}>💰 Valores</div>
          </div>

          <div className={cs.formGridFull}>
            <CurrencyField label="Valor dos Serviços" value={form.valor_servicos}
              onChange={(v) => set('valor_servicos', v)} required />
          </div>

          {/* ── Tributação ──────────────────────────────────────────── */}
          <div className={cs.formGridFull}>
            <div className={cs.secaoTitulo}>⚖️ Tributação</div>
          </div>

          <div className={cs.formGridFull}>
            <SelectComDesc
              label="Natureza da Operação"
              value={form.natureza_operacao ?? '1'}
              onChange={(v) => set('natureza_operacao', v)}
              opcoes={naturezasOp.map((o) => ({ valor: o.valor, label: o.label, descricao: o.descricao }))}
            />
          </div>

          <div className={cs.formGridFull}>
            <SelectComDesc
              label="Regime de Apuração dos Tributos"
              value={form.reg_apuracao_sn ?? '3'}
              onChange={(v) => set('reg_apuracao_sn', v)}
              opcoes={regApSN.map((o) => ({ valor: o.valor, label: o.label, descricao: o.descricao }))}
              info="Pré-selecionado: Regime de apuração dos tributos federais e municipais pelo Simples Nacional."
            />
          </div>

          <div className={cs.formGridFull}>
            <label className={cs.checkboxLabel}>
              <input type="checkbox" checked={form.iss_retido}
                onChange={(e) => set('iss_retido', e.target.checked)} />
              ISS retido pelo tomador
              <span title={
                'O tomador geralmente RETÉM os tributos quando:\n'
                + '• É órgão público (União, Estado, Município, autarquias)\n'
                + '• É a fonte pagadora obrigada (ex.: serviços com retenção de ISS pela lei municipal)\n'
                + '• Há contrato/CNPJ enquadrado em substituição tributária do ISS\n'
                + '• IRRF/INSS/PIS/COFINS/CSLL: tomador PJ paga a PJ acima dos limites legais\n'
                + 'Na dúvida, confirme com o contador. Pessoa física normalmente NÃO retém.'
              } style={{ marginLeft: 8, cursor: 'help', color: 'var(--teal)', fontWeight: 700 }}>
                ⓘ quando o tomador retém?
              </span>
            </label>
          </div>

          {/* ── Retenções (colapsível) ──────────────────────────────── */}
          <div className={cs.formGridFull}>
            <button type="button" className={cs.colapsarBtn}
              onClick={() => setMostrarRetencoes((v) => !v)}>
              {mostrarRetencoes ? '▲' : '▶'} Retenções na Fonte (IR, INSS, CSLL, COFINS, PIS)
              <span className={cs.colapsarLabel}>— normalmente aplicável a tomador PJ</span>
            </button>
            {mostrarRetencoes && (
              <div className={cs.retencaoGrid}>
                {([
                  ['retencao_ir',     'IR'],
                  ['retencao_inss',   'INSS'],
                  ['retencao_csll',   'CSLL'],
                  ['retencao_cofins', 'COFINS'],
                  ['retencao_pis',    'PIS'],
                ] as const).map(([campo, label]) => (
                  <CurrencyField key={campo} label={label}
                    value={(form[campo] as number) || 0}
                    onChange={(v) => set(campo, v as any)} />
                ))}
              </div>
            )}
          </div>

          {/* ── Intermediário (colapsível) ──────────────────────────── */}
          <div className={cs.formGridFull}>
            <button type="button" className={cs.colapsarBtn}
              onClick={() => setMostrarIntermed((v) => !v)}>
              {mostrarIntermed ? '▲' : '▶'} Intermediário do Serviço
              <span className={cs.colapsarLabel}>— opcional; somente se houver terceiro intermediando</span>
            </button>
            {mostrarIntermed && (
              <div className={cs.intermediarioGrid}>
                <div>
                  <label className={cs.formLabel}>CNPJ / CPF do Intermediário</label>
                  <input className={cs.input} placeholder="Apenas dígitos"
                    value={form.intermediario?.cpf_cnpj ?? ''}
                    onChange={(e) => set('intermediario', {
                      ...form.intermediario,
                      nome: form.intermediario?.nome ?? '',
                      cpf_cnpj: e.target.value.replace(/\D/g, ''),
                    })} />
                </div>
                <div>
                  <label className={cs.formLabel}>Nome do Intermediário</label>
                  <input className={cs.input}
                    value={form.intermediario?.nome ?? ''}
                    onChange={(e) => set('intermediario', {
                      ...form.intermediario,
                      cpf_cnpj: form.intermediario?.cpf_cnpj ?? '',
                      nome: e.target.value,
                    })} />
                </div>
              </div>
            )}
          </div>

        </div>

        {/* ── Valor líquido calculado ──────────────────────────────── */}
        {form.valor_servicos > 0 && (
          <div className={cs.resumoValores}>
            <span>Valor bruto: <strong>{fmtBRL(form.valor_servicos)}</strong></span>
            {((form.retencao_ir || 0) + (form.retencao_inss || 0) + (form.retencao_csll || 0) +
              (form.retencao_cofins || 0) + (form.retencao_pis || 0)) > 0 && (
              <>
                <span>Retenções: <strong style={{ color: '#b91c1c' }}>
                  {fmtBRL((form.retencao_ir || 0) + (form.retencao_inss || 0) +
                    (form.retencao_csll || 0) + (form.retencao_cofins || 0) + (form.retencao_pis || 0))}
                </strong></span>
                <span>Valor líquido: <strong style={{ color: '#15803d' }}>
                  {fmtBRL(form.valor_servicos - ((form.retencao_ir || 0) + (form.retencao_inss || 0) +
                    (form.retencao_csll || 0) + (form.retencao_cofins || 0) + (form.retencao_pis || 0)))}
                </strong></span>
              </>
            )}
          </div>
        )}

        {/* Modo teste (homologação) */}
        <div className={cs.formGridFull} style={{ marginTop: 14 }}>
          <label className={cs.checkboxLabel} style={{ color: form.ambiente === 2 ? '#b45309' : undefined }}>
            <input type="checkbox" checked={form.ambiente === 2}
              onChange={(e) => set('ambiente', e.target.checked ? 2 : undefined)} />
            🧪 Modo teste (homologação) — nota <b>sem valor fiscal</b>, não gera imposto
          </label>
        </div>

        {erro && <div className={cs.erroBox}>⚠️ {erro}</div>}

        <div className={cs.modalFooter}>
          <button className={cs.btnSecondary} onClick={onClose}>Cancelar</button>
          <button className={styles.btnPrimary}
            disabled={
              mutation.isPending ||
              !form.tomador_cpf_cnpj || !form.tomador_nome ||
              !form.valor_servicos || !form.descricao_servico ||
              (!form.tomador_no_exterior && !validaDocumento(form.tomador_cpf_cnpj).valido)
            }
            onClick={() => { setErro(null); mutation.mutate(form) }}>
            {mutation.isPending ? 'Emitindo…'
              : form.ambiente === 2 ? '🧪 Emitir TESTE' : '📤 Emitir NFS-e'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Modal de detalhe / cancelamento ────────────────────────────────────────

function DetalheModal({ nf, onClose, onSubstituir }: { nf: NotaFiscalOut; onClose: () => void; onSubstituir?: (nf: NotaFiscalOut) => void }) {
  const [motivo, setMotivo] = useState('')
  const [confirmando, setConfirmando] = useState(false)
  const [erroPdf, setErroPdf] = useState<string | null>(null)
  const [baixando, setBaixando] = useState(false)
  const [procIds, setProcIds] = useState<string[]>(nf.processos_ids ?? (nf.processo_id ? [nf.processo_id] : []))
  const [contrSel, setContrSel] = useState(nf.contrato_id ?? '')
  const [vincMsg, setVincMsg] = useState<string | null>(null)
  const [erroCancelamento, setErroCancelamento] = useState<string | null>(null)
  const [conciliando, setConciliando] = useState(false)
  const qc = useQueryClient()
  const cancelMut = useMutation({
    mutationFn: (m: string) => fiscalApi.cancelar(nf.id, m),
    retry: false, // POST sem retry (risco de duplicação de evento)
    onSuccess: () => {
      setErroCancelamento(null)
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      onClose()
    },
    onError: (err: any) => {
      const msg = err.response?.data?.detail || err.message || 'Falha ao cancelar NF-e'
      setErroCancelamento(msg)
    },
  })
  const { data: conciliaveis = [] } = useQuery({
    queryKey: ['conciliaveis', nf.id, conciliando],
    queryFn: () => fiscalApi.conciliaveis(nf.id),
    enabled: conciliando,
  })
  const conciliarMut = useMutation({
    mutationFn: (recId: string) => fiscalApi.conciliar(nf.id, recId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      qc.invalidateQueries({ queryKey: ['fluxo-caixa'] })
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      setConciliando(false); onClose()
    },
  })
  const desconciliarMut = useMutation({
    mutationFn: () => fiscalApi.desconciliar(nf.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      qc.invalidateQueries({ queryKey: ['fluxo-caixa'] })
      onClose()
    },
  })
  const { data: analise } = useQuery({
    queryKey: ['cancel-analise', nf.id, confirmando],
    queryFn: () => fiscalApi.analiseCancelamento(nf.id),
    enabled: confirmando,
  })

  // Vínculos internos: escolhe o cliente cujos processos/contratos serão listados
  const [clienteVincId, setClienteVincId] = useState<string | undefined>(nf.cliente_id)
  const { data: procs = [] } = useQuery({
    queryKey: ['proc-nf', clienteVincId],
    queryFn: () => processosApi.listar({ cliente_id: clienteVincId! }),
    enabled: !!clienteVincId,
  })
  const { data: contrs = [] } = useQuery({
    queryKey: ['contr-nf', clienteVincId],
    queryFn: () => contratosApi.listar({ cliente_id: clienteVincId! }),
    enabled: !!clienteVincId,
  })
  const vincMut = useMutation({
    mutationFn: () => fiscalApi.vincular(nf.id, {
      processos_ids: procIds.join(','), contrato_id: contrSel || undefined,
      cliente_id: clienteVincId || undefined }),
    onSuccess: () => { setVincMsg('✓ Vínculos salvos'); qc.invalidateQueries({ queryKey: ['notas-fiscais'] }) },
  })
  const toggleProc = (id: string) =>
    setProcIds((cur) => cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id])
  const [novoContrTitulo, setNovoContrTitulo] = useState('')
  const criarContrMut = useMutation({
    mutationFn: () => contratosApi.criar({ cliente_id: clienteVincId!, titulo: novoContrTitulo }),
    onSuccess: (c) => { setContrSel(c.id); setNovoContrTitulo(''); qc.invalidateQueries({ queryKey: ['contr-nf', clienteVincId] }) },
  })

  async function baixarPdf() {
    setErroPdf(null); setBaixando(true)
    try {
      const blob = await fiscalApi.baixarDanfse(nf.id)
      const url = URL.createObjectURL(blob as Blob)
      window.open(url, '_blank')
    } catch (err: any) {
      setErroPdf('Não foi possível gerar o PDF agora. Tente novamente em instantes.')
    } finally {
      setBaixando(false)
    }
  }

  return (
    <div className={cs.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={cs.modal}>
        <button className={cs.closeBtn} onClick={onClose}>✕</button>
        <div className={cs.modalTitle}>
          🧾 NFS-e
          {nf.numero_nfse && <span className={cs.nfNumero}> #{nf.numero_nfse}</span>}
          <span className={`${styles.badge} ${STATUS_CLASS[nf.status]}`}>{STATUS_LABEL[nf.status]}</span>
        </div>

        <div className={cs.detailGrid}>
          <span className={cs.detailLabel}>Competência</span>
          <span>{fmtCompetencia(nf.competencia)}</span>
          <span className={cs.detailLabel}>Emissão</span>
          <span>{fmtData(nf.data_emissao)}</span>
          <span className={cs.detailLabel}>Tomador</span>
          <span>{nf.tomador_nome}</span>
          <span className={cs.detailLabel}>CPF/CNPJ</span>
          <span>{nf.tomador_cpf_cnpj}</span>
          {nf.tomador_email && <><span className={cs.detailLabel}>E-mail</span><span>{nf.tomador_email}</span></>}
          <span className={cs.detailLabel}>Valor bruto</span>
          <span><strong>{fmtBRL(nf.valor_servicos)}</strong></span>
          {nf.valor_liquido !== nf.valor_servicos && (
            <><span className={cs.detailLabel}>Valor líquido</span>
            <span style={{ color: '#15803d' }}><strong>{fmtBRL(nf.valor_liquido)}</strong></span></>
          )}
          <span className={cs.detailLabel}>Descrição</span>
          <span>{nf.descricao_servico}</span>
          {nf.chave_acesso && (
            <><span className={cs.detailLabel}>Chave acesso</span>
            <span style={{ fontSize: 11, wordBreak: 'break-all' }}>{nf.chave_acesso}</span></>
          )}
          {nf.erro_mensagem && (
            <><span className={cs.detailLabel}>Erro</span>
            <span style={{ color: '#c2410c' }}>{nf.erro_mensagem}</span></>
          )}
          {nf.xml_nfse && (
            <><span className={cs.detailLabel}>XML</span>
            <pre className={cs.xmlBlock}>{nf.xml_nfse.slice(0, 2000)}</pre></>
          )}
        </div>

        {/* Vínculos internos — sempre disponível, qualquer cliente (info interna) */}
        <div style={{ marginTop: 16, padding: 12, background: 'var(--light)', borderRadius: 8 }}>
          <div className={cs.formLabel}>🔗 Vínculos internos (opcional, não altera a nota)</div>
          <div style={{ marginTop: 6 }}>
            <ClienteSearch value="" label="Cliente (de quem listar processos/contratos)"
              placeholder="Buscar cliente…"
              onSelect={(c) => { if (c) { setClienteVincId(c.id); setProcIds([]); setContrSel('') } }} />
          </div>
          {clienteVincId && (
            <div style={{ marginTop: 8 }}>
              <div className={cs.fieldHint} style={{ marginBottom: 4 }}>
                Processos {procs.length ? '(marque um ou mais)' : '(nenhum p/ este cliente)'}:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                {procs.map((p) => (
                  <label key={p.id} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4,
                    background: procIds.includes(p.id) ? 'var(--teal-light)' : 'var(--white)',
                    border: '1px solid var(--gray-border)', borderRadius: 6, padding: '4px 8px', cursor: 'pointer' }}>
                    <input type="checkbox" checked={procIds.includes(p.id)} onChange={() => toggleProc(p.id)} />
                    {p.numero_cnj}
                  </label>
                ))}
              </div>
              <select className={cs.input} value={contrSel} onChange={(e) => setContrSel(e.target.value)}>
                <option value="">— Contrato {contrs.length ? '' : '(nenhum)'} —</option>
                {contrs.map((c) => <option key={c.id} value={c.id}>{c.descricao || (c as any).titulo || 'Contrato'}</option>)}
              </select>
            </div>
          )}
          {clienteVincId && (
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <input className={cs.input} placeholder="Criar contrato: título…"
                value={novoContrTitulo} onChange={(e) => setNovoContrTitulo(e.target.value)} />
              <button className={cs.btnSecondary} disabled={!novoContrTitulo || criarContrMut.isPending}
                onClick={() => criarContrMut.mutate()}>
                {criarContrMut.isPending ? 'Criando…' : '+ Contrato'}
              </button>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
            <button className={cs.btnSecondary} disabled={vincMut.isPending || !clienteVincId} onClick={() => vincMut.mutate()}>
              {vincMut.isPending ? 'Salvando…' : 'Salvar vínculos'}
            </button>
            {vincMsg && <span className={cs.fieldHint} style={{ color: '#15803d' }}>{vincMsg}</span>}
          </div>
        </div>

        {nf.status === 'emitida' && (
          <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className={styles.btnPrimary} onClick={() => baixarPdf()} disabled={baixando}>
              {baixando ? 'Gerando…' : '📄 Baixar DANFSe (PDF)'}
            </button>
            {nf.consulta_publica_url && (
              <a className={cs.btnSecondary} href={nf.consulta_publica_url}
                target="_blank" rel="noopener noreferrer"
                style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>
                🔗 Consulta pública (portal)
              </a>
            )}
          </div>
        )}
        {erroPdf && <div className={cs.erroBox} style={{ marginTop: 8 }}>⚠️ {erroPdf}</div>}

        {/* Conciliação de caixa: liga a NF (fiscal) a um recebimento (PIX/caixa) sem duplicar */}
        {nf.status === 'emitida' && (
          <div style={{ marginTop: 16, padding: 12, background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#15803d' }}>💵 Conciliação de caixa</div>
            {nf.recebimento_id ? (
              <div style={{ marginTop: 6 }}>
                <div style={{ fontSize: 12, color: '#374151' }}>
                  ✓ Esta NF está conciliada a uma entrada de caixa (não duplica no Fluxo de Caixa).
                </div>
                <button className={cs.btnSecondary} style={{ marginTop: 8 }}
                  disabled={desconciliarMut.isPending}
                  onClick={() => desconciliarMut.mutate()}>
                  {desconciliarMut.isPending ? 'Desfazendo…' : 'Desfazer conciliação'}
                </button>
              </div>
            ) : !conciliando ? (
              <div style={{ marginTop: 6 }}>
                <div style={{ fontSize: 12, color: '#374151', marginBottom: 8 }}>
                  Se este pagamento já entrou no caixa (PIX/TED registrado como recebimento), concilie aqui:
                  a NF vira o selo "🧾 NF ✓" na linha da entrada e <b>não cria entrada nova</b>.
                </div>
                <button className={styles.btnPrimary} onClick={() => setConciliando(true)}>
                  Conciliar com entrada de caixa
                </button>
              </div>
            ) : (
              <div style={{ marginTop: 6 }}>
                {conciliaveis.length === 0 ? (
                  <p style={{ fontSize: 12, color: '#b45309' }}>
                    Nenhuma entrada de caixa disponível do cliente/beneficiário. Registre o recebimento (PIX) no Financeiro primeiro.
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {conciliaveis.map((r) => (
                      <button key={r.id} disabled={conciliarMut.isPending}
                        onClick={() => conciliarMut.mutate(r.id)}
                        style={{ textAlign: 'left', background: '#fff', border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px', cursor: 'pointer' }}>
                        <span style={{ fontWeight: 700 }}>{fmtBRL(r.valor)}</span> · {fmtData(r.data)} · {r.forma.toUpperCase()}
                        <div style={{ fontSize: 11, color: '#6b7280' }}>{r.cliente} — {r.honorario_descricao}</div>
                      </button>
                    ))}
                  </div>
                )}
                <button className={cs.btnSecondary} style={{ marginTop: 8 }} onClick={() => setConciliando(false)}>Cancelar</button>
              </div>
            )}
          </div>
        )}

        {nf.status === 'emitida' && (
          <div style={{ marginTop: 16 }}>
            {!confirmando ? (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className={styles.btnDanger} onClick={() => setConfirmando(true)}>
                  Cancelar NFS-e
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {analise && analise.alertas.map((a, i) => {
                  const cor = a.nivel === 'alerta' ? { bg: '#fef2f2', br: '#fecaca', fg: '#b91c1c' }
                    : a.nivel === 'atencao' ? { bg: '#fffbeb', br: '#fde68a', fg: '#b45309' }
                    : a.nivel === 'ok' ? { bg: '#f0fdf4', br: '#bbf7d0', fg: '#15803d' }
                    : { bg: '#f8fafc', br: '#e2e8f0', fg: '#475569' }
                  return (
                    <div key={i} style={{ background: cor.bg, border: `1px solid ${cor.br}`, borderRadius: 8, padding: '8px 10px' }}>
                      <div style={{ fontWeight: 700, fontSize: 12, color: cor.fg }}>{a.titulo}</div>
                      <div style={{ fontSize: 12, color: '#374151', marginTop: 2 }}>{a.detalhe}</div>
                    </div>
                  )
                })}
                {/* Opção de substituição: corrigir sem cancelar */}
                {onSubstituir && nf.chave_acesso && (
                  <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '10px 12px' }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: '#1d4ed8' }}>
                      💡 Prefere corrigir em vez de cancelar?
                    </div>
                    <div style={{ fontSize: 12, color: '#374151', marginTop: 2, marginBottom: 8 }}>
                      Emita uma <b>nota de substituição</b>: o sistema gera uma NF nova já corrigida que
                      substitui esta. Evita a retificação do DAS de um simples cancelamento.
                    </div>
                    <button className={styles.btnPrimary} style={{ fontSize: 12 }}
                      onClick={() => onSubstituir(nf)}>
                      📝 Emitir nota de substituição
                    </button>
                  </div>
                )}
                {erroCancelamento && (
                  <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '10px', marginTop: 8 }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: '#b91c1c' }}>⚠️ Erro ao cancelar</div>
                    <div style={{ fontSize: 12, color: '#374151', marginTop: 4, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {erroCancelamento}
                    </div>
                  </div>
                )}
                {cancelMut.isPending && (
                  <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 8, padding: '10px', marginTop: 8 }}>
                    <div style={{ fontSize: 12, color: '#0369a1', fontWeight: 600 }}>⏳ Aguardando resposta da API Sefin...</div>
                    <div style={{ fontSize: 11, color: '#0c4a6e', marginTop: 4 }}>
                      Pode levar até 60 segundos. Não feche esta tela.
                    </div>
                  </div>
                )}
                <label className={cs.formLabel}>Motivo *</label>
                <input className={cs.input} placeholder="Mínimo 15 caracteres"
                  value={motivo} onChange={(e) => setMotivo(e.target.value)}
                  disabled={cancelMut.isPending} />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className={styles.btnDanger}
                    disabled={motivo.length < 15 || cancelMut.isPending}
                    onClick={() => cancelMut.mutate(motivo)}>
                    {cancelMut.isPending ? 'Conectando ao Sefin…' : 'Confirmar cancelamento'}
                  </button>
                  <button className={cs.btnSecondary} onClick={() => { setConfirmando(false); setErroCancelamento(null) }}
                    disabled={cancelMut.isPending}>
                    Voltar
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <div className={cs.modalFooter}>
          <button className={cs.btnSecondary} onClick={onClose}>Fechar</button>
        </div>
      </div>
    </div>
  )
}

// ─── Fila "A emitir" (sugestões vindas do extrato bancário) ───────────────────

function SugestoesNFSection({ onEmitir }: { onEmitir: (s: SugestaoNF) => void }) {
  const qc = useQueryClient()
  const { data: sugestoes = [] } = useQuery({
    queryKey: ['sugestoes-nf'],
    queryFn: () => backofficeApi.listarSugestoesNf('pendente'),
  })
  const { data: reembolsos = [] } = useQuery({ queryKey: ['reembolsos'], queryFn: () => reembolsosApi.listar() })
  const { data: clientes = [] } = useQuery({ queryKey: ['clientes'], queryFn: () => clientesApi.listar() })
  const cliNome = (id: string) => clientes.find(c => c.id === id)?.nome ?? '—'
  const reembMap = Object.fromEntries(reembolsos.map(r => [r.id, r]))

  const ignorar = useMutation({
    mutationFn: (id: string) => backofficeApi.patchSugestaoNf(id, { status: 'ignorada' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sugestoes-nf'] }),
  })
  const vincular = useMutation({
    mutationFn: ({ id, ids }: { id: string; ids: string[] }) => backofficeApi.patchSugestaoNf(id, { reembolso_ids: ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sugestoes-nf'] }),
  })
  // Item 4: concluir o vínculo a reembolso → sai da fila (status 'vinculada')
  const concluirVinculo = useMutation({
    mutationFn: (id: string) => backofficeApi.patchSugestaoNf(id, { status: 'vinculada' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sugestoes-nf'] }),
  })
  // Item 5: vincular a entrada a uma NF já emitida → sai da fila
  const vincularNf = useMutation({
    mutationFn: ({ id, nfId }: { id: string; nfId: string }) =>
      backofficeApi.patchSugestaoNf(id, { nota_fiscal_id: nfId, status: 'emitida' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sugestoes-nf'] }),
  })
  const { data: nfsEmitidas = [] } = useQuery({
    queryKey: ['notas-fiscais', 'emitida'],
    queryFn: () => fiscalApi.listar({ status: 'emitida' }),
  })
  const [aberto, setAberto] = useState(true)
  const [vinculando, setVinculando] = useState<string | null>(null)
  const [linkandoNf, setLinkandoNf] = useState<string | null>(null)

  if (sugestoes.length === 0) return null
  const fmt = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
  const pastasOpts = reembolsos
    .filter(r => r.status !== 'cancelado')
    .map(r => ({ value: r.id, label: `${cliNome(r.cliente_id)} — ${r.titulo}${r.status === 'pago' ? ' (pago)' : r.status === 'rascunho' ? ' (rascunho)' : ''}` }))

  return (
    <div style={{ background: '#fff', borderRadius: 12, boxShadow: 'var(--shadow-card)', marginBottom: 20, overflow: 'hidden', border: '1px solid #bfdbfe' }}>
      <div
        style={{ padding: '12px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', background: '#eff6ff' }}
        onClick={() => setAberto(a => !a)}
      >
        <div style={{ fontWeight: 700, fontSize: 14, color: '#1e3a8a' }}>
          📥 A emitir — {sugestoes.length} sugestão(ões) do extrato
        </div>
        <span style={{ fontSize: 12, color: '#1e3a8a' }}>{aberto ? '▲' : '▼'}</span>
      </div>
      {aberto && (
        <div style={{ padding: '8px 0' }}>
          {sugestoes.map(s => {
            const tipo = s.tipo_sugerido === 'reembolso_recebido'
              ? { txt: 'Reembolso recebido', bg: '#e0e7ff', fg: '#3730a3' }
              : s.tipo_sugerido === 'outro' ? { txt: 'Outro', bg: '#f3f4f6', fg: '#6b7280' }
              : { txt: 'Receita', bg: '#dcfce7', fg: '#15803d' }
            const vinc = s.reembolso_ids ?? []
            return (
              <div key={s.id} style={{ borderTop: '1px solid #f3f4f6' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr 120px 110px auto', gap: 10, alignItems: 'center', padding: '8px 18px' }}>
                  <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>{s.data ?? '—'}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {s.pagador}
                      {vinc.length > 0 && (
                        <span style={{ marginLeft: 6, fontSize: 9, background: '#e0e7ff', color: '#3730a3', padding: '1px 6px', borderRadius: 999, fontWeight: 700 }}
                          title={vinc.map(id => reembMap[id] ? `${cliNome(reembMap[id].cliente_id)} — ${reembMap[id].titulo}` : id).join('\n')}>
                          🔗 {vinc.length === 1 && reembMap[vinc[0]] ? cliNome(reembMap[vinc[0]].cliente_id) : `${vinc.length} reemb.`}
                        </span>
                      )}
                    </div>
                    {s.descricao && <div style={{ fontSize: 11, color: 'var(--gray-mid)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.descricao}</div>}
                  </div>
                  <span style={{ fontSize: 10, background: tipo.bg, color: tipo.fg, padding: '2px 8px', borderRadius: 999, fontWeight: 700, textAlign: 'center', whiteSpace: 'nowrap' }}>{tipo.txt}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{fmt(s.valor)}</span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className={styles.btnPrimary} style={{ padding: '5px 12px', fontSize: 12 }} onClick={() => onEmitir(s)}>Emitir</button>
                    <button className={cs.btnSecondary} style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => { setLinkandoNf(linkandoNf === s.id ? null : s.id); setVinculando(null) }}>🧾 NF existente</button>
                    <button className={cs.btnSecondary} style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => { setVinculando(vinculando === s.id ? null : s.id); setLinkandoNf(null) }}>🔗 Reembolso</button>
                    <button className={styles.btnDanger} style={{ padding: '5px 10px', fontSize: 12 }} disabled={ignorar.isPending} onClick={() => ignorar.mutate(s.id)}>Ignorar</button>
                  </div>
                </div>
                {linkandoNf === s.id && (
                  <div style={{ padding: '4px 18px 12px', background: '#f8fafc' }}>
                    <div style={{ fontSize: 11, color: 'var(--gray-mid)', marginBottom: 6 }}>
                      Vincular este crédito a uma NFS-e já emitida (sai da fila):
                    </div>
                    <select
                      value=""
                      onChange={(e) => { if (e.target.value) vincularNf.mutate({ id: s.id, nfId: e.target.value }) }}
                      style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, maxWidth: 420, width: '100%', fontFamily: 'Archivo, sans-serif' }}
                    >
                      <option value="">+ escolher NFS-e emitida…</option>
                      {nfsEmitidas.map(n => (
                        <option key={n.id} value={n.id}>
                          {(n.numero_nfse ? `#${n.numero_nfse} · ` : '')}{n.tomador_nome} · {fmt(n.valor_servicos)} · {n.competencia}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                {vinculando === s.id && (
                  <div style={{ padding: '4px 18px 12px', background: '#f8fafc' }}>
                    <div style={{ fontSize: 11, color: 'var(--gray-mid)', marginBottom: 6 }}>
                      Vincular este crédito a pasta(s) de reembolso (abertas, rascunho ou pagas):
                    </div>
                    {vinc.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
                        {vinc.map(id => (
                          <span key={id} style={{ fontSize: 11, background: '#e0e7ff', color: '#3730a3', padding: '2px 8px', borderRadius: 999, fontWeight: 600, display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                            {reembMap[id] ? `${cliNome(reembMap[id].cliente_id)} — ${reembMap[id].titulo}` : id.slice(0, 8)}
                            <span style={{ cursor: 'pointer' }} onClick={() => vincular.mutate({ id: s.id, ids: vinc.filter(x => x !== id) })}>×</span>
                          </span>
                        ))}
                      </div>
                    )}
                    <select
                      value=""
                      onChange={(e) => { if (e.target.value && !vinc.includes(e.target.value)) vincular.mutate({ id: s.id, ids: [...vinc, e.target.value] }) }}
                      style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, maxWidth: 360, width: '100%', fontFamily: 'Archivo, sans-serif' }}
                    >
                      <option value="">+ vincular pasta de reembolso…</option>
                      {pastasOpts.filter(o => !vinc.includes(o.value)).map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                    {vinc.length > 0 && (
                      <button className={styles.btnPrimary} style={{ marginTop: 10, padding: '6px 14px', fontSize: 12 }}
                        disabled={concluirVinculo.isPending}
                        onClick={() => concluirVinculo.mutate(s.id)}>
                        {concluirVinculo.isPending ? 'Concluindo…' : '✓ Concluir vínculo (sair da fila)'}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── Página principal ────────────────────────────────────────────────────────

type Filtro = 'todas' | 'emitida' | 'rascunho' | 'cancelada' | 'erro'

export default function FiscalPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [filtro, setFiltro] = useState<Filtro>('todas')
  const [emitindo, setEmitindo] = useState(false)
  const [prefill, setPrefill] = useState<Partial<EmitirNFSeIn> | undefined>()
  // Quando a emissão parte de uma sugestão da fila, guardamos o id para marcá-la depois.
  const [sugestaoEmitindo, setSugestaoEmitindo] = useState<string | null>(null)
  const [nfDetalhe, setNfDetalhe] = useState<NotaFiscalOut | null>(null)
  const [nfEmitida, setNfEmitida] = useState<NotaFiscalOut | null>(null)
  const [sincronizando, setSincronizando] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [dtIni, setDtIni] = useState('')
  const [dtFim, setDtFim] = useState('')
  const [colapsados, setColapsados] = useState<Record<string, boolean>>({})

  const { data: notas = [], isLoading } = useQuery({
    queryKey: ['notas-fiscais', filtro],
    queryFn: () => fiscalApi.listar(filtro !== 'todas' ? { status: filtro } : undefined),
  })

  const qc = useQueryClient()
  // Modal de data ao marcar pago
  const [pagandoNf, setPagandoNf] = useState<NotaFiscalResumo | null>(null)
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10))
  const pagoMut = useMutation({
    mutationFn: ({ id, pago, data }: { id: string; pago: boolean; data?: string }) =>
      fiscalApi.marcarPago(id, pago, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
      setPagandoNf(null)
    },
  })
  // Anti-duplicação: ao marcar pago, procura entradas de caixa já existentes
  // (mesmo cliente/beneficiário) para conciliar em vez de criar uma nova.
  const { data: conciliaveisPago = [] } = useQuery({
    queryKey: ['conciliaveis', pagandoNf?.id],
    queryFn: () => fiscalApi.conciliaveis(pagandoNf!.id),
    enabled: !!pagandoNf,
  })
  const conciliarPagoMut = useMutation({
    mutationFn: ({ id, recId }: { id: string; recId: string }) => fiscalApi.conciliar(id, recId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      qc.invalidateQueries({ queryKey: ['fluxo-caixa'] })
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
      setPagandoNf(null)
    },
  })

  function toggleGrupo(chave: string) {
    setColapsados((c) => ({ ...c, [chave]: !c[chave] }))
  }
  function labelGrupo(chave: string) {
    const [ano, mes] = chave.split('-')
    const m = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    return `${m[parseInt(mes) - 1]}/${ano}`
  }

  // Filtra por data de emissão, agrupa por competência (ano-mês), ordena nº desc
  const mesCorrente = new Date().toISOString().slice(0, 7)
  const grupos = useMemo(() => {
    let lista = notas.filter((n) => {
      if (dtIni && (!n.data_emissao || n.data_emissao < dtIni)) return false
      if (dtFim && (!n.data_emissao || n.data_emissao > dtFim)) return false
      return true
    })
    const map: Record<string, typeof notas> = {}
    for (const n of lista) {
      const k = n.competencia
      ;(map[k] ||= []).push(n)
    }
    const entradas = Object.entries(map).sort((a, b) => b[0].localeCompare(a[0]))
    for (const [, arr] of entradas) {
      arr.sort((a, b) => (parseInt(b.numero_nfse || '0') || 0) - (parseInt(a.numero_nfse || '0') || 0))
    }
    return entradas
  }, [notas, dtIni, dtFim])

  // Colapsa automaticamente meses já fechados (anteriores ao corrente)
  useEffect(() => {
    setColapsados((cur) => {
      const next = { ...cur }
      for (const [chave] of grupos) {
        if (!(chave in next)) next[chave] = chave < mesCorrente
      }
      return next
    })
  }, [grupos.length]) // eslint-disable-line

  // Abrir uma NF específica vinda do Fluxo de Caixa (?nf=<id>)
  useEffect(() => {
    const nfId = searchParams.get('nf')
    if (!nfId) return
    fiscalApi.obter(nfId).then((nf) => {
      setNfDetalhe(nf)
      setSearchParams({})
    }).catch(() => setSearchParams({}))
  }, []) // eslint-disable-line

  // Pré-fill vindo do Financeiro (?honorario=&recebimento=)
  useEffect(() => {
    const hId = searchParams.get('honorario')
    const rId = searchParams.get('recebimento') ?? undefined
    if (!hId) return
    fiscalApi.prefillDeHonorario(hId, rId).then((d) => {
      setPrefill({
        competencia: d.competencia,
        tomador_cpf_cnpj: d.tomador_cpf_cnpj ?? '',
        tomador_nome: d.tomador_nome ?? '',
        tomador_email: d.tomador_email ?? '',
        tomador_telefone: d.tomador_telefone ?? '',
        valor_servicos: d.valor_servicos,
        descricao_servico: d.descricao_servico,
        honorario_id: d.honorario_id,
        recebimento_id: d.recebimento_id,
        contrato_id: d.contrato_id,
      })
      setEmitindo(true)
      setSearchParams({})
    })
  }, []) // eslint-disable-line

  const filtros: { key: Filtro; label: string }[] = [
    { key: 'todas', label: 'Todas' },
    { key: 'emitida', label: 'Emitidas' },
    { key: 'rascunho', label: 'Rascunho' },
    { key: 'erro', label: 'Erro' },
    { key: 'cancelada', label: 'Canceladas' },
  ]

  // Abre a emissão pré-preenchida com os dados da NF antiga, marcada como substituição.
  // O usuário corrige o que estava errado e emite; a antiga vira "substituída".
  function abrirSubstituicao(nf: NotaFiscalOut) {
    setNfDetalhe(null); setNfEmitida(null)
    setPrefill({
      competencia: nf.competencia,
      tomador_cpf_cnpj: nf.tomador_cpf_cnpj,
      tomador_nome: nf.tomador_nome,
      tomador_email: nf.tomador_email || '',
      descricao_servico: nf.descricao_servico,
      valor_servicos: nf.valor_servicos,
      cod_tributacao_nacional: nf.cod_tributacao_nacional,
      cliente_id: nf.cliente_id,
      contrato_id: nf.contrato_id,
      honorario_id: nf.honorario_id,
      // Marca como substituição da NF antiga
      substitui_chave: nf.chave_acesso,
      substitui_nf_id: nf.id,
      motivo_substituicao: 'Substituicao por correcao de dados',
    })
    setEmitindo(true)
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Notas Fiscais <strong>NFS-e</strong></h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className={cs.btnSecondary} disabled={sincronizando}
            onClick={async () => {
              setSincronizando(true); setSyncMsg(null)
              try {
                const r = await fiscalApi.sincronizarDfe()
                setSyncMsg(`✓ ${r.novas} nova(s) importada(s) do governo`)
                qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
              } catch { setSyncMsg('⚠️ Falha ao sincronizar') }
              finally { setSincronizando(false) }
            }}>
            {sincronizando ? 'Sincronizando…' : '🔄 Sincronizar do governo'}
          </button>
          <button className={styles.btnPrimary} onClick={() => { setPrefill(undefined); setEmitindo(true) }}>
            + Emitir NFS-e
          </button>
        </div>
      </div>
      {syncMsg && <p className={cs.fieldHint} style={{ marginTop: -12, marginBottom: 12 }}>{syncMsg}</p>}

      {/* Fila de sugestões de NF vindas do extrato bancário */}
      <SugestoesNFSection onEmitir={(s) => {
        const comp = s.competencia || (s.data ? s.data.slice(0, 7) : undefined)
        setPrefill({
          ...(comp ? { competencia: comp } : {}),
          tomador_nome: s.pagador,
          valor_servicos: s.valor as any,
          descricao_servico: s.descricao || `Honorários advocatícios — ${s.pagador}`,
        })
        setSugestaoEmitindo(s.id)
        setEmitindo(true)
      }} />

      <div className={cs.filtros}>
        {filtros.map((f) => (
          <button key={f.key}
            className={`${cs.filtroBtn} ${filtro === f.key ? cs.filtroBtnActive : ''}`}
            onClick={() => setFiltro(f.key)}>
            {f.label}
          </button>
        ))}
        <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--gray-mid)' }}>Emissão de</span>
        <input type="date" className={cs.input} style={{ width: 150 }} value={dtIni}
          onChange={(e) => setDtIni(e.target.value)} />
        <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>até</span>
        <input type="date" className={cs.input} style={{ width: 150 }} value={dtFim}
          onChange={(e) => setDtFim(e.target.value)} />
        {(dtIni || dtFim) && (
          <button className={cs.filtroBtn} onClick={() => { setDtIni(''); setDtFim('') }}>limpar</button>
        )}
      </div>

      <div className={styles.tableCard}>
        {isLoading ? (
          <div className={styles.empty}>Carregando…</div>
        ) : grupos.length === 0 ? (
          <div className={styles.empty}>
            Nenhuma nota fiscal encontrada.<br />
            <small>Clique em "+ Emitir NFS-e" para emitir a primeira.</small>
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Nº NFS-e</th><th>Tomador</th><th>Valor</th><th>Líquido</th>
                <th>Emissão</th><th>Status</th><th>Pago</th><th></th>
              </tr>
            </thead>
            <tbody>
              {grupos.map(([chave, lista]) => (
                <React.Fragment key={chave}>
                  <tr style={{ background: 'var(--light)', cursor: 'pointer' }}
                    onClick={() => toggleGrupo(chave)}>
                    <td colSpan={8} style={{ fontWeight: 700, fontSize: 13 }}>
                      {colapsados[chave] ? '▸' : '▾'} {labelGrupo(chave)} · {lista.length} nota(s)
                      <span style={{ fontWeight: 400, color: 'var(--gray-mid)', marginLeft: 8 }}>
                        {fmtBRL(lista.reduce((s, n) => s + n.valor_servicos, 0))}
                      </span>
                    </td>
                  </tr>
                  {!colapsados[chave] && lista.map((nf) => (
                    <tr key={nf.id}>
                      <td><strong>{nf.numero_nfse ?? '—'}</strong>
                        {nf.origem === 'dfe' && (
                          <span className={styles.badge} style={{ marginLeft: 4, background: '#e0e7ff', color: '#3730a3' }}>importada</span>
                        )}
                      </td>
                      <td>{nf.tomador_nome}</td>
                      <td>{fmtBRL(nf.valor_servicos)}</td>
                      <td>{fmtBRL(nf.valor_liquido)}</td>
                      <td>{fmtData(nf.data_emissao)}</td>
                      <td>
                        <span className={`${styles.badge} ${STATUS_CLASS[nf.status]}`}>{STATUS_LABEL[nf.status]}</span>
                        {nf.ambiente === 2 && (
                          <span className={styles.badge} style={{ marginLeft: 4, background: '#fef3c7', color: '#b45309' }}>TESTE</span>
                        )}
                      </td>
                      <td>
                        {nf.status === 'emitida' ? (
                          nf.pago ? (
                            <button className={styles.btnTable}
                              style={{ background: '#dcfce7', color: '#15803d', borderColor: '#bbf7d0' }}
                              onClick={() => pagoMut.mutate({ id: nf.id, pago: false })}>
                              ✓ Pago
                            </button>
                          ) : (
                            <button className={styles.btnTable}
                              onClick={() => { setPagandoNf(nf); setDataPagamento(new Date().toISOString().slice(0, 10)) }}>
                              Marcar pago
                            </button>
                          )
                        ) : (
                          <span style={{ fontSize: 11, color: '#9ca3af' }}>—</span>
                        )}
                      </td>
                      <td>
                        <button className={styles.btnTable} onClick={() => fiscalApi.obter(nf.id).then(setNfDetalhe)}>Ver</button>
                      </td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {emitindo && (
        <EmissaoModal
          inicial={prefill}
          onClose={() => { setEmitindo(false); setPrefill(undefined); setSugestaoEmitindo(null) }}
          onSucesso={(nf) => {
            setEmitindo(false); setPrefill(undefined)
            setNfEmitida(nf)
            // Se veio de uma sugestão da fila, marca como emitida e vincula a NF
            if (sugestaoEmitindo) {
              backofficeApi.patchSugestaoNf(sugestaoEmitindo, { status: 'emitida', nota_fiscal_id: nf.id })
                .finally(() => { setSugestaoEmitindo(null); qc.invalidateQueries({ queryKey: ['sugestoes-nf'] }) })
            }
            qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
          }}
        />
      )}

      {nfEmitida && <DetalheModal nf={nfEmitida} onClose={() => setNfEmitida(null)} onSubstituir={abrirSubstituicao} />}
      {nfDetalhe && !nfEmitida && <DetalheModal nf={nfDetalhe} onClose={() => setNfDetalhe(null)} onSubstituir={abrirSubstituicao} />}

      {/* Modal: data do pagamento ao marcar pago */}
      {pagandoNf && (() => {
        const val = pagandoNf.valor_servicos
        // Ordena: entradas de valor igual primeiro (prováveis o mesmo pagamento)
        const matches = [...conciliaveisPago].sort((a, b) =>
          Math.abs(a.valor - val) - Math.abs(b.valor - val))
        const temIgual = matches.some((m) => Math.abs(m.valor - val) < 0.01)
        return (
        <div className={cs.overlay} onClick={(e) => e.target === e.currentTarget && setPagandoNf(null)}>
          <div className={cs.modal} style={{ maxWidth: 440 }}>
            <button className={cs.closeBtn} onClick={() => setPagandoNf(null)}>✕</button>
            <div className={cs.modalTitle}>Marcar NFS-e como paga</div>
            <p style={{ fontSize: 13, color: '#374151', margin: '8px 0 4px' }}>
              {pagandoNf.tomador_nome} · {fmtBRL(val)}
            </p>

            {/* Anti-duplicação: entradas de caixa já existentes */}
            {matches.length > 0 && (
              <div style={{ background: temIgual ? '#fffbeb' : '#f9fafb', border: `1px solid ${temIgual ? '#fde68a' : '#e5e7eb'}`, borderRadius: 8, padding: 10, marginTop: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: temIgual ? '#b45309' : '#374151' }}>
                  {temIgual ? '⚠️ Já existe entrada de caixa deste valor. É este pagamento?' : 'Entradas de caixa do cliente — é uma delas?'}
                </div>
                <div style={{ fontSize: 11, color: '#6b7280', margin: '2px 0 8px' }}>
                  Conciliar evita lançar o dinheiro duas vezes no Fluxo de Caixa.
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {matches.slice(0, 5).map((r) => {
                    const igual = Math.abs(r.valor - val) < 0.01
                    return (
                      <button key={r.id} disabled={conciliarPagoMut.isPending}
                        onClick={() => conciliarPagoMut.mutate({ id: pagandoNf.id, recId: r.id })}
                        style={{ textAlign: 'left', background: '#fff', border: `1px solid ${igual ? '#86efac' : '#d1d5db'}`, borderRadius: 6, padding: '7px 10px', cursor: 'pointer' }}>
                        <span style={{ fontWeight: 700, color: igual ? '#15803d' : '#374151' }}>{fmtBRL(r.valor)}</span>
                        {igual && <span style={{ fontSize: 10, color: '#15803d', marginLeft: 6 }}>• mesmo valor</span>}
                        <span style={{ color: '#6b7280' }}> · {fmtData(r.data)} · {r.forma.toUpperCase()}</span>
                        <div style={{ fontSize: 11, color: '#6b7280' }}>{r.cliente} — {r.honorario_descricao}</div>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            <div style={{ marginTop: 14, paddingTop: 12, borderTop: matches.length > 0 ? '1px solid #e5e7eb' : 'none' }}>
              <label className={cs.formLabel}>
                {matches.length > 0 ? 'Nenhuma acima? Registrar nova entrada na data:' : 'Data do pagamento *'}
              </label>
              <input type="date" className={cs.input}
                value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} />
              <p className={cs.fieldHint} style={{ marginTop: 6, fontSize: 12 }}>
                Cria um recebimento novo no Financeiro nesta data (mês {fmtCompetencia(dataPagamento.slice(0, 7))}).
              </p>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className={temIgual ? cs.btnSecondary : styles.btnPrimary}
                  disabled={!dataPagamento || pagoMut.isPending}
                  onClick={() => pagoMut.mutate({ id: pagandoNf.id, pago: true, data: dataPagamento })}>
                  {pagoMut.isPending ? 'Salvando…' : temIgual ? 'Criar nova mesmo assim' : 'Confirmar pagamento'}
                </button>
                <button className={cs.btnSecondary} onClick={() => setPagandoNf(null)}>Cancelar</button>
              </div>
            </div>
          </div>
        </div>
        )
      })()}
    </div>
  )
}
