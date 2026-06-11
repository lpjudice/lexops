import { Fragment, useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  backofficeApi,
  type Despesa,
  type DespesaRecorrente,
  type Fornecedor,
  type ParsedExpense,
} from '../api/backoffice'
import styles from './Page.module.css'

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
  const display = open ? search : (value || '')
  const filtered = options.filter(o =>
    o.label.toLowerCase().includes((open ? search : '').toLowerCase())
  )
  const exactMatch = options.some(o => o.label.toLowerCase() === search.toLowerCase())

  return (
    <div style={{ position: 'relative' }}>
      <input
        value={display}
        onChange={e => { setSearch(e.target.value); setOpen(true); onChange(e.target.value) }}
        onFocus={() => { setSearch(value); setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        style={{ width: '100%', padding: '8px 28px 8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif' }}
      />
      <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af', fontSize: 10, pointerEvents: 'none' }}>▼</span>
      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
          background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,.1)', marginTop: 2, maxHeight: 420, overflowY: 'auto',
        }}>
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
        </div>
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

  const save = useMutation({
    mutationFn: () =>
      backofficeApi.addDespesa(mes, { categoria, fornecedor, valor, data: dataDespesa, tem_nota: temNota, elegivel }),
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
      setFornecedor(''); setCnpj(''); setCategoria(''); setValor(0)
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

      <div style={{ display: 'flex', gap: 16, alignItems: 'center', paddingTop: 6, gridColumn: '1/-1' }}>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
          <input type="checkbox" checked={temNota} onChange={e => setTemNota(e.target.checked)} />
          Tem nota fiscal
        </label>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
          <input type="checkbox" checked={elegivel} onChange={e => setElegivel(e.target.checked)} />
          Elegível IBS/CBS
        </label>
      </div>
      <div style={{ gridColumn: '1/-1' }}>
        <button
          className={styles.btnPrimary}
          disabled={!fornecedor || valor <= 0 || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? 'Salvando…' : 'Adicionar despesa'}
        </button>
      </div>
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
  const [linhas, setLinhas] = useState<(ParsedExpense & { selecionado: boolean; elegivel: boolean })[]>([])
  const [parsing, setParsing] = useState(false)
  const [parseErr, setParseErr] = useState<string | null>(null)
  const allCats = Array.from(new Set([...CATEGORIAS_PADRAO, ...categorias]))

  async function handleFile(file: File) {
    setParsing(true); setParseErr(null); setLinhas([])
    try {
      const res = await backofficeApi.parseExtrato(file)
      setLinhas(res.linhas.map(l => ({ ...l, selecionado: true, elegivel: false })))
    } catch {
      setParseErr('Falha ao processar o arquivo. Verifique se é uma imagem ou PDF legível.')
    } finally {
      setParsing(false)
    }
  }

  const confirmar = useMutation({
    mutationFn: () => {
      const selecionadas = linhas.filter(l => l.selecionado)
      return backofficeApi.addDespesasBatch(mes, selecionadas.map(l => ({
        categoria: l.categoria,
        fornecedor: l.fornecedor,
        descricao: l.descricao,
        valor: l.valor,
        tem_nota: false,
        elegivel: l.elegivel,
      })))
    },
    onSuccess: async () => {
      // Salva fornecedores novos
      const novos = linhas.filter(l => l.selecionado && l.fornecedor)
      for (const l of novos) {
        await backofficeApi.upsertFornecedor({ nome: l.fornecedor, categoria_padrao: l.categoria || undefined })
      }
      qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] })
      qc.invalidateQueries({ queryKey: ['backoffice-despesas', mes] })
      setLinhas([])
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
          <span style={{ color: 'var(--teal)', fontSize: 13 }}>⏳ Analisando com IA…</span>
        ) : (
          <>
            <div style={{ fontSize: 22, marginBottom: 6 }}>📄</div>
            <div style={{ fontSize: 13, color: 'var(--gray-mid)' }}>
              Arraste ou clique para enviar extrato bancário (imagem ou PDF)
            </div>
            <div style={{ fontSize: 11, color: '#c0c5c5', marginTop: 4 }}>
              A IA extrai as saídas automaticamente para você revisar
            </div>
          </>
        )}
      </div>

      {parseErr && (
        <div style={{ marginTop: 8, padding: '8px 12px', background: '#fee2e2', borderRadius: 6, fontSize: 12, color: '#b91c1c' }}>
          {parseErr}
        </div>
      )}

      {linhas.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8, color: 'var(--dark)' }}>
            {linhas.length} saída(s) detectada(s) — revise e confirme:
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {linhas.map((l, i) => (
              <div
                key={i}
                style={{
                  display: 'grid', gridTemplateColumns: '24px 1fr 1fr 100px 80px 80px',
                  gap: 8, alignItems: 'center', padding: '8px 12px',
                  background: l.selecionado ? '#f0fdf4' : '#f9fafb',
                  borderRadius: 6, border: '1px solid #e5e7eb',
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
                  onChange={c => setLinhas(prev => prev.map((x, j) => j === i ? { ...x, categoria: c } : x))}
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
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
            <button
              className={styles.btnPrimary}
              disabled={confirmar.isPending || !linhas.some(l => l.selecionado)}
              onClick={() => confirmar.mutate()}
            >
              {confirmar.isPending ? 'Lançando…' : `Lançar ${linhas.filter(l => l.selecionado).length} despesa(s)`}
            </button>
            <button className={styles.btnSmall} onClick={() => setLinhas([])}>Cancelar</button>
          </div>
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
              <button className={styles.btnPrimary} onClick={() => salvarEdit.mutate(d.id)} disabled={salvarEdit.isPending}>
                {salvarEdit.isPending ? '…' : 'Salvar'}
              </button>
              <button className={styles.btnSmall} onClick={() => setEditId(null)}>Cancelar</button>
            </div>
          </div>
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
  const [editForm, setEditForm] = useState<{ fornecedor: string; categoria: string; valor: number; data: string; tem_nota: boolean; elegivel: boolean }>({
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
          🔗 Reembolsos aparecem agrupados por pasta (1 card de reembolso = 1 grupo). Clique na seta para expandir.
          <strong> Cancelados</strong> viram despesa real; demais status não geram crédito (apenas referência).
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

type Aba = 'lancamentos' | 'fornecedores'
type SecaoAberta = 'nova' | 'extrato' | 'recorrentes' | null

export default function DespesasPage() {
  const [aba, setAba] = useState<Aba>('lancamentos')
  const [mes, setMes] = useState(mesAtual)
  const [secao, setSecao] = useState<SecaoAberta>(null)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)

  const { data: fornecedoresData = [] } = useQuery({
    queryKey: ['backoffice-fornecedores'],
    queryFn: backofficeApi.fornecedores,
  })
  const { data: categoriasData = [] } = useQuery({
    queryKey: ['backoffice-categorias'],
    queryFn: backofficeApi.categorias,
  })

  async function syncNfs() {
    setSyncing(true); setSyncMsg(null)
    try {
      const r = await backofficeApi.syncNfsHistorico()
      setSyncMsg(`✓ DFe sincronizado — ${r.processados ?? 0} NF(s) processada(s).`)
    } catch {
      setSyncMsg('⚠ Falha ao sincronizar. Verifique o certificado digital.')
    } finally {
      setSyncing(false)
    }
  }

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

      {aba === 'fornecedores' && <AbaFornecedores />}

      {aba === 'lancamentos' && <>

      {/* Sync NFs */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <button className={styles.btnSmall} disabled={syncing} onClick={syncNfs}>
          {syncing ? 'Sincronizando…' : '↻ Sincronizar NFs históricas (DFe)'}
        </button>
        {syncMsg && <span style={{ fontSize: 12, color: syncMsg.startsWith('✓') ? '#15803d' : '#b45309' }}>{syncMsg}</span>}
      </div>

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
