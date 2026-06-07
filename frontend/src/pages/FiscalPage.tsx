import React, { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fiscalApi } from '../api/fiscal'
import type { NotaFiscalOut, EmitirNFSeIn, StatusNF } from '../api/fiscal'
import { clientesApi } from '../api/clientes'
import type { Cliente } from '../api/clientes'
import { contratosApi } from '../api/contratos'
import { processosApi } from '../api/processos'
import { configFiscalApi } from '../api/configFiscal'
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
}
const STATUS_CLASS: Record<StatusNF, string> = {
  emitida: cs.badgeEmitida, rascunho: cs.badgeRascunho,
  cancelada: cs.badgeCancelada, erro: cs.badgeErro,
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
}: {
  value: string
  onSelect: (c: Cliente | null, nomeRaw: string) => void
  label?: string
  placeholder?: string
}) {
  const [q, setQ] = useState(value)
  const [aberto, setAberto] = useState(false)

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: clientesApi.listar,
    staleTime: 60_000,
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
      {aberto && filtrados.length > 0 && (
        <ul className={cs.dropdown}>
          {filtrados.map((c) => (
            <li key={c.id} className={cs.dropdownItem}
              onMouseDown={() => { setQ(c.nome); setAberto(false); onSelect(c, c.nome) }}>
              <span className={cs.dropdownNome}>{c.nome}</span>
              {c.cpf_cnpj && <span className={cs.dropdownDoc}>{c.cpf_cnpj}</span>}
              {c.email && <span className={cs.dropdownEmail}>{c.email}</span>}
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
    onSuccess: (nf) => { qc.invalidateQueries({ queryKey: ['notas-fiscais'] }); onSucesso(nf) },
    onError: (err: any) => {
      const d = err?.response?.data?.detail
      if (typeof d === 'object') setErro(`[${d.codigo ?? '?'}] ${d.detalhe ?? d.message}`)
      else setErro(String(d ?? err?.message ?? 'Erro desconhecido'))
    },
  })

  function set<K extends keyof EmitirNFSeIn>(k: K, v: EmitirNFSeIn[K]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  const criarClienteMut = useMutation({
    mutationFn: () => clientesApi.criar({
      nome: form.tomador_nome,
      tipo: (form.tomador_cpf_cnpj || '').replace(/\D/g, '').length === 14 ? 'PJ' : 'PF',
      cpf_cnpj: form.tomador_cpf_cnpj || undefined,
      email: form.tomador_email || undefined,
      telefone: form.tomador_telefone || undefined,
    } as any),
    onSuccess: (c: Cliente) => {
      setClienteSelecionado(c)
      set('cliente_id', c.id)
      qc.invalidateQueries({ queryKey: ['clientes'] })
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
        <div className={cs.modalTitle}>🧾 Emitir NFS-e</div>

        {temPrefill && (
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
            <ClienteSearch value={form.tomador_nome} onSelect={handleClienteSelect} />

            {/* Cliente novo → criar na hora */}
            {!clienteSelecionado && form.tomador_nome.trim().length > 2 && (
              <div className={cs.prefillBanner} style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Tomador não cadastrado.</span>
                <button type="button" className={cs.templateBtn}
                  disabled={criarClienteMut.isPending}
                  onClick={() => criarClienteMut.mutate()}>
                  {criarClienteMut.isPending ? 'Criando…' : `➕ Criar cliente "${form.tomador_nome.slice(0, 30)}"`}
                </button>
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
              <span className={cs.fieldHint} style={{ display: 'inline', marginLeft: 8 }}>
                (marque quando o tomador PJ é responsável por reter e recolher o ISS)
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

function DetalheModal({ nf, onClose }: { nf: NotaFiscalOut; onClose: () => void }) {
  const [motivo, setMotivo] = useState('')
  const [confirmando, setConfirmando] = useState(false)
  const [erroPdf, setErroPdf] = useState<string | null>(null)
  const [baixando, setBaixando] = useState(false)
  const [procIds, setProcIds] = useState<string[]>(nf.processos_ids ?? (nf.processo_id ? [nf.processo_id] : []))
  const [contrSel, setContrSel] = useState(nf.contrato_id ?? '')
  const [vincMsg, setVincMsg] = useState<string | null>(null)
  const qc = useQueryClient()
  const cancelMut = useMutation({
    mutationFn: (m: string) => fiscalApi.cancelar(nf.id, m),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notas-fiscais'] }); onClose() },
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

        {nf.status === 'emitida' && (
          <div style={{ marginTop: 16 }}>
            {!confirmando ? (
              <button className={styles.btnDanger} onClick={() => setConfirmando(true)}>
                Cancelar NFS-e
              </button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label className={cs.formLabel}>Motivo *</label>
                <input className={cs.input} placeholder="Mínimo 10 caracteres"
                  value={motivo} onChange={(e) => setMotivo(e.target.value)} />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className={styles.btnDanger}
                    disabled={motivo.length < 10 || cancelMut.isPending}
                    onClick={() => cancelMut.mutate(motivo)}>
                    {cancelMut.isPending ? 'Cancelando…' : 'Confirmar cancelamento'}
                  </button>
                  <button className={cs.btnSecondary} onClick={() => setConfirmando(false)}>Voltar</button>
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

// ─── Página principal ────────────────────────────────────────────────────────

type Filtro = 'todas' | 'emitida' | 'rascunho' | 'cancelada' | 'erro'

export default function FiscalPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [filtro, setFiltro] = useState<Filtro>('todas')
  const [emitindo, setEmitindo] = useState(false)
  const [prefill, setPrefill] = useState<Partial<EmitirNFSeIn> | undefined>()
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
  const pagoMut = useMutation({
    mutationFn: ({ id, pago }: { id: string; pago: boolean }) => fiscalApi.marcarPago(id, pago),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notas-fiscais'] }),
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
                        <button className={styles.btnTable}
                          style={nf.pago ? { background: '#dcfce7', color: '#15803d', borderColor: '#bbf7d0' } : {}}
                          onClick={() => pagoMut.mutate({ id: nf.id, pago: !nf.pago })}>
                          {nf.pago ? '✓ Pago' : 'Marcar pago'}
                        </button>
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
          onClose={() => { setEmitindo(false); setPrefill(undefined) }}
          onSucesso={(nf) => { setEmitindo(false); setPrefill(undefined); setNfEmitida(nf); qc.invalidateQueries({ queryKey: ['notas-fiscais'] }) }}
        />
      )}

      {nfEmitida && <DetalheModal nf={nfEmitida} onClose={() => setNfEmitida(null)} />}
      {nfDetalhe && !nfEmitida && <DetalheModal nf={nfDetalhe} onClose={() => setNfDetalhe(null)} />}
    </div>
  )
}
