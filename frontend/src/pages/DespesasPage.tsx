import { useRef, useState } from 'react'
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

const CATEGORIAS_PADRAO = [
  'Software jurídico','Marketing / publicidade','Correspondentes','Aluguel',
  'Energia elétrica','Telefonia','Internet','Contabilidade','Despesas com clientes',
  'Material de escritório','Outros',
]
const STATUS_COR: Record<string, string> = {
  validado: '#15803d', revalidar: '#b45309', pendente: '#6b7280', novo: '#1d4ed8',
}

// ─── Combobox de fornecedor ────────────────────────────────────────────────────

function FornecedorInput({
  value,
  onChange,
  fornecedores,
  onSelect,
}: {
  value: string
  onChange: (v: string) => void
  fornecedores: Fornecedor[]
  onSelect: (f: Fornecedor) => void
}) {
  const [open, setOpen] = useState(false)
  const filtered = fornecedores.filter(f =>
    f.nome.toLowerCase().includes(value.toLowerCase())
  ).slice(0, 8)

  return (
    <div style={{ position: 'relative' }}>
      <input
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Nome do fornecedor"
        style={{ width: '100%', padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif' }}
      />
      {open && filtered.length > 0 && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
          background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,.1)', marginTop: 2,
        }}>
          {filtered.map(f => (
            <div
              key={f.id}
              onMouseDown={() => { onSelect(f); setOpen(false) }}
              style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              onMouseEnter={e => (e.currentTarget.style.background = '#f0fdf4')}
              onMouseLeave={e => (e.currentTarget.style.background = '')}
            >
              <span>{f.nome}</span>
              {f.categoria_padrao && (
                <span style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{f.categoria_padrao}</span>
              )}
            </div>
          ))}
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
  const [temNota, setTemNota] = useState(true)
  const [elegivel, setElegivel] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      backofficeApi.addDespesa(mes, { categoria, fornecedor, valor, tem_nota: temNota, elegivel }),
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
      onSaved()
    },
  })

  const allCats = Array.from(new Set([...CATEGORIAS_PADRAO, ...categorias]))

  return (
    <div style={{ padding: '0 18px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
      <div className={styles.fieldGroup}>
        <span>Fornecedor</span>
        <FornecedorInput
          value={fornecedor}
          onChange={setFornecedor}
          fornecedores={fornecedores}
          onSelect={f => {
            setFornecedor(f.nome)
            setCnpj(f.cnpj ? fmtCNPJ(f.cnpj) : '')
            if (f.categoria_padrao && !categoria) setCategoria(f.categoria_padrao)
          }}
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
        <select
          value={categoria}
          onChange={e => setCategoria(e.target.value)}
          style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif', color: 'var(--dark)', background: '#fff' }}
        >
          <option value="">Selecione…</option>
          {allCats.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div className={styles.fieldGroup}>
        <span>Valor (R$)</span>
        <MoneyInput value={valor} onValue={setValor} />
      </div>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', paddingTop: 18, gridColumn: '1/-1' }}>
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
                <select
                  value={l.categoria}
                  onChange={e => setLinhas(prev => prev.map((x, j) => j === i ? { ...x, categoria: e.target.value } : x))}
                  style={{ fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4, padding: '4px 6px', fontFamily: 'Archivo, sans-serif', color: 'var(--dark)' }}
                >
                  {allCats.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
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
            <FornecedorInput
              value={novaFornecedor}
              onChange={setNovaFornecedor}
              fornecedores={fornecedores}
              onSelect={f => { setNovaFornecedor(f.nome); if (f.categoria_padrao) setNovaCategoria(f.categoria_padrao) }}
            />
          </div>
          <div className={styles.fieldGroup}>
            <span>Categoria</span>
            <select
              value={novaCategoria}
              onChange={e => setNovaCategoria(e.target.value)}
              style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif', color: 'var(--dark)', background: '#fff' }}
            >
              <option value="">Selecione…</option>
              {allCats.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
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

function TabelaDespesas({ mes }: { mes: string }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['backoffice-lancamentos', mes],
    queryFn: () => backofficeApi.lancamentos(mes),
  })

  const deleteDespesa = useMutation({
    mutationFn: (id: string) => backofficeApi.deleteDespesa(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] })
    },
  })

  const patchElegivel = useMutation({
    mutationFn: ({ id, elegivel }: { id: string; elegivel: boolean }) =>
      backofficeApi.patchDespesa(id, { elegivel }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backoffice-lancamentos', mes] }),
  })

  if (isLoading) return <div className={styles.empty}>Carregando…</div>
  const despesas = data?.despesas ?? []

  const total = despesas.reduce((s, d) => s + d.valor, 0)
  const totalCredito = despesas.reduce((s, d) => s + d.credito.total, 0)

  return (
    <div className={styles.tableCard}>
      <div style={{ padding: '12px 18px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: 13 }}>Despesas de {mesLabel(mes)}</span>
          <span style={{ fontSize: 11, color: 'var(--gray-mid)', marginLeft: 8 }}>
            {despesas.length} itens · {fmtBRL(total)} · crédito IBS/CBS {fmtBRL(totalCredito)}
          </span>
        </div>
      </div>
      {despesas.length === 0 ? (
        <div className={styles.empty}>Nenhuma despesa lançada neste mês.</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Fornecedor</th><th>Categoria</th>
                <th style={{ textAlign: 'right' }}>Valor</th>
                <th>Nota</th><th>Elegível</th>
                <th style={{ textAlign: 'right' }}>Crédito est.</th>
                <th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {despesas.map((d: Despesa) => (
                <tr key={d.id}>
                  <td style={{ fontWeight: 600, fontSize: 12 }}>{d.fornecedor}</td>
                  <td style={{ fontSize: 11, color: 'var(--gray-mid)' }}>{d.categoria}</td>
                  <td style={{ textAlign: 'right' }}>{fmtBRL(d.valor)}</td>
                  <td>
                    {d.tem_nota
                      ? <span style={{ fontSize: 10, background: '#dcfce7', color: '#15803d', padding: '2px 6px', borderRadius: 999 }}>sim</span>
                      : <span style={{ fontSize: 10, color: '#ef4444' }}>não</span>}
                  </td>
                  <td>
                    <button
                      onClick={() => patchElegivel.mutate({ id: d.id, elegivel: !d.elegivel })}
                      style={{
                        fontSize: 10, padding: '2px 6px', borderRadius: 999, border: 'none', cursor: 'pointer',
                        background: d.elegivel ? '#dcfce7' : '#f3f4f6',
                        color: d.elegivel ? '#15803d' : '#6b7280', fontWeight: 600,
                      }}
                    >
                      {d.elegivel ? 'sim' : 'não'}
                    </button>
                  </td>
                  <td style={{ textAlign: 'right', color: d.credito.total > 0 ? 'var(--teal)' : 'var(--gray-mid)', fontWeight: d.credito.total > 0 ? 700 : 400 }}>
                    {fmtBRL(d.credito.total)}
                  </td>
                  <td>
                    <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 999, background: '#f3f4f6', color: STATUS_COR[d.status] || '#6b7280', fontWeight: 600 }}>
                      {d.status}
                    </span>
                  </td>
                  <td>
                    <button
                      style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 13 }}
                      onClick={() => deleteDespesa.mutate(d.id)}
                    >×</button>
                  </td>
                </tr>
              ))}
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
            <select
              value={novaCat}
              onChange={e => setNovaCat(e.target.value)}
              style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, fontFamily: 'Archivo, sans-serif', color: 'var(--dark)', background: '#fff' }}
            >
              <option value="">—</option>
              {allCats.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
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
