import { Fragment, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  backofficeApi,
  type Despesa,
  type DespesaRecorrente,
  type Fornecedor,
  type ParsedExpense,
  type ParsedEntrada,
  type Adiantamento,
  type AlocarItem,
} from '../api/backoffice'
import { reembolsosApi } from '../api/reembolsos'
import { clientesApi } from '../api/clientes'
import styles from './Page.module.css'

// Categorias que disparam o vínculo com reembolso (despesa paga em nome do cliente)
function ehReembolsavel(categoria: string): boolean {
  const c = (categoria || '').toLowerCase()
  return c.includes('reembols') || c.includes('cliente')
}

function fmtDataCurta(iso?: string | null) {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-')
  return d && m && y ? `${d}/${m}/${y.slice(2)}` : ''
}

// Rótulo de pasta de reembolso no combobox, com cliente, título e datas
function labelPasta(r: { titulo: string; data_emissao: string; status: string; updated_at: string }, cliente: string): string {
  const aberta = fmtDataCurta(r.data_emissao)
  const pago = r.status === 'pago' ? ` · pago ${fmtDataCurta(r.updated_at)}` : ''
  return `${cliente} — ${r.titulo} · aberto ${aberta}${pago}`
}

function fmtBRL(v: number) {
  return (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function fmtNum(v: number) {
  return (v ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function parseNum(s: string): number {
  if (!s) return 0
  // Remove tudo exceto dígitos, vírgula e ponto. Trata "1.234,56" e "1234.56".
  const cleaned = s.replace(/[^\d.,-]/g, '')
  // Se tem vírgula, ela é o decimal e os pontos são milhares
  if (cleaned.includes(',')) {
    return parseFloat(cleaned.replace(/\./g, '').replace(',', '.')) || 0
  }
  return parseFloat(cleaned) || 0
}
function fmtCNPJ(s: string) {
  const d = s.replace(/\D/g, '').slice(0, 14)
  if (d.length <= 2) return d
  if (d.length <= 5) return `${d.slice(0,2)}.${d.slice(2)}`
  if (d.length <= 8) return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5)}`
  if (d.length <= 12) return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8)}`
  return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}`
}

// Input monetário X.XXX,XX — guarda texto formatado, expõe valor numérico via onValue
function MoneyInput({
  value,
  onValue,
  style,
  disabled,
}: {
  value: number
  onValue: (n: number) => void
  style?: React.CSSProperties
  disabled?: boolean
}) {
  const [text, setText] = useState(value ? fmtNum(value) : '')
  // Sincroniza quando value muda externamente
  const lastSyncedRef = useRef(value)
  if (lastSyncedRef.current !== value && parseNum(text) !== value) {
    lastSyncedRef.current = value
    setText(value ? fmtNum(value) : '')
  }
  return (
    <input
      type="text"
      inputMode="decimal"
      value={text}
      disabled={disabled}
      onChange={e => {
        setText(e.target.value)
        onValue(parseNum(e.target.value))
      }}
      onBlur={() => {
        const n = parseNum(text)
        setText(n ? fmtNum(n) : '')
      }}
      style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif', textAlign: 'right', ...style }}
    />
  )
}

function mesAtual() { return new Date().toISOString().slice(0, 7) }
function mesLabel(mes: string) {
  const [ano, mm] = mes.split('-')
  const nomes = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
  return `${nomes[Number(mm) - 1]}/${ano}`
}

// Categorias mapeadas à LC 214/2025 — agrupadas por elegibilidade típica
const CATEGORIAS_PADRAO = [
  // Insumos diretos da atividade (elegíveis em regra)
  'Software jurídico (SaaS)',
  'Correspondentes / parceiros forenses',
  'Honorários periciais',
  'Honorários de outros advogados',
  'Pesquisa jurisprudencial / bases de dados',
  'Cópias e autenticações',
  // Infraestrutura do escritório (elegíveis se uso 100% empresarial)
  'Aluguel comercial',
  'Condomínio comercial',
  'Energia elétrica',
  'Água e esgoto',
  'Internet',
  'Telefonia fixa / móvel',
  'Manutenção predial',
  'Limpeza e conservação',
  'Segurança / monitoramento',
  // TI e administrativo
  'Hardware (computadores, impressoras)',
  'Manutenção de TI',
  'Material de escritório',
  'Material de copa',
  // Profissionais terceirizados
  'Contabilidade',
  'Consultoria jurídica externa',
  'Marketing / publicidade',
  'Design / branding',
  'Treinamento e cursos',
  // Despesas mistas — IA pedirá detalhes
  'Combustível',
  'Viagens (passagens)',
  'Hospedagem',
  'Alimentação em viagem',
  'Refeições com clientes',
  'Uber / táxi',
  'Estacionamento',
  // Não elegíveis em regra (incluídas para classificar corretamente)
  'Despesas de clientes (reembolsáveis)',
  'Brindes / presentes',
  'Multas e juros',
  'IPTU / IPVA / tributos',
  'Doações',
  'Despesas pessoais',
  // Outros
  'Outros',
]

// ─── Combobox genérico com "+ Criar novo" ──────────────────────────────────────

function Combobox({
  value,
  onChange,
  options,
  placeholder,
  onCreate,
  renderOption,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string; hint?: string }[]
  placeholder?: string
  onCreate?: (v: string) => void
  renderOption?: (opt: { value: string; label: string; hint?: string }) => React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const display = open ? search : (value || '')
  const filtered = options.filter(o =>
    o.label.toLowerCase().includes((open ? search : '').toLowerCase())
  )
  const exactMatch = options.some(o => o.label.toLowerCase() === search.toLowerCase())

  // Atualiza posição do dropdown (fixed) ao abrir e em scroll/resize
  useEffect(() => {
    if (!open) return
    const update = () => {
      const el = inputRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      setRect({ top: r.bottom + 4, left: r.left, width: r.width })
    }
    update()
    window.addEventListener('scroll', update, true)
    window.addEventListener('resize', update)
    return () => {
      window.removeEventListener('scroll', update, true)
      window.removeEventListener('resize', update)
    }
  }, [open])

  return (
    <div style={{ position: 'relative' }}>
      <input
        ref={inputRef}
        value={display}
        onChange={e => { setSearch(e.target.value); setOpen(true); onChange(e.target.value) }}
        onFocus={() => { setSearch(value); setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 180)}
        placeholder={placeholder}
        style={{ width: '100%', padding: '8px 28px 8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif' }}
      />
      <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af', fontSize: 10, pointerEvents: 'none' }}>▼</span>
      {open && rect && createPortal(
        <div
          style={{
            position: 'fixed', top: rect.top, left: rect.left, width: rect.width, zIndex: 10000,
            background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
            boxShadow: '0 8px 24px rgba(0,0,0,.15)', maxHeight: 420, overflowY: 'auto',
            overscrollBehavior: 'contain',
          }}
          onWheel={e => {
            // Trava scroll do dropdown — se chegou no fim, não propaga pro body
            const el = e.currentTarget
            const dy = e.deltaY
            const atTop = el.scrollTop === 0
            const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= 1
            if ((dy < 0 && atTop) || (dy > 0 && atBottom)) e.preventDefault()
          }}
        >
          {filtered.length === 0 && !search && (
            <div style={{ padding: '8px 12px', fontSize: 12, color: 'var(--gray-mid)' }}>Nenhuma opção</div>
          )}
          {filtered.map(opt => (
            <div
              key={opt.value}
              onMouseDown={() => { onChange(opt.label); setOpen(false) }}
              style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13 }}
              onMouseEnter={e => (e.currentTarget.style.background = '#f0fdf4')}
              onMouseLeave={e => (e.currentTarget.style.background = '')}
            >
              {renderOption ? renderOption(opt) : (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{opt.label}</span>
                  {opt.hint && <span style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{opt.hint}</span>}
                </div>
              )}
            </div>
          ))}
          {onCreate && search && !exactMatch && (
            <div
              onMouseDown={() => { onCreate(search); onChange(search); setOpen(false) }}
              style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13, borderTop: '1px solid #f3f4f6', background: '#fefce8', color: '#a16207', fontWeight: 600 }}
              onMouseEnter={e => (e.currentTarget.style.background = '#fef3c7')}
              onMouseLeave={e => (e.currentTarget.style.background = '#fefce8')}
            >
              + Criar "{search}"
            </div>
          )}
        </div>,
        document.body
      )}
    </div>
  )
}

// ─── IA: classificação LC 214/2025 ────────────────────────────────────────────

function IaClassificacao({
  categoria,
  fornecedor,
  valor,
  onElegivelMudou,
}: {
  categoria: string
  fornecedor: string
  valor: number
  onElegivelMudou: (eleg: boolean) => void
}) {
  const [data, setData] = useState<{
    elegivel: boolean
    base_legal: string
    aliquota_ibs_pct: number
    aliquota_cbs_pct: number
    credito_estimado: number
    confianca: string
    observacao: string
    perguntas?: { id: string; pergunta: string; opcoes: string[] }[]
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [respostas, setRespostas] = useState<Record<string, string>>({})
  const lastKeyRef = useRef('')

  function classificar(respostasAtuais: Record<string, string>) {
    setLoading(true)
    backofficeApi.classificarDespesa({ categoria, fornecedor, valor, respostas: respostasAtuais })
      .then(r => { setData(r); onElegivelMudou(r.elegivel) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  // Só dispara IA quando há categoria + valor > 0. Re-dispara se categoria/fornecedor mudam.
  // Não re-dispara só por mudar valor — apenas recalcula crédito localmente.
  useEffect(() => {
    if (!categoria || valor <= 0) return
    const key = `${categoria}|${fornecedor}`
    if (key === lastKeyRef.current) return
    lastKeyRef.current = key
    setRespostas({})
    classificar({})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoria, fornecedor, valor])

  // Limpa o card quando categoria some ou valor zera
  useEffect(() => {
    if (!categoria || valor <= 0) {
      setData(null)
      setRespostas({})
      lastKeyRef.current = ''
    }
  }, [categoria, valor])

  if (!categoria) return null
  if (valor <= 0) {
    return (
      <div style={{ padding: '10px 14px', background: '#f9fafb', border: '1px dashed #e5e7eb', borderRadius: 8, fontSize: 12, color: 'var(--gray-mid)' }}>
        💡 Informe o valor para a IA analisar a elegibilidade pela LC 214/2025.
      </div>
    )
  }
  if (loading && !data) {
    return (
      <div style={{ padding: '10px 14px', background: '#f9fafb', border: '1px dashed #e5e7eb', borderRadius: 8, fontSize: 12, color: 'var(--gray-mid)' }}>
        🤖 Analisando elegibilidade pela LC 214/2025…
      </div>
    )
  }
  if (!data) return null

  // Se a IA pediu clarificações pendentes, renderiza perguntas
  const pendentes = (data.perguntas ?? []).filter(p => !respostas[p.id])
  if (pendentes.length > 0) {
    return (
      <div style={{ padding: '12px 14px', background: '#fef3c7', border: '1px solid #fde68a', borderRadius: 8, fontSize: 12 }}>
        <div style={{ color: '#92400e', fontWeight: 700, marginBottom: 8 }}>
          🤖 Preciso de mais detalhes para classificar essa despesa pela LC 214/2025:
        </div>
        {pendentes.map(p => (
          <div key={p.id} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 12, color: 'var(--dark)', marginBottom: 4 }}>{p.pergunta}</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {p.opcoes.map(op => (
                <button
                  key={op}
                  onClick={() => {
                    const novas = { ...respostas, [p.id]: op }
                    setRespostas(novas)
                    if (pendentes.length === 1) classificar(novas)
                  }}
                  style={{ padding: '4px 10px', borderRadius: 999, border: '1px solid #fde68a', background: '#fff', fontSize: 11, fontWeight: 600, cursor: 'pointer', color: '#92400e', fontFamily: 'Archivo, sans-serif' }}
                >
                  {op}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  // Crédito recalculado em tempo real conforme o valor — IA não roda de novo, só multiplica
  const aliqTotal = (data.aliquota_ibs_pct + data.aliquota_cbs_pct) / 100
  const credito = data.elegivel ? valor * aliqTotal : 0
  const corBg = data.elegivel ? '#f0fdf4' : '#fef2f2'
  const corBd = data.elegivel ? '#bbf7d0' : '#fecaca'
  const corTx = data.elegivel ? '#15803d' : '#b91c1c'

  return (
    <div style={{ padding: '10px 14px', background: corBg, border: `1px solid ${corBd}`, borderRadius: 8, fontSize: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <span style={{ color: corTx, fontWeight: 700 }}>
          🤖 {data.elegivel ? '✓ Elegível' : '✗ Não elegível'} para crédito IBS/CBS
          <span style={{ fontSize: 10, marginLeft: 6, color: 'var(--gray-mid)', fontWeight: 400 }}>(confiança: {data.confianca})</span>
        </span>
        {data.elegivel && (
          <span style={{ color: 'var(--teal)', fontWeight: 700 }}>
            Crédito estimado: {fmtBRL(credito)}
            <span style={{ fontSize: 10, color: 'var(--gray-mid)', fontWeight: 400, marginLeft: 4 }}>
              (IBS {data.aliquota_ibs_pct}% + CBS {data.aliquota_cbs_pct}%)
            </span>
          </span>
        )}
      </div>
      {data.observacao && (
        <div style={{ marginTop: 4, color: 'var(--gray-mid)', fontSize: 11 }}>
          {data.observacao} · <span style={{ fontStyle: 'italic' }}>{data.base_legal}</span>
        </div>
      )}
    </div>
  )
}

// ─── Formulário de nova despesa ────────────────────────────────────────────────

function FormNovaDespesa({
  mes,
  fornecedores,
  categorias,
  onSaved,
}: {
  mes: string
  fornecedores: Fornecedor[]
  categorias: string[]
  onSaved: () => void
}) {
  const qc = useQueryClient()
  const [fornecedor, setFornecedor] = useState('')
  const [cnpj, setCnpj] = useState('')
  const [categoria, setCategoria] = useState('')
  const [valor, setValor] = useState(0)
  const [dataDespesa, setDataDespesa] = useState(() => {
    // Default: hoje, mas se o mês selecionado não for o atual, primeiro dia do mês
    const hoje = new Date().toISOString().slice(0, 10)
    if (hoje.startsWith(mes)) return hoje
    return `${mes}-01`
  })
  const [temNota, setTemNota] = useState(true)
  const [elegivel, setElegivel] = useState(false)
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)

  const save = useMutation({
    mutationFn: async () => {
      let drive_link: string | undefined
      if (arquivo) {
        setUploading(true)
        try {
          const mesUpload = dataDespesa ? dataDespesa.slice(0, 7) : mes
          const nomeArq = [dataDespesa, fornecedor, categoria].filter(Boolean).join('_')
          const r = await backofficeApi.uploadComprovante(mesUpload, arquivo, nomeArq)
          drive_link = r.link
        } finally { setUploading(false) }
      }
      return backofficeApi.addDespesa(mes, { categoria, fornecedor, valor, data: dataDespesa, tem_nota: temNota, elegivel, drive_link })
    },
    onSuccess: async () => {
      // Salva fornecedor (com CNPJ) se preenchido
      if (fornecedor.trim()) {
        await backofficeApi.upsertFornecedor({
          nome: fornecedor.trim(),
          cnpj: cnpj.replace(/\D/g, '') || undefined,
          categoria_padrao: categoria || undefined,
        })
      }
      qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] })
      qc.invalidateQueries({ queryKey: ['backoffice-despesas', mes] })
      qc.invalidateQueries({ queryKey: ['backoffice-fornecedores'] })
      setFornecedor(''); setCnpj(''); setCategoria(''); setValor(0); setArquivo(null)
      const hoje = new Date().toISOString().slice(0, 10)
      setDataDespesa(hoje.startsWith(mes) ? hoje : `${mes}-01`)
      onSaved()
    },
  })

  const allCats = Array.from(new Set([...CATEGORIAS_PADRAO, ...categorias]))

  return (
    <div style={{ padding: '0 18px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
      <div className={styles.fieldGroup}>
        <span>Fornecedor</span>
        <Combobox
          value={fornecedor}
          onChange={nome => {
            setFornecedor(nome)
            const f = fornecedores.find(x => x.nome === nome)
            if (f) {
              setCnpj(f.cnpj ? fmtCNPJ(f.cnpj) : '')
              if (f.categoria_padrao && !categoria) setCategoria(f.categoria_padrao)
            }
          }}
          options={fornecedores.map(f => ({ value: f.id, label: f.nome, hint: f.categoria_padrao ?? undefined }))}
          placeholder="Selecione ou digite um novo"
          onCreate={setFornecedor}
        />
      </div>
      <div className={styles.fieldGroup}>
        <span>CNPJ (opcional)</span>
        <input
          value={cnpj}
          onChange={e => setCnpj(fmtCNPJ(e.target.value))}
          placeholder="00.000.000/0000-00"
          style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif' }}
        />
      </div>
      <div className={styles.fieldGroup}>
        <span>Categoria</span>
        <Combobox
          value={categoria}
          onChange={setCategoria}
          options={allCats.map(c => ({ value: c, label: c }))}
          placeholder="Selecione ou digite uma nova"
          onCreate={c => setCategoria(c)}
        />
      </div>
      <div className={styles.fieldGroup}>
        <span>Valor (R$)</span>
        <MoneyInput value={valor} onValue={setValor} />
      </div>
      <div className={styles.fieldGroup}>
        <span>
          Data da despesa
          {!dataDespesa.startsWith(mes) && (
            <span style={{ color: '#b45309', marginLeft: 6, fontSize: 10, fontWeight: 700 }}>
              ⚠ vai para {dataDespesa.slice(0, 7)}
            </span>
          )}
        </span>
        <input
          type="date"
          value={dataDespesa}
          onChange={e => setDataDespesa(e.target.value)}
          style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif' }}
        />
      </div>

      {/* IA: classificação de crédito IBS/CBS */}
      <div style={{ gridColumn: '1/-1' }}>
        <IaClassificacao
          categoria={categoria}
          fornecedor={fornecedor}
          valor={valor}
          onElegivelMudou={setElegivel}
        />
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'center', paddingTop: 6, gridColumn: '1/-1', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
          <input type="checkbox" checked={temNota} onChange={e => setTemNota(e.target.checked)} />
          Tem nota fiscal
        </label>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
          <input type="checkbox" checked={elegivel} onChange={e => setElegivel(e.target.checked)} />
          Elegível IBS/CBS
        </label>
      </div>

      {/* Upload de comprovante (opcional) → /Backoffice/Despesas/{mes}/ no Drive */}
      <div style={{ gridColumn: '1/-1', padding: '10px 14px', border: '1px dashed #e5e7eb', borderRadius: 8, background: '#fafafa' }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--gray-mid)', textTransform: 'uppercase', letterSpacing: '.04em', display: 'block', marginBottom: 6 }}>
          📎 Comprovante (opcional · PDF ou imagem)
        </label>
        <input
          type="file"
          accept=".pdf,image/*"
          onChange={e => setArquivo(e.target.files?.[0] ?? null)}
          style={{ fontSize: 12 }}
        />
        {arquivo && (
          <div style={{ fontSize: 11, color: 'var(--teal)', marginTop: 6 }}>
            ✓ {arquivo.name} ({Math.round(arquivo.size / 1024)} KB) — será salvo em /Backoffice/Despesas/{(dataDespesa || mes).slice(0, 7)}
          </div>
        )}
      </div>

      <div style={{ gridColumn: '1/-1' }}>
        <button
          className={styles.btnPrimary}
          disabled={!fornecedor || valor <= 0 || save.isPending}
          onClick={() => save.mutate()}
        >
          {uploading ? 'Enviando arquivo…' : save.isPending ? 'Salvando…' : 'Adicionar despesa'}
        </button>
      </div>
    </div>
  )
}

// ─── Vínculo de pagamento a reembolso(s) — N:N informativo ─────────────────────

function VincularReembolso({
  value,
  onChange,
}: {
  value: string[]
  onChange: (ids: string[]) => void
}) {
  const qc = useQueryClient()
  const { data: reembolsos = [] } = useQuery({
    queryKey: ['reembolsos'],
    queryFn: () => reembolsosApi.listar(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })
  const cliNome = (id: string) => clientes.find(c => c.id === id)?.nome ?? '—'
  const reembMap = Object.fromEntries(reembolsos.map(r => [r.id, r]))

  const [criando, setCriando] = useState(false)
  const [novoCliente, setNovoCliente] = useState('')   // nome digitado/selecionado
  const [novoClienteId, setNovoClienteId] = useState('')
  const [novoTitulo, setNovoTitulo] = useState('')

  const criar = useMutation({
    mutationFn: () => reembolsosApi.criar({
      cliente_id: novoClienteId,
      titulo: novoTitulo.trim(),
      data_emissao: new Date().toISOString().slice(0, 10),
    }),
    onSuccess: (novo) => {
      qc.invalidateQueries({ queryKey: ['reembolsos'] })
      onChange([...value, novo.id])
      setCriando(false); setNovoCliente(''); setNovoClienteId(''); setNovoTitulo('')
    },
    onError: (e: any) => alert(`Erro ao criar reembolso: ${e?.response?.data?.detail || e?.message}`),
  })

  // Reembolsos disponíveis (inclui pagos — adiantamento pode ter sido quitado) que ainda
  // não estão vinculados a esta linha. Exclui só os cancelados.
  const disponiveis = reembolsos
    .filter(r => r.status !== 'cancelado' && !value.includes(r.id))
    .map(r => ({ value: r.id, label: labelPasta(r, cliNome(r.cliente_id)) }))

  return (
    <div style={{ gridColumn: '1 / -1', padding: '8px 10px 4px 34px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: 11, color: '#92400e', fontWeight: 600 }}>
        🔗 Vincular a reembolso(s) — a quais clientes esse adiantamento se refere?
      </div>

      {/* Chips dos vinculados */}
      {value.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {value.map(id => {
            const r = reembMap[id]
            return (
              <span key={id} style={{ fontSize: 11, background: '#e0e7ff', color: '#3730a3', padding: '2px 8px', borderRadius: 999, fontWeight: 600, display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                {r ? `${cliNome(r.cliente_id)} — ${r.titulo}` : id.slice(0, 8)}
                <span style={{ cursor: 'pointer' }} onClick={() => onChange(value.filter(x => x !== id))}>×</span>
              </span>
            )
          })}
        </div>
      )}

      {/* Adicionar existente — Combobox devolve o label; mapeamos de volta ao id */}
      <div style={{ maxWidth: 360 }}>
        <Combobox
          value=""
          onChange={(label) => {
            const opt = disponiveis.find(o => o.label === label)
            if (opt && !value.includes(opt.value)) onChange([...value, opt.value])
          }}
          options={disponiveis}
          placeholder="+ vincular reembolso existente…"
        />
      </div>

      {/* Criar novo inline */}
      {!criando ? (
        <button type="button" className={styles.btnSmall} style={{ alignSelf: 'flex-start' }} onClick={() => setCriando(true)}>
          + Novo reembolso
        </button>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto auto', gap: 6, alignItems: 'center', maxWidth: 540 }}>
          <Combobox
            value={novoCliente}
            onChange={(nome) => {
              setNovoCliente(nome)
              const c = clientes.find(x => x.nome === nome)
              setNovoClienteId(c?.id ?? '')
            }}
            options={clientes.map(c => ({ value: c.id, label: c.nome }))}
            placeholder="Cliente"
          />
          <input
            value={novoTitulo}
            onChange={e => setNovoTitulo(e.target.value)}
            placeholder="Título (ex.: Certidões ONR)"
            style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, fontFamily: 'Archivo, sans-serif' }}
          />
          <button type="button" className={styles.btnPrimary} style={{ padding: '5px 12px', fontSize: 12 }}
            disabled={!novoClienteId || !novoTitulo.trim() || criar.isPending}
            onClick={() => criar.mutate()}>
            {criar.isPending ? '…' : 'Criar'}
          </button>
          <button type="button" className={styles.btnSmall} style={{ fontSize: 12 }} onClick={() => setCriando(false)}>Cancelar</button>
        </div>
      )}
    </div>
  )
}

// ─── Upload de extrato bancário ────────────────────────────────────────────────

function SecaoExtrato({
  mes,
  fornecedores: _fornecedores,
  categorias,
  onSaved,
}: {
  mes: string
  fornecedores: Fornecedor[]
  categorias: string[]
  onSaved: () => void
}) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [linhas, setLinhas] = useState<(ParsedExpense & { selecionado: boolean; elegivel: boolean; reembolso_ids?: string[] })[]>([])
  const [entradas, setEntradas] = useState<(ParsedEntrada & { selecionado: boolean })[]>([])
  const [parsing, setParsing] = useState(false)
  const [parseErr, setParseErr] = useState<string | null>(null)
  const [progresso, setProgresso] = useState(0)
  const [salvoInfo, setSalvoInfo] = useState<string | null>(null)
  const allCats = Array.from(new Set([...CATEGORIAS_PADRAO, ...categorias]))

  async function handleFile(file: File) {
    setParsing(true); setParseErr(null); setLinhas([]); setEntradas([]); setSalvoInfo(null)
    // Progresso "fake" crescente (não há stream do fetch) — vai até 90% e completa no fim
    setProgresso(8)
    const timer = setInterval(() => {
      setProgresso(p => (p < 90 ? p + Math.max(1, Math.round((92 - p) / 12)) : p))
    }, 400)
    try {
      const res = await backofficeApi.parseExtrato(file)
      const saidas = res.saidas ?? res.linhas ?? []
      // Entradas: "receita" já vem marcada (candidata a NF); reembolso/outro desmarcadas
      setEntradas((res.entradas ?? []).map(e => ({ ...e, selecionado: e.tipo_sugerido === 'receita' })))
      if (saidas.length === 0 && (res.entradas ?? []).length === 0) {
        setParseErr('Nenhuma transação encontrada no extrato. Confira se o arquivo é legível.')
        return
      }
      setLinhas(saidas.map(l => ({ ...l, selecionado: true, elegivel: false })))
      if (res.drive_link) {
        setSalvoInfo(`💾 ${res.banco ?? 'Extrato'} salvo no Drive (${(res.meses ?? []).join(', ') || 'mês atual'}).`)
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      const status = e?.response?.status
      const detailStr = typeof detail === 'string'
        ? detail
        : detail ? JSON.stringify(detail) : null
      setParseErr(
        detailStr
          ? `Erro ${status ?? ''}: ${detailStr}`
          : `Falha ao processar (${e?.message ?? 'erro desconhecido'}). Verifique se o PDF é legível.`
      )
    } finally {
      clearInterval(timer)
      setProgresso(100)
      setTimeout(() => setProgresso(0), 600)
      setParsing(false)
    }
  }

  const confirmar = useMutation({
    mutationFn: async () => {
      const selecionadas = linhas.filter(l => l.selecionado)
      if (selecionadas.length > 0) {
        await backofficeApi.addDespesasBatch(mes, selecionadas.map(l => ({
          categoria: l.categoria,
          fornecedor: l.fornecedor,
          descricao: l.descricao,
          valor: l.valor,
          data: l.data,  // cada despesa vai para o mês da sua própria data
          tem_nota: false,
          elegivel: l.elegivel,
          reembolso_ids: l.reembolso_ids && l.reembolso_ids.length ? l.reembolso_ids : undefined,
        })))
      }
      // Entradas selecionadas → fila de sugestões de NF
      const entSel = entradas.filter(e => e.selecionado)
      if (entSel.length > 0) {
        await backofficeApi.criarSugestoesNf(entSel.map(e => ({
          data: e.data,
          pagador: e.pagador,
          valor: e.valor,
          descricao: e.descricao,
          tipo_sugerido: e.tipo_sugerido,
        })))
      }
    },
    onSuccess: async () => {
      // Salva fornecedores novos
      const novos = linhas.filter(l => l.selecionado && l.fornecedor)
      for (const l of novos) {
        await backofficeApi.upsertFornecedor({ nome: l.fornecedor, categoria_padrao: l.categoria || undefined })
      }
      qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] })
      qc.invalidateQueries({ queryKey: ['backoffice-despesas', mes] })
      qc.invalidateQueries({ queryKey: ['sugestoes-nf'] })
      setLinhas([]); setEntradas([])
      onSaved()
    },
  })

  return (
    <div>
      <div
        style={{
          border: '2px dashed #e5e7eb', borderRadius: 8, padding: '24px',
          textAlign: 'center', cursor: 'pointer', transition: 'border-color .15s',
        }}
        onClick={() => fileRef.current?.click()}
        onDragOver={e => { e.preventDefault(); e.currentTarget.style.borderColor = 'var(--teal)' }}
        onDragLeave={e => { e.currentTarget.style.borderColor = '#e5e7eb' }}
        onDrop={e => {
          e.preventDefault()
          e.currentTarget.style.borderColor = '#e5e7eb'
          const f = e.dataTransfer.files[0]
          if (f) handleFile(f)
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept="image/*,.pdf"
          style={{ display: 'none' }}
          onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
        />
        {parsing ? (
          <div style={{ width: '100%', maxWidth: 360, margin: '0 auto' }}>
            <div style={{ color: 'var(--teal)', fontSize: 13, marginBottom: 8 }}>
              ⏳ Lendo o extrato com IA… {progresso}%
            </div>
            <div style={{ height: 8, background: '#e5e7eb', borderRadius: 999, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${progresso}%`, background: 'var(--teal)', borderRadius: 999, transition: 'width .4s ease' }} />
            </div>
            <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 6 }}>
              Extraindo saídas, entradas e identificando o banco…
            </div>
          </div>
        ) : (
          <>
            <div style={{ fontSize: 22, marginBottom: 6 }}>📄</div>
            <div style={{ fontSize: 13, color: 'var(--gray-mid)' }}>
              Arraste ou clique para enviar extrato bancário (imagem ou PDF)
            </div>
            <div style={{ fontSize: 11, color: '#c0c5c5', marginTop: 4 }}>
              A IA extrai saídas e entradas, salva o arquivo no Drive e identifica o banco
            </div>
          </>
        )}
      </div>

      {salvoInfo && (
        <div style={{ marginTop: 8, padding: '6px 12px', background: '#f0fdf4', borderRadius: 6, fontSize: 12, color: '#15803d' }}>
          {salvoInfo}
        </div>
      )}

      {parseErr && (
        <div style={{ marginTop: 8, padding: '8px 12px', background: '#fee2e2', borderRadius: 6, fontSize: 12, color: '#b91c1c' }}>
          {parseErr}
        </div>
      )}

      {linhas.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--dark)' }}>
              {linhas.length} saída(s) detectada(s) — revise e confirme:
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {(() => {
                const todosEleg = linhas.every(l => l.elegivel)
                return (
                  <button
                    type="button"
                    className={styles.btnSmall}
                    style={{ fontSize: 11, padding: '4px 10px' }}
                    onClick={() => setLinhas(prev => prev.map(x => ({ ...x, elegivel: !todosEleg })))}
                  >
                    {todosEleg ? 'Desmarcar elegível de todas' : '✓ Marcar elegível em todas'}
                  </button>
                )
              })()}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {linhas.map((l, i) => {
              const reembolsavel = ehReembolsavel(l.categoria)
              return (
              <div
                key={i}
                style={{
                  display: 'grid', gridTemplateColumns: '24px 1fr 1fr 100px 80px 80px',
                  gap: 8, alignItems: 'center', padding: '8px 12px',
                  background: l.selecionado ? (reembolsavel ? '#fffbeb' : '#f0fdf4') : '#f9fafb',
                  borderRadius: 6, border: `1px solid ${reembolsavel && l.selecionado ? '#fde68a' : '#e5e7eb'}`,
                }}
              >
                <input
                  type="checkbox"
                  checked={l.selecionado}
                  onChange={e => setLinhas(prev => prev.map((x, j) => j === i ? { ...x, selecionado: e.target.checked } : x))}
                />
                <input
                  value={l.fornecedor}
                  onChange={e => setLinhas(prev => prev.map((x, j) => j === i ? { ...x, fornecedor: e.target.value } : x))}
                  style={{ fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4, padding: '4px 8px', fontFamily: 'Archivo, sans-serif' }}
                />
                <Combobox
                  value={l.categoria}
                  onChange={c => setLinhas(prev => prev.map((x, j) => j === i ? {
                    ...x, categoria: c,
                    // reembolsável é pass-through → não elegível por padrão
                    elegivel: ehReembolsavel(c) ? false : x.elegivel,
                  } : x))}
                  options={allCats.map(c => ({ value: c, label: c }))}
                  placeholder="Categoria"
                  onCreate={c => setLinhas(prev => prev.map((x, j) => j === i ? { ...x, categoria: c } : x))}
                />
                <MoneyInput
                  value={l.valor}
                  onValue={n => setLinhas(prev => prev.map((x, j) => j === i ? { ...x, valor: n } : x))}
                  style={{ fontSize: 12, padding: '4px 8px' }}
                />
                <span style={{ fontSize: 11, color: 'var(--gray-mid)', whiteSpace: 'nowrap' }}>{l.data}</span>
                <label style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                  <input
                    type="checkbox"
                    checked={l.elegivel}
                    onChange={e => setLinhas(prev => prev.map((x, j) => j === i ? { ...x, elegivel: e.target.checked } : x))}
                  />
                  Elegível
                </label>
                {reembolsavel && l.selecionado && (
                  <VincularReembolso
                    value={l.reembolso_ids ?? []}
                    onChange={(ids) => setLinhas(prev => prev.map((x, j) => j === i ? { ...x, reembolso_ids: ids } : x))}
                  />
                )}
              </div>
            )})}
          </div>
        </div>
      )}

      {/* Entradas → sugestões de NF */}
      {entradas.length > 0 && (
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4, color: 'var(--dark)' }}>
            {entradas.length} entrada(s) detectada(s) — marque as que viram <span style={{ color: 'var(--teal)' }}>sugestão de NF</span>:
          </div>
          <div style={{ fontSize: 11, color: 'var(--gray-mid)', marginBottom: 8 }}>
            Recebimentos de cliente por serviço viram fila de emissão (Notas Fiscais). Devolução de reembolso já vem desmarcada.
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {entradas.map((e, i) => {
              const tipoLabel = e.tipo_sugerido === 'receita' ? { txt: 'Receita → NF', bg: '#dcfce7', fg: '#15803d' }
                : e.tipo_sugerido === 'reembolso_recebido' ? { txt: 'Reembolso recebido', bg: '#e0e7ff', fg: '#3730a3' }
                : { txt: 'Outro', bg: '#f3f4f6', fg: '#6b7280' }
              return (
                <div
                  key={i}
                  style={{
                    display: 'grid', gridTemplateColumns: '24px 1fr 130px 100px 90px', gap: 8, alignItems: 'center',
                    padding: '8px 12px', background: e.selecionado ? '#eff6ff' : '#f9fafb',
                    borderRadius: 6, border: '1px solid #e5e7eb',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={e.selecionado}
                    onChange={ev => setEntradas(prev => prev.map((x, j) => j === i ? { ...x, selecionado: ev.target.checked } : x))}
                  />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.pagador}</div>
                    {e.descricao && <div style={{ fontSize: 10, color: 'var(--gray-mid)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.descricao}</div>}
                  </div>
                  <span style={{ fontSize: 9, background: tipoLabel.bg, color: tipoLabel.fg, padding: '2px 6px', borderRadius: 999, fontWeight: 700, textAlign: 'center', whiteSpace: 'nowrap' }}>
                    {tipoLabel.txt}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, textAlign: 'right' }}>{fmtBRL(e.valor)}</span>
                  <span style={{ fontSize: 11, color: 'var(--gray-mid)', whiteSpace: 'nowrap', textAlign: 'right' }}>{e.data}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {(linhas.length > 0 || entradas.length > 0) && (
        <div style={{ marginTop: 14, display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            className={styles.btnPrimary}
            disabled={confirmar.isPending || (!linhas.some(l => l.selecionado) && !entradas.some(e => e.selecionado))}
            onClick={() => confirmar.mutate()}
          >
            {confirmar.isPending ? 'Salvando…' : (() => {
              const nd = linhas.filter(l => l.selecionado).length
              const ne = entradas.filter(e => e.selecionado).length
              const partes = []
              if (nd) partes.push(`${nd} despesa(s)`)
              if (ne) partes.push(`${ne} sugestão(ões) de NF`)
              return `Lançar ${partes.join(' + ')}`
            })()}
          </button>
          <button className={styles.btnSmall} onClick={() => { setLinhas([]); setEntradas([]) }}>Cancelar</button>
        </div>
      )}
    </div>
  )
}

// ─── Despesas recorrentes ──────────────────────────────────────────────────────

function SecaoRecorrentes({
  mes,
  fornecedores,
  categorias,
  onSaved,
}: {
  mes: string
  fornecedores: Fornecedor[]
  categorias: string[]
  onSaved: () => void
}) {
  const qc = useQueryClient()
  const { data: recorrentes = [] } = useQuery({
    queryKey: ['backoffice-recorrentes'],
    queryFn: backofficeApi.recorrentes,
  })

  const [selecionados, setSelecionados] = useState<Record<string, { valor: number; elegivel: boolean }>>({})
  const [showForm, setShowForm] = useState(false)
  const [novaCategoria, setNovaCategoria] = useState('')
  const [novaFornecedor, setNovaFornecedor] = useState('')
  const [novoValor, setNovoValor] = useState(0)
  const [novaElegivel, setNovaElegivel] = useState(false)
  const allCats = Array.from(new Set([...CATEGORIAS_PADRAO, ...categorias]))

  const lancar = useMutation({
    mutationFn: () => {
      const items = recorrentes
        .filter(r => selecionados[r.id])
        .map(r => ({
          categoria: r.categoria,
          fornecedor: r.fornecedor,
          descricao: r.descricao,
          valor: selecionados[r.id].valor,
          tem_nota: r.tem_nota,
          elegivel: selecionados[r.id].elegivel,
        }))
      return backofficeApi.addDespesasBatch(mes, items)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] })
      qc.invalidateQueries({ queryKey: ['backoffice-despesas', mes] })
      setSelecionados({})
      onSaved()
    },
  })

  const addRecorrente = useMutation({
    mutationFn: () => backofficeApi.createRecorrente({
      categoria: novaCategoria, fornecedor: novaFornecedor,
      valor_padrao: novoValor, elegivel: novaElegivel,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['backoffice-recorrentes'] })
      setShowForm(false); setNovaCategoria(''); setNovaFornecedor(''); setNovoValor(0); setNovaElegivel(false)
    },
  })

  const removeRecorrente = useMutation({
    mutationFn: (id: string) => backofficeApi.deleteRecorrente(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backoffice-recorrentes'] }),
  })

  function toggle(r: DespesaRecorrente) {
    setSelecionados(prev => {
      if (prev[r.id]) {
        const next = { ...prev }
        delete next[r.id]
        return next
      }
      return { ...prev, [r.id]: { valor: r.valor_padrao, elegivel: r.elegivel } }
    })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {recorrentes.length === 0 && !showForm && (
        <div style={{ fontSize: 12, color: 'var(--gray-mid)', textAlign: 'center', padding: '16px 0' }}>
          Nenhuma despesa recorrente cadastrada. Adicione para facilitar o lançamento mensal.
        </div>
      )}

      {recorrentes.map(r => {
        const sel = selecionados[r.id]
        return (
          <div
            key={r.id}
            style={{
              display: 'grid', gridTemplateColumns: '24px 1fr 1fr 120px 80px 28px',
              gap: 8, alignItems: 'center', padding: '8px 12px',
              background: sel ? '#f0fdf4' : '#fafafa',
              borderRadius: 6, border: `1px solid ${sel ? '#bbf7d0' : '#e5e7eb'}`,
            }}
          >
            <input type="checkbox" checked={!!sel} onChange={() => toggle(r)} />
            <span style={{ fontSize: 13 }}>{r.fornecedor}</span>
            <span style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{r.categoria}</span>
            <MoneyInput
              value={sel ? sel.valor : r.valor_padrao}
              disabled={!sel}
              onValue={n => setSelecionados(prev => ({ ...prev, [r.id]: { ...prev[r.id], valor: n } }))}
              style={{ fontSize: 12, padding: '4px 8px', background: sel ? '#fff' : '#f5f5f5' }}
            />
            <label style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: 11, cursor: sel ? 'pointer' : 'default' }}>
              <input
                type="checkbox"
                checked={sel ? sel.elegivel : r.elegivel}
                disabled={!sel}
                onChange={e => setSelecionados(prev => ({ ...prev, [r.id]: { ...prev[r.id], elegivel: e.target.checked } }))}
              />
              Elegível
            </label>
            <button
              style={{ background: 'none', border: 'none', color: '#d1d5db', cursor: 'pointer', fontSize: 14 }}
              onClick={() => removeRecorrente.mutate(r.id)}
              title="Remover recorrente"
            >×</button>
          </div>
        )
      })}

      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        {Object.keys(selecionados).length > 0 && (
          <button
            className={styles.btnPrimary}
            disabled={lancar.isPending}
            onClick={() => lancar.mutate()}
          >
            {lancar.isPending ? 'Lançando…' : `Lançar ${Object.keys(selecionados).length} recorrente(s) em ${mesLabel(mes)}`}
          </button>
        )}
        <button className={styles.btnSmall} onClick={() => setShowForm(v => !v)}>
          {showForm ? 'Cancelar' : '+ Nova recorrente'}
        </button>
      </div>

      {showForm && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '10px 0' }}>
          <div className={styles.fieldGroup}>
            <span>Fornecedor</span>
            <Combobox
              value={novaFornecedor}
              onChange={nome => {
                setNovaFornecedor(nome)
                const f = fornecedores.find(x => x.nome === nome)
                if (f?.categoria_padrao && !novaCategoria) setNovaCategoria(f.categoria_padrao)
              }}
              options={fornecedores.map(f => ({ value: f.id, label: f.nome, hint: f.categoria_padrao ?? undefined }))}
              placeholder="Selecione ou digite um novo"
              onCreate={setNovaFornecedor}
            />
          </div>
          <div className={styles.fieldGroup}>
            <span>Categoria</span>
            <Combobox
              value={novaCategoria}
              onChange={setNovaCategoria}
              options={allCats.map(c => ({ value: c, label: c }))}
              placeholder="Selecione ou digite uma nova"
              onCreate={setNovaCategoria}
            />
          </div>
          <div className={styles.fieldGroup}>
            <span>Valor padrão (R$)</span>
            <MoneyInput value={novoValor} onValue={setNovoValor} />
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', paddingTop: 18 }}>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={novaElegivel} onChange={e => setNovaElegivel(e.target.checked)} />
              Elegível IBS/CBS
            </label>
          </div>
          <div style={{ gridColumn: '1/-1' }}>
            <button
              className={styles.btnPrimary}
              disabled={!novaFornecedor || addRecorrente.isPending}
              onClick={() => addRecorrente.mutate()}
            >
              {addRecorrente.isPending ? 'Salvando…' : 'Adicionar recorrente'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Tabela de despesas do mês ────────────────────────────────────────────────

function fmtData(iso?: string | null) {
  if (!iso) return '—'
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y.slice(2)}`
}

function LinhaDespesa({
  d, depth = 0, fornecedores, allCats,
  editId, editForm, setEditForm, setEditId,
  iniciarEdit, salvarEdit, patchElegivel, deleteDespesa,
}: {
  d: Despesa; depth?: number
  fornecedores: Fornecedor[]; allCats: string[]
  editId: string | null
  editForm: any; setEditForm: any; setEditId: (id: string | null) => void
  iniciarEdit: (d: Despesa) => void
  salvarEdit: { mutate: (id: string) => void; isPending: boolean }
  patchElegivel: { mutate: (a: { id: string; elegivel: boolean }) => void }
  deleteDespesa: { mutate: (id: string) => void }
}) {
  const indent = depth * 18
  const [uploadEdit, setUploadEdit] = useState(false)
  if (editId === d.id) {
    return (
      <tr key={d.id} style={{ background: '#f0fdf4' }}>
        <td colSpan={9} style={{ padding: '12px 14px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '110px 2fr 2fr 1fr auto auto auto', gap: 8, alignItems: 'center' }}>
            <input
              type="date"
              value={editForm.data ?? ''}
              onChange={e => setEditForm((f: any) => ({ ...f, data: e.target.value }))}
              style={{ padding: '6px 8px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, fontFamily: 'Archivo, sans-serif' }}
            />
            <Combobox
              value={editForm.fornecedor}
              onChange={v => setEditForm((f: any) => ({ ...f, fornecedor: v }))}
              options={fornecedores.map(f => ({ value: f.id, label: f.nome, hint: f.categoria_padrao ?? undefined }))}
              placeholder="Fornecedor"
              onCreate={v => setEditForm((f: any) => ({ ...f, fornecedor: v }))}
            />
            <Combobox
              value={editForm.categoria}
              onChange={v => setEditForm((f: any) => ({ ...f, categoria: v }))}
              options={allCats.map(c => ({ value: c, label: c }))}
              placeholder="Categoria"
              onCreate={v => setEditForm((f: any) => ({ ...f, categoria: v }))}
            />
            <MoneyInput value={editForm.valor} onValue={v => setEditForm((f: any) => ({ ...f, valor: v }))} />
            <label style={{ display: 'flex', gap: 4, fontSize: 11, alignItems: 'center' }}>
              <input type="checkbox" checked={editForm.tem_nota} onChange={e => setEditForm((f: any) => ({ ...f, tem_nota: e.target.checked }))} /> NF
            </label>
            <label style={{ display: 'flex', gap: 4, fontSize: 11, alignItems: 'center' }}>
              <input type="checkbox" checked={editForm.elegivel} onChange={e => setEditForm((f: any) => ({ ...f, elegivel: e.target.checked }))} /> Eleg.
            </label>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className={styles.btnPrimary} onClick={() => salvarEdit.mutate(d.id)} disabled={salvarEdit.isPending || uploadEdit}>
                {salvarEdit.isPending ? '…' : 'Salvar'}
              </button>
              <button className={styles.btnSmall} onClick={() => setEditId(null)}>Cancelar</button>
            </div>
          </div>
          {/* Upload da NF / comprovante na edição */}
          {editForm.tem_nota && (
            <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center', fontSize: 11 }}>
              <span style={{ color: 'var(--gray-mid)' }}>📎 NF / comprovante:</span>
              <input
                type="file"
                accept=".pdf,image/*"
                disabled={uploadEdit}
                onChange={async (e) => {
                  const f = e.target.files?.[0]
                  if (!f) return
                  setUploadEdit(true)
                  try {
                    const mesUp = (editForm.data || d.data || '').slice(0, 7) || new Date().toISOString().slice(0, 7)
                    const nomeArq = [editForm.data, editForm.fornecedor, editForm.categoria].filter(Boolean).join('_')
                    const r = await backofficeApi.uploadComprovante(mesUp, f, nomeArq)
                    setEditForm((ff: any) => ({ ...ff, drive_link: r.link }))
                  } catch (err: any) {
                    alert(`Falha no upload: ${err?.message || err}`)
                  } finally { setUploadEdit(false) }
                }}
                style={{ fontSize: 11 }}
              />
              {uploadEdit && <span style={{ color: 'var(--teal)' }}>enviando…</span>}
              {editForm.drive_link && <a href={editForm.drive_link} target="_blank" rel="noreferrer" style={{ color: 'var(--teal)' }}>✓ anexado</a>}
            </div>
          )}
        </td>
      </tr>
    )
  }
  return (
    <tr key={d.id} style={d.origem === 'reembolso' ? { background: '#fafafa' } : undefined}>
      <td style={{ fontSize: 11, color: 'var(--gray-mid)', whiteSpace: 'nowrap', paddingLeft: 14 + indent }}>{fmtData(d.data)}</td>
      <td style={{ fontWeight: 600, fontSize: 12 }}>
        {d.fornecedor}
        {d.origem === 'reembolso' && (
          <span style={{ marginLeft: 6, fontSize: 9, background: d.reembolso_status === 'cancelado' ? '#fee2e2' : '#e0e7ff', color: d.reembolso_status === 'cancelado' ? '#b91c1c' : '#3730a3', padding: '1px 6px', borderRadius: 999, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em' }}>
            {d.reembolso_status === 'cancelado' ? 'PERDA' : 'REEMB.'}
          </span>
        )}
        {d.criado_por_nome && (
          <span style={{ marginLeft: 6, fontSize: 9, background: '#f3f4f6', color: '#6b7280', padding: '1px 6px', borderRadius: 999, fontWeight: 600 }} title="Cadastrado por">
            {d.criado_por_nome.split(' ')[0]}
          </span>
        )}
        {(d.reembolsos_vinculados?.length ?? 0) > 0 && (
          <span
            style={{ marginLeft: 6, fontSize: 9, background: '#e0e7ff', color: '#3730a3', padding: '1px 6px', borderRadius: 999, fontWeight: 600 }}
            title={d.reembolsos_vinculados!.map(r => `${r.cliente_nome ?? '—'} — ${r.titulo}`).join('\n')}
          >
            🔗 {d.reembolsos_vinculados!.length === 1
              ? `${d.reembolsos_vinculados![0].cliente_nome ?? d.reembolsos_vinculados![0].titulo}`
              : `${d.reembolsos_vinculados!.length} reembolsos`}
          </span>
        )}
      </td>
      <td style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{d.categoria}</td>
      <td style={{ textAlign: 'right' }}>{fmtBRL(d.valor)}</td>
      <td>
        {d.tem_nota
          ? <span style={{ fontSize: 10, background: '#dcfce7', color: '#15803d', padding: '2px 6px', borderRadius: 999 }}>sim</span>
          : <span style={{ fontSize: 10, color: '#ef4444' }}>não</span>}
      </td>
      <td>
        <button
          disabled={d.origem === 'reembolso'}
          onClick={() => patchElegivel.mutate({ id: d.id, elegivel: !d.elegivel })}
          style={{
            fontSize: 10, padding: '2px 6px', borderRadius: 999, border: 'none',
            cursor: d.origem === 'reembolso' ? 'not-allowed' : 'pointer',
            background: d.elegivel ? '#dcfce7' : '#f3f4f6',
            color: d.elegivel ? '#15803d' : '#6b7280', fontWeight: 600,
            opacity: d.origem === 'reembolso' ? 0.7 : 1,
          }}
        >
          {d.elegivel ? 'sim' : 'não'}
        </button>
      </td>
      <td style={{ textAlign: 'right', fontSize: 11, color: (d.alq_iva_pct ?? 0) > 0 ? 'var(--teal)' : '#d1d5db', fontWeight: (d.alq_iva_pct ?? 0) > 0 ? 600 : 400 }}>
        {(d.alq_iva_pct ?? 0) > 0 ? `${(d.alq_iva_pct ?? 0).toFixed(2).replace('.', ',')}%` : '—'}
      </td>
      <td style={{ textAlign: 'right', color: d.credito.total > 0 ? 'var(--teal)' : 'var(--gray-mid)', fontWeight: d.credito.total > 0 ? 700 : 400 }}>
        {fmtBRL(d.credito.total)}
      </td>
      <td style={{ display: 'flex', gap: 4 }}>
        {d.origem === 'reembolso' ? (
          d.drive_link ? (
            <a href={d.drive_link} target="_blank" rel="noreferrer" title="Abrir reembolso no Drive" style={{ color: 'var(--teal)', fontSize: 13, textDecoration: 'none' }}>🔗</a>
          ) : (
            <span style={{ fontSize: 10, color: '#d1d5db' }} title="Sem link no Drive">🔗</span>
          )
        ) : (
          <>
            {d.drive_link && (
              <a href={d.drive_link} target="_blank" rel="noreferrer" title="Comprovante no Drive" style={{ color: 'var(--teal)', fontSize: 12, textDecoration: 'none' }}>📎</a>
            )}
            <button title="Editar" style={{ background: 'none', border: 'none', color: 'var(--gray-mid)', cursor: 'pointer', fontSize: 13 }} onClick={() => iniciarEdit(d)}>✎</button>
            <button title="Remover" style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 13 }} onClick={() => deleteDespesa.mutate(d.id)}>×</button>
          </>
        )}
      </td>
    </tr>
  )
}

function TabelaDespesas({ mes }: { mes: string }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['backoffice-lancamentos', mes],
    queryFn: () => backofficeApi.lancamentos(mes),
  })
  const { data: fornecedores = [] } = useQuery({
    queryKey: ['backoffice-fornecedores'],
    queryFn: backofficeApi.fornecedores,
  })
  const { data: categoriasDb = [] } = useQuery({
    queryKey: ['backoffice-categorias'],
    queryFn: backofficeApi.categorias,
  })
  const allCats = Array.from(new Set([...CATEGORIAS_PADRAO, ...categoriasDb]))

  const [editId, setEditId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<{ fornecedor: string; categoria: string; valor: number; data: string; tem_nota: boolean; elegivel: boolean; drive_link?: string }>({
    fornecedor: '', categoria: '', valor: 0, data: '', tem_nota: true, elegivel: false,
  })
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const toggle = (k: string) => setExpanded(p => ({ ...p, [k]: !p[k] }))

  const deleteDespesa = useMutation({
    mutationFn: (id: string) => backofficeApi.deleteDespesa(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] }),
  })
  const patchElegivel = useMutation({
    mutationFn: ({ id, elegivel }: { id: string; elegivel: boolean }) =>
      backofficeApi.patchDespesa(id, { elegivel }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] }),
  })
  const salvarEdit = useMutation({
    mutationFn: (id: string) => backofficeApi.patchDespesa(id, editForm),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] })
      setEditId(null)
    },
  })
  function iniciarEdit(d: Despesa) {
    setEditForm({
      fornecedor: d.fornecedor, categoria: d.categoria, valor: d.valor,
      data: d.data ?? '', tem_nota: d.tem_nota, elegivel: d.elegivel,
      drive_link: d.drive_link ?? undefined,
    })
    setEditId(d.id)
  }

  if (isLoading) return <div className={styles.empty}>Carregando…</div>
  const despesasManuais = (data?.despesas ?? []).filter(d => d.origem !== 'reembolso')
  const grupos = data?.reembolso_grupos ?? []

  const totalManuais = despesasManuais.reduce((s, d) => s + d.valor, 0)
  const totalGrupos = grupos.reduce((s, g) => s + g.valor_total, 0)
  const total = totalManuais + totalGrupos
  const totalCredito = despesasManuais.reduce((s, d) => s + d.credito.total, 0) + grupos.reduce((s, g) => s + g.credito_total, 0)

  // Agrupar despesas manuais por fornecedor — qualquer fornecedor com 2+ lançamentos vira pasta
  const porFornecedor: Record<string, Despesa[]> = {}
  for (const d of despesasManuais) {
    (porFornecedor[d.fornecedor] ||= []).push(d)
  }
  const linhasManuais: Array<{ tipo: 'unica'; despesa: Despesa } | { tipo: 'grupoFornecedor'; nome: string; itens: Despesa[] }> = []
  for (const [nome, itens] of Object.entries(porFornecedor)) {
    if (itens.length >= 2) linhasManuais.push({ tipo: 'grupoFornecedor', nome, itens })
    else linhasManuais.push({ tipo: 'unica', despesa: itens[0] })
  }

  // Cor do badge por status de reembolso
  const statusReembBadge = (status: string) => {
    if (status === 'cancelado') return { bg: '#fee2e2', color: '#b91c1c', label: 'PERDA' }
    if (status === 'pago') return { bg: '#dcfce7', color: '#15803d', label: 'PAGO' }
    if (status === 'enviado') return { bg: '#e0e7ff', color: '#3730a3', label: 'ENVIADO' }
    if (status === 'aguardando_pagamento') return { bg: '#fef3c7', color: '#92400e', label: 'AGUARDANDO' }
    return { bg: '#f3f4f6', color: '#6b7280', label: 'RASCUNHO' }
  }

  return (
    <div className={styles.tableCard}>
      <div style={{ padding: '12px 18px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: 13 }}>Despesas de {mesLabel(mes)}</span>
          <span style={{ fontSize: 11, color: 'var(--gray-mid)', marginLeft: 8 }}>
            {despesasManuais.length + grupos.reduce((s, g) => s + g.itens.length, 0)} itens · {fmtBRL(total)} · crédito IBS/CBS {fmtBRL(totalCredito)}
          </span>
        </div>
      </div>
      {grupos.length > 0 && (
        <div style={{ padding: '0 18px 8px', fontSize: 11, color: 'var(--gray-mid)' }}>
          🔗 Apenas reembolsos marcados como <strong>PERDA</strong> aparecem aqui (viram despesa real com crédito).
          Reembolsos normais ficam só na aba Reembolsos — não duplicam com os pagamentos do extrato.
        </div>
      )}
      {linhasManuais.length === 0 && grupos.length === 0 ? (
        <div className={styles.empty}>Nenhuma despesa lançada neste mês.</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Data</th><th>Fornecedor</th><th>Categoria</th>
                <th style={{ textAlign: 'right' }}>Valor</th>
                <th>Nota</th><th>Eleg.</th>
                <th style={{ textAlign: 'right' }}>% IVA</th>
                <th style={{ textAlign: 'right' }}>Crédito est.</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {/* Linha de soma (total geral) — destacada */}
              <tr style={{ background: '#f0fdf4', fontWeight: 700 }}>
                <td style={{ fontSize: 11, color: 'var(--gray-mid)' }}>TOTAL</td>
                <td colSpan={2} style={{ fontSize: 11, color: 'var(--gray-mid)' }}>
                  {despesasManuais.length + grupos.reduce((s, g) => s + g.itens.length, 0)} itens
                </td>
                <td style={{ textAlign: 'right', color: 'var(--dark)' }}>{fmtBRL(total)}</td>
                <td colSpan={3}></td>
                <td style={{ textAlign: 'right', color: totalCredito > 0 ? 'var(--teal)' : 'var(--gray-mid)' }}>{fmtBRL(totalCredito)}</td>
                <td></td>
              </tr>
              {/* Grupos de reembolso */}
              {grupos.map(g => {
                const open = expanded[g.id]
                const badge = statusReembBadge(g.reembolso_status)
                return (
                  <Fragment key={g.id}>
                    <tr style={{ background: '#f8fafc', cursor: 'pointer' }} onClick={() => toggle(g.id)}>
                      <td style={{ fontSize: 11, color: 'var(--gray-mid)', whiteSpace: 'nowrap' }}>
                        <span style={{ marginRight: 4, display: 'inline-block', transition: 'transform .15s', transform: open ? 'rotate(90deg)' : '' }}>▶</span>
                        {g.data_inicio && g.data_fim && g.data_inicio !== g.data_fim
                          ? `${fmtData(g.data_inicio)} – ${fmtData(g.data_fim)}`
                          : fmtData(g.data_inicio)}
                      </td>
                      <td style={{ fontWeight: 700, fontSize: 12 }}>
                        📁 {g.reembolso_titulo}
                        <span style={{ marginLeft: 6, fontSize: 9, background: badge.bg, color: badge.color, padding: '1px 6px', borderRadius: 999, fontWeight: 700, letterSpacing: '.04em' }}>
                          {badge.label}
                        </span>
                        {g.cliente_nome && (
                          <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--gray-mid)' }}>· {g.cliente_nome}</span>
                        )}
                      </td>
                      <td style={{ fontSize: 11, color: 'var(--gray-mid)' }}>
                        {g.itens.length} {g.itens.length === 1 ? 'despesa' : 'despesas'}
                      </td>
                      <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtBRL(g.valor_total)}</td>
                      <td colSpan={3}></td>
                      <td style={{ textAlign: 'right', color: g.credito_total > 0 ? 'var(--teal)' : '#d1d5db', fontWeight: g.credito_total > 0 ? 700 : 400 }}>
                        {fmtBRL(g.credito_total)}
                      </td>
                      <td onClick={e => e.stopPropagation()}>
                        {g.drive_link ? (
                          <a href={g.drive_link} target="_blank" rel="noreferrer" title="Abrir reembolso no Drive" style={{ color: 'var(--teal)', fontSize: 14, textDecoration: 'none' }}>🔗</a>
                        ) : (
                          <span style={{ fontSize: 11, color: '#d1d5db' }} title="Sem link no Drive">🔗</span>
                        )}
                      </td>
                    </tr>
                    {open && g.itens.map(it => (
                      <LinhaDespesa key={it.id} d={it} depth={1}
                        fornecedores={fornecedores} allCats={allCats}
                        editId={editId} editForm={editForm} setEditForm={setEditForm} setEditId={setEditId}
                        iniciarEdit={iniciarEdit} salvarEdit={salvarEdit} patchElegivel={patchElegivel} deleteDespesa={deleteDespesa}
                      />
                    ))}
                  </Fragment>
                )
              })}

              {/* Despesas manuais (com agrupamento por fornecedor quando 2+) */}
              {linhasManuais.map((l, idx) => {
                if (l.tipo === 'unica') {
                  return <LinhaDespesa key={l.despesa.id} d={l.despesa}
                    fornecedores={fornecedores} allCats={allCats}
                    editId={editId} editForm={editForm} setEditForm={setEditForm} setEditId={setEditId}
                    iniciarEdit={iniciarEdit} salvarEdit={salvarEdit} patchElegivel={patchElegivel} deleteDespesa={deleteDespesa}
                  />
                }
                const grpKey = `fornecedor:${l.nome}`
                const open = expanded[grpKey]
                const valorTotal = l.itens.reduce((s, x) => s + x.valor, 0)
                const credTotal = l.itens.reduce((s, x) => s + x.credito.total, 0)
                return (
                  <Fragment key={`grp-${idx}`}>
                    <tr style={{ background: '#fafafa', cursor: 'pointer' }} onClick={() => toggle(grpKey)}>
                      <td style={{ fontSize: 11, color: 'var(--gray-mid)', whiteSpace: 'nowrap' }}>
                        <span style={{ marginRight: 4, display: 'inline-block', transition: 'transform .15s', transform: open ? 'rotate(90deg)' : '' }}>▶</span>
                        ({l.itens.length})
                      </td>
                      <td style={{ fontWeight: 700, fontSize: 12 }}>{l.nome}</td>
                      <td style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{l.itens.length} lançamentos</td>
                      <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtBRL(valorTotal)}</td>
                      <td colSpan={3}></td>
                      <td style={{ textAlign: 'right', color: credTotal > 0 ? 'var(--teal)' : '#d1d5db', fontWeight: credTotal > 0 ? 700 : 400 }}>
                        {fmtBRL(credTotal)}
                      </td>
                      <td></td>
                    </tr>
                    {open && l.itens.map(it => (
                      <LinhaDespesa key={it.id} d={it} depth={1}
                        fornecedores={fornecedores} allCats={allCats}
                        editId={editId} editForm={editForm} setEditForm={setEditForm} setEditId={setEditId}
                        iniciarEdit={iniciarEdit} salvarEdit={salvarEdit} patchElegivel={patchElegivel} deleteDespesa={deleteDespesa}
                      />
                    ))}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ─── Aba Fornecedores ─────────────────────────────────────────────────────────

// ─── Aba Adiantamentos (ledger de saldo + alocação por item de reembolso) ──────

function AlocarPanel({ adiantamento, onDone }: { adiantamento: Adiantamento; onDone: () => void }) {
  const qc = useQueryClient()
  const { data: reembolsos = [] } = useQuery({ queryKey: ['reembolsos'], queryFn: () => reembolsosApi.listar() })
  const { data: clientes = [] } = useQuery({ queryKey: ['clientes'], queryFn: () => clientesApi.listar() })
  const cliNome = (id: string) => clientes.find(c => c.id === id)?.nome ?? '—'

  const [pastaId, setPastaId] = useState('')
  // item_id -> valor alocado (selecionados)
  const [selItens, setSelItens] = useState<Record<string, number>>({})
  const [novoItemDesc, setNovoItemDesc] = useState('')
  const [novoItemValor, setNovoItemValor] = useState(0)
  const [criandoPasta, setCriandoPasta] = useState(false)
  const [novaPastaCliente, setNovaPastaCliente] = useState('')
  const [novaPastaClienteId, setNovaPastaClienteId] = useState('')
  const [novaPastaTitulo, setNovaPastaTitulo] = useState('')

  const pasta = reembolsos.find(r => r.id === pastaId)
  const pastasOpts = reembolsos
    .filter(r => r.status !== 'cancelado')
    .map(r => ({ value: r.id, label: labelPasta(r, cliNome(r.cliente_id)) }))

  const somaSelecionada =
    Object.values(selItens).reduce((s, v) => s + v, 0) +
    (novoItemDesc && novoItemValor ? novoItemValor : 0)
  const excede = somaSelecionada - adiantamento.saldo > 0.001

  const alocar = useMutation({
    mutationFn: () => {
      const itens: AlocarItem[] = []
      for (const [itemId, valor] of Object.entries(selItens)) {
        if (valor > 0) itens.push({ reembolso_id: pastaId, item_reembolso_id: itemId, valor })
      }
      if (novoItemDesc && novoItemValor > 0 && pastaId) {
        itens.push({ reembolso_id: pastaId, novo_item: { descricao: novoItemDesc, valor: novoItemValor }, valor: novoItemValor })
      }
      return backofficeApi.alocarAdiantamento(adiantamento.despesa_id, itens)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['adiantamentos'] })
      qc.invalidateQueries({ queryKey: ['reembolsos'] })
      onDone()
    },
    onError: (e: any) => alert(`Erro ao alocar: ${e?.response?.data?.detail || e?.message}`),
  })

  const criarPasta = useMutation({
    mutationFn: async () => {
      const novo = await reembolsosApi.criar({
        cliente_id: novaPastaClienteId,
        titulo: novaPastaTitulo.trim(),
        data_emissao: new Date().toISOString().slice(0, 10),
      })
      return novo
    },
    onSuccess: (novo) => {
      qc.invalidateQueries({ queryKey: ['reembolsos'] })
      setPastaId(novo.id); setCriandoPasta(false)
      setNovaPastaCliente(''); setNovaPastaClienteId(''); setNovaPastaTitulo('')
    },
    onError: (e: any) => alert(`Erro ao criar pasta: ${e?.response?.data?.detail || e?.message}`),
  })

  return (
    <div style={{ padding: '12px 14px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, marginTop: 8 }}>
      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8, color: '#92400e' }}>
        Alocar saldo ({fmtBRL(adiantamento.saldo)}) a itens de reembolso
      </div>

      {/* Escolher pasta */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 280, flex: 1 }}>
          <Combobox
            value={pasta ? labelPasta(pasta, cliNome(pasta.cliente_id)) : ''}
            onChange={(label) => {
              const opt = pastasOpts.find(o => o.label === label)
              setPastaId(opt?.value ?? '')
              setSelItens({})
            }}
            options={pastasOpts}
            placeholder="Pasta de reembolso (ativas e pagas)…"
          />
        </div>
        <button type="button" className={styles.btnSmall} onClick={() => setCriandoPasta(v => !v)}>
          {criandoPasta ? 'Cancelar' : '+ Nova pasta'}
        </button>
      </div>

      {/* Criar pasta nova */}
      {criandoPasta && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 6, marginBottom: 10, alignItems: 'center' }}>
          <Combobox
            value={novaPastaCliente}
            onChange={(nome) => { setNovaPastaCliente(nome); setNovaPastaClienteId(clientes.find(c => c.nome === nome)?.id ?? '') }}
            options={clientes.map(c => ({ value: c.id, label: c.nome }))}
            placeholder="Cliente"
          />
          <input value={novaPastaTitulo} onChange={e => setNovaPastaTitulo(e.target.value)} placeholder="Título da pasta"
            style={{ padding: '7px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, fontFamily: 'Archivo, sans-serif' }} />
          <button type="button" className={styles.btnPrimary} style={{ padding: '5px 12px', fontSize: 12 }}
            disabled={!novaPastaClienteId || !novaPastaTitulo.trim() || criarPasta.isPending}
            onClick={() => criarPasta.mutate()}>Criar pasta</button>
        </div>
      )}

      {/* Itens da pasta */}
      {pasta && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--gray-mid)', marginBottom: 4 }}>
            Itens em <strong>{pasta.titulo}</strong> — marque os que este pagamento cobre:
          </div>
          {pasta.itens.length === 0 && <div style={{ fontSize: 11, color: 'var(--gray-mid)' }}>Pasta sem itens. Crie um abaixo.</div>}
          {pasta.itens.map(it => {
            const sel = selItens[it.id] != null
            return (
              <div key={it.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0' }}>
                <input type="checkbox" checked={sel} onChange={e => {
                  setSelItens(prev => {
                    const next = { ...prev }
                    if (e.target.checked) next[it.id] = it.valor
                    else delete next[it.id]
                    return next
                  })
                }} />
                <span style={{ fontSize: 12, flex: 1 }}>{it.descricao} <span style={{ color: 'var(--gray-mid)' }}>· {it.natureza}</span></span>
                {sel ? (
                  <MoneyInput value={selItens[it.id]} onValue={v => setSelItens(prev => ({ ...prev, [it.id]: v }))} style={{ fontSize: 12, padding: '3px 6px', width: 90 }} />
                ) : (
                  <span style={{ fontSize: 12, color: 'var(--gray-mid)' }}>{fmtBRL(it.valor)}</span>
                )}
              </div>
            )
          })}

          {/* Criar item novo na pasta */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6 }}>
            <span style={{ fontSize: 11, color: 'var(--gray-mid)' }}>+ novo item:</span>
            <input value={novoItemDesc} onChange={e => setNovoItemDesc(e.target.value)} placeholder="descrição (ex.: busca certidão)"
              style={{ padding: '5px 8px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, fontFamily: 'Archivo, sans-serif', flex: 1 }} />
            <MoneyInput value={novoItemValor} onValue={setNovoItemValor} style={{ fontSize: 12, padding: '3px 6px', width: 90 }} />
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between', marginTop: 8 }}>
        <span style={{ fontSize: 12, color: excede ? '#b91c1c' : 'var(--gray-mid)' }}>
          Selecionado: <strong>{fmtBRL(somaSelecionada)}</strong> de {fmtBRL(adiantamento.saldo)}
          {excede && ' — excede o saldo!'}
        </span>
        <button className={styles.btnPrimary} disabled={somaSelecionada <= 0 || excede || alocar.isPending} onClick={() => alocar.mutate()}>
          {alocar.isPending ? 'Alocando…' : 'Alocar'}
        </button>
      </div>
    </div>
  )
}

function AbaAdiantamentos() {
  const qc = useQueryClient()
  const { data: adiantamentos = [], isLoading } = useQuery({
    queryKey: ['adiantamentos'],
    queryFn: () => backofficeApi.listarAdiantamentos(),
  })
  const [expandido, setExpandido] = useState<string | null>(null)
  const [alocando, setAlocando] = useState<string | null>(null)

  const removerAloc = useMutation({
    mutationFn: (id: string) => backofficeApi.removerAlocacao(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['adiantamentos'] }),
  })
  const perda = useMutation({
    mutationFn: (despesaId: string) => backofficeApi.perdaSaldoAdiantamento(despesaId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adiantamentos'] }); qc.invalidateQueries({ queryKey: ['backoffice-lancamentos'] }) },
    onError: (e: any) => alert(`Erro: ${e?.response?.data?.detail || e?.message}`),
  })

  if (isLoading) return <div className={styles.empty}>Carregando…</div>

  const comSaldo = adiantamentos.filter(a => a.saldo > 0.001)
  const zerados = adiantamentos.filter(a => a.saldo <= 0.001)

  function Card({ a }: { a: Adiantamento }) {
    const pct = a.valor > 0 ? Math.min(100, (a.total_alocado / a.valor) * 100) : 0
    const pctPerda = a.valor > 0 ? Math.min(100, (a.perda_valor / a.valor) * 100) : 0
    const open = expandido === a.despesa_id
    return (
      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 10, overflow: 'hidden', background: '#fff' }}>
        <div style={{ padding: '12px 14px', display: 'grid', gridTemplateColumns: '1fr 130px 200px auto', gap: 12, alignItems: 'center' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{a.fornecedor}</div>
            <div style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{a.categoria} · {fmtData(a.data)} · {mesLabel(a.mes)}</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 11, color: 'var(--gray-mid)' }}>Total</div>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{fmtBRL(a.valor)}</div>
          </div>
          <div>
            <div style={{ height: 8, background: '#f3f4f6', borderRadius: 999, overflow: 'hidden', display: 'flex' }}>
              <div style={{ width: `${pct}%`, background: 'var(--teal)' }} />
              <div style={{ width: `${pctPerda}%`, background: '#ef4444' }} />
            </div>
            <div style={{ fontSize: 10, color: 'var(--gray-mid)', marginTop: 3 }}>
              Alocado {fmtBRL(a.total_alocado)}{a.perda_valor > 0 ? ` · Perda ${fmtBRL(a.perda_valor)}` : ''}
              {a.saldo > 0.001
                ? <strong style={{ color: '#b45309' }}> · Saldo {fmtBRL(a.saldo)}</strong>
                : <strong style={{ color: '#15803d' }}> · zerado</strong>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {a.saldo > 0.001 && (
              <>
                <button className={styles.btnPrimary} style={{ padding: '5px 12px', fontSize: 12 }}
                  onClick={() => setAlocando(alocando === a.despesa_id ? null : a.despesa_id)}>
                  {alocando === a.despesa_id ? 'Fechar' : 'Alocar'}
                </button>
                <button className={styles.btnDanger} style={{ padding: '5px 10px', fontSize: 12 }}
                  title="Marca o saldo não alocado como perda (escritório absorve). Já desconta o que foi alocado."
                  onClick={() => { if (confirm(`Ignorar/perda do saldo de ${fmtBRL(a.saldo)}? Vira despesa do escritório (crédito IBS/CBS). O que já foi alocado a clientes não é afetado.`)) perda.mutate(a.despesa_id) }}>
                  Ignorar / perda
                </button>
              </>
            )}
            <button className={styles.btnSmall} style={{ fontSize: 12 }} onClick={() => setExpandido(open ? null : a.despesa_id)}>
              {open ? '▲' : `▼ ${a.alocacoes.length}`}
            </button>
          </div>
        </div>

        {alocando === a.despesa_id && (
          <div style={{ padding: '0 14px 12px' }}>
            <AlocarPanel adiantamento={a} onDone={() => setAlocando(null)} />
          </div>
        )}

        {open && (
          <div style={{ padding: '0 14px 12px', borderTop: '1px solid #f3f4f6' }}>
            {a.alocacoes.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--gray-mid)', padding: '8px 0' }}>Nenhuma alocação ainda.</div>
            ) : (
              a.alocacoes.map(al => (
                <div key={al.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #f9fafb', fontSize: 12 }}>
                  <span style={{ flex: 1 }}>
                    <strong>{al.cliente_nome ?? '—'}</strong> · {al.reembolso_titulo ?? '—'}
                    {al.item_descricao && <span style={{ color: 'var(--gray-mid)' }}> · {al.item_descricao}</span>}
                  </span>
                  <span style={{ fontWeight: 600 }}>{fmtBRL(al.valor)}</span>
                  <button style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }} onClick={() => removerAloc.mutate(al.id)}>×</button>
                </div>
              ))
            )}
            {a.saldo > 0.001 && (
              <div style={{ marginTop: 8 }}>
                <button className={styles.btnDanger} style={{ fontSize: 12 }}
                  onClick={() => { if (confirm(`Tratar o saldo de ${fmtBRL(a.saldo)} como PERDA? Vira despesa elegível a crédito.`)) perda.mutate(a.despesa_id) }}>
                  Tratar saldo ({fmtBRL(a.saldo)}) como perda
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--gray-mid)', marginBottom: 12 }}>
        Adiantamentos são pagamentos reembolsáveis (ex.: ONR) consumidos por itens de reembolso ao longo dos meses.
        O saldo não alocado permanece aqui até você alocar ou tratar como perda.
      </div>

      {comSaldo.length > 0 && (
        <>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#b45309', marginBottom: 6 }}>⏳ Com saldo a alocar ({comSaldo.length})</div>
          {comSaldo.map(a => <Card key={a.despesa_id} a={a} />)}
        </>
      )}

      {zerados.length > 0 && (
        <>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#15803d', margin: '12px 0 6px' }}>✓ Zerados / em perda ({zerados.length})</div>
          {zerados.map(a => <Card key={a.despesa_id} a={a} />)}
        </>
      )}

      {adiantamentos.length === 0 && (
        <div className={styles.empty}>Nenhum adiantamento. Categorize uma despesa do extrato como reembolsável para ela aparecer aqui.</div>
      )}
    </div>
  )
}

function AbaFornecedores() {
  const qc = useQueryClient()
  const { data: fornecedores = [] } = useQuery({
    queryKey: ['backoffice-fornecedores'],
    queryFn: backofficeApi.fornecedores,
  })
  const { data: categoriasData = [] } = useQuery({
    queryKey: ['backoffice-categorias'],
    queryFn: backofficeApi.categorias,
  })
  const allCats = Array.from(new Set([...CATEGORIAS_PADRAO, ...categoriasData]))

  const [busca, setBusca] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [novoNome, setNovoNome] = useState('')
  const [novoCnpj, setNovoCnpj] = useState('')
  const [novaCat, setNovaCat] = useState('')

  const save = useMutation({
    mutationFn: () => backofficeApi.upsertFornecedor({
      nome: novoNome.trim(),
      cnpj: novoCnpj.replace(/\D/g, '') || undefined,
      categoria_padrao: novaCat || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['backoffice-fornecedores'] })
      setNovoNome(''); setNovoCnpj(''); setNovaCat(''); setShowForm(false)
    },
  })

  const filtered = fornecedores.filter(f =>
    f.nome.toLowerCase().includes(busca.toLowerCase()) ||
    (f.cnpj ?? '').includes(busca.replace(/\D/g, ''))
  )

  return (
    <div className={styles.tableCard}>
      <div style={{ padding: '14px 18px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: 13 }}>Fornecedores cadastrados</span>
          <span style={{ fontSize: 11, color: 'var(--gray-mid)', marginLeft: 8 }}>
            {fornecedores.length} fornecedor(es)
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Buscar por nome ou CNPJ…"
            style={{ padding: '6px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, fontFamily: 'Archivo, sans-serif', minWidth: 220 }}
          />
          <button className={styles.btnSmall} onClick={() => setShowForm(v => !v)}>
            {showForm ? 'Cancelar' : '+ Novo fornecedor'}
          </button>
        </div>
      </div>

      {showForm && (
        <div style={{ padding: '4px 18px 14px', display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr auto', gap: 10, alignItems: 'end', borderBottom: '1px solid #f3f4f6' }}>
          <div className={styles.fieldGroup}>
            <span>Nome</span>
            <input value={novoNome} onChange={e => setNovoNome(e.target.value)}
              style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif' }} />
          </div>
          <div className={styles.fieldGroup}>
            <span>CNPJ</span>
            <input
              value={novoCnpj}
              onChange={e => setNovoCnpj(fmtCNPJ(e.target.value))}
              placeholder="00.000.000/0000-00"
              style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif' }}
            />
          </div>
          <div className={styles.fieldGroup}>
            <span>Categoria padrão</span>
            <Combobox
              value={novaCat}
              onChange={setNovaCat}
              options={allCats.map(c => ({ value: c, label: c }))}
              placeholder="—"
              onCreate={setNovaCat}
            />
          </div>
          <button
            className={styles.btnPrimary}
            disabled={!novoNome.trim() || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className={styles.empty}>
          {busca ? 'Nenhum fornecedor encontrado.' : 'Nenhum fornecedor cadastrado ainda.'}
        </div>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Nome</th><th>CNPJ</th><th>Categoria padrão</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(f => (
              <tr key={f.id}>
                <td style={{ fontWeight: 600 }}>{f.nome}</td>
                <td style={{ color: 'var(--gray-mid)', fontFamily: 'monospace', fontSize: 12 }}>
                  {f.cnpj ? fmtCNPJ(f.cnpj) : <span style={{ color: '#d1d5db' }}>—</span>}
                </td>
                <td style={{ color: 'var(--gray-mid)', fontSize: 12 }}>
                  {f.categoria_padrao ?? <span style={{ color: '#d1d5db' }}>—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

type Aba = 'lancamentos' | 'adiantamentos' | 'fornecedores'
type SecaoAberta = 'nova' | 'extrato' | 'recorrentes' | null

export default function DespesasPage() {
  const [aba, setAba] = useState<Aba>('lancamentos')
  const [mes, setMes] = useState(mesAtual)
  const [secao, setSecao] = useState<SecaoAberta>(null)

  const { data: fornecedoresData = [] } = useQuery({
    queryKey: ['backoffice-fornecedores'],
    queryFn: backofficeApi.fornecedores,
  })
  const { data: categoriasData = [] } = useQuery({
    queryKey: ['backoffice-categorias'],
    queryFn: backofficeApi.categorias,
  })

  function toggleSecao(s: SecaoAberta) {
    setSecao(prev => prev === s ? null : s)
  }

  const btnAtivo = (s: SecaoAberta) => ({
    padding: '7px 16px', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer',
    fontFamily: 'Archivo, sans-serif', transition: 'background .15s, border-color .15s',
    border: secao === s ? '1px solid var(--teal)' : '1px solid #e5e7eb',
    background: secao === s ? 'var(--teal-light)' : '#fff',
    color: secao === s ? 'var(--teal)' : 'var(--dark)',
  } as React.CSSProperties)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Cabeçalho */}
      <div className={styles.pageHeader} style={{ flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 className={styles.pageTitle}>Despesas</h1>
          <div style={{ fontSize: 12, color: 'var(--gray-mid)', marginTop: 2 }}>
            Lançamentos mensais · base para crédito IBS/CBS na Decisão Tributária
          </div>
        </div>
        {aba === 'lancamentos' && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="month"
              value={mes}
              onChange={e => setMes(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #e5e7eb', fontSize: 13 }}
            />
            <button style={btnAtivo('nova')} onClick={() => toggleSecao('nova')}>+ Nova despesa</button>
            <button style={btnAtivo('extrato')} onClick={() => toggleSecao('extrato')}>📄 Subir extrato</button>
            <button style={btnAtivo('recorrentes')} onClick={() => toggleSecao('recorrentes')}>🔁 Recorrentes</button>
          </div>
        )}
      </div>

      {/* Sub-abas */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid #e5e7eb' }}>
        {([
          { id: 'lancamentos' as Aba, label: 'Lançamentos' },
          { id: 'adiantamentos' as Aba, label: 'Adiantamentos' },
          { id: 'fornecedores' as Aba, label: 'Fornecedores' },
        ]).map(t => (
          <button
            key={t.id}
            onClick={() => setAba(t.id)}
            style={{
              padding: '8px 18px',
              background: 'none', border: 'none',
              borderBottom: aba === t.id ? '2px solid var(--teal)' : '2px solid transparent',
              cursor: 'pointer', fontSize: 13,
              fontWeight: aba === t.id ? 700 : 400,
              color: aba === t.id ? 'var(--teal)' : 'var(--gray-mid)',
              transition: 'color .15s', marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {aba === 'adiantamentos' && <AbaAdiantamentos />}
      {aba === 'fornecedores' && <AbaFornecedores />}

      {aba === 'lancamentos' && <>

      {/* Painéis expansíveis */}
      {secao === 'nova' && (
        <div className={styles.tableCard} style={{ padding: '14px 0 0' }}>
          <div style={{ padding: '0 18px 10px', fontWeight: 700, fontSize: 13 }}>Nova despesa</div>
          <FormNovaDespesa
            mes={mes}
            fornecedores={fornecedoresData}
            categorias={categoriasData}
            onSaved={() => setSecao(null)}
          />
        </div>
      )}

      {secao === 'extrato' && (
        <div className={styles.tableCard} style={{ padding: '14px 18px' }}>
          <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12 }}>Importar extrato bancário</div>
          <SecaoExtrato
            mes={mes}
            fornecedores={fornecedoresData}
            categorias={categoriasData}
            onSaved={() => setSecao(null)}
          />
        </div>
      )}

      {secao === 'recorrentes' && (
        <div className={styles.tableCard} style={{ padding: '14px 18px' }}>
          <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>Despesas recorrentes</div>
          <div style={{ fontSize: 11, color: 'var(--gray-mid)', marginBottom: 12 }}>
            Selecione as que ocorreram em {mesLabel(mes)}, ajuste os valores se necessário e confirme.
          </div>
          <SecaoRecorrentes
            mes={mes}
            fornecedores={fornecedoresData}
            categorias={categoriasData}
            onSaved={() => setSecao(null)}
          />
        </div>
      )}

      {/* Tabela */}
      <TabelaDespesas mes={mes} />
      </>}
    </div>
  )
}
