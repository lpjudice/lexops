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

const TABS: { key: Tab; label: string }[] = [
  { key: 'clientes', label: 'Clientes' },
  { key: 'emissoes', label: 'Emissões' },
  { key: 'debentures', label: 'Debêntures' },
  { key: 'empreendimentos', label: 'Empreendimentos' },
  { key: 'imobiliario', label: 'Imobiliário' },
  { key: 'fundos-ref', label: 'Fundos Ref.' },
  { key: 'fundos', label: 'Fundos Posição' },
  { key: 'estrategias', label: 'Estratégias' },
]

export default function CarteiraPage() {
  const [tab, setTab] = useState<Tab>('debentures')
  const [modal, setModal] = useState<string | null>(null)
  const [form, setForm] = useState<Record<string, any>>({})
  const qc = useQueryClient()

  const inp = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }))
  const closeModal = () => { setModal(null); setForm({}) }

  // ── queries ──────────────────────────────────────────────────────
  const { data: dash } = useQuery({
    queryKey: ['carteira-dash'],
    queryFn: () => api.get('/api/carteira/dashboard').then(r => r.data),
  })
  const { data: clientesRes } = useQuery({
    queryKey: ['carteira-clientes'],
    queryFn: () => api.get('/api/carteira/clientes').then(r => r.data),
  })
  const { data: emissoesRef = [] } = useQuery({
    queryKey: ['carteira-emissoes'],
    queryFn: () => api.get('/api/carteira/emissoes').then(r => r.data),
  })
  const { data: debenturesRes } = useQuery({
    queryKey: ['carteira-debentures'],
    queryFn: () => api.get('/api/carteira/debentures').then(r => r.data),
  })
  const { data: empreendimentosRef = [] } = useQuery({
    queryKey: ['carteira-empreendimentos'],
    queryFn: () => api.get('/api/carteira/empreendimentos').then(r => r.data),
  })
  const { data: imobiliarioRes } = useQuery({
    queryKey: ['carteira-imobiliario'],
    queryFn: () => api.get('/api/carteira/imobiliario').then(r => r.data),
  })
  const { data: fundosRefRes = [] } = useQuery({
    queryKey: ['carteira-fundos-ref'],
    queryFn: () => api.get('/api/carteira/fundos-referencia').then(r => r.data),
  })
  const { data: fundosRes } = useQuery({
    queryKey: ['carteira-fundos'],
    queryFn: () => api.get('/api/carteira/fundos').then(r => r.data),
  })
  const { data: estrategiasRes } = useQuery({
    queryKey: ['carteira-estrategias'],
    queryFn: () => api.get('/api/carteira/estrategias').then(r => r.data),
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

  const salvarCliente = mk('/api/carteira/clientes', ['carteira-clientes', 'carteira-dash'], ['usuario_cliente_id', 'pro_labore_valor', 'percentual_sucesso_geral'])
  const salvarEmissao = mk('/api/carteira/emissoes', ['carteira-emissoes'], ['numero_emissao'])
  const salvarDebenture = mk('/api/carteira/debentures', ['carteira-debentures', 'carteira-dash'], ['cliente_id', 'emissao_id', 'valor_aplicado', 'valor_atual_estimado', 'percentual_sucesso_honor', 'numero_debentures'])
  const salvarEmpreendimento = mk('/api/carteira/empreendimentos', ['carteira-empreendimentos'])
  const salvarImobiliario = mk('/api/carteira/imobiliario', ['carteira-imobiliario', 'carteira-dash'], ['cliente_id', 'empreendimento_id', 'valor_total_compromissado', 'valor_efetivamente_investido', 'percentual_participacao', 'percentual_sucesso_honorario'])
  const salvarFundoRef = mk('/api/carteira/fundos-referencia', ['carteira-fundos-ref'])
  const salvarFundo = mk('/api/carteira/fundos', ['carteira-fundos', 'carteira-dash'], ['cliente_id', 'fundo_id', 'valor_aplicado', 'valor_atual_estimado', 'percentual_sucesso_honor'])
  const salvarEstrategia = mk('/api/carteira/estrategias', ['carteira-estrategias'])

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

      {/* Tab Bar */}
      <div className={cs.tabBar}>
        {TABS.map(t => (
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
          {addBtn('Novo Cliente', () => { setForm({ pro_labore_tipo: 'fixo', tipo_pessoa: 'PF' }); setModal('cliente') })}
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>#</th><th>ID Sistema</th><th>Tipo PL</th>
                  <th>Pro-Labore</th><th>% Sucesso</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {clientes.length === 0 ? emptyRow(6) : clientes.map((c: any) => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td>{c.usuario_cliente_id}</td>
                    <td>{c.pro_labore_tipo}</td>
                    <td>{brl(c.pro_labore_valor)}</td>
                    <td>{pct(c.percentual_sucesso_geral)}</td>
                    <td>{statusBadge(c.ativo)}</td>
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
                  <th>#</th><th>Cautela</th><th>Emissão</th><th>Cliente</th>
                  <th>Aplicado</th><th>Atual</th><th>Status</th><th>Honorários</th>
                </tr>
              </thead>
              <tbody>
                {debentures.length === 0 ? emptyRow(8) : debentures.map((d: any) => (
                  <tr key={d.id}>
                    <td>{d.id}</td>
                    <td><strong>{d.numero_cautela}</strong></td>
                    <td>{emissaoNome(d.emissao_id)}</td>
                    <td>#{d.cliente_id}</td>
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
                  <th>#</th><th>Empreendimento</th><th>Cliente</th>
                  <th>Comprometido</th><th>Investido</th><th>% Part.</th><th>Honorários</th>
                </tr>
              </thead>
              <tbody>
                {imobiliario.length === 0 ? emptyRow(7) : imobiliario.map((i: any) => (
                  <tr key={i.id}>
                    <td>{i.id}</td>
                    <td>{empreendimentoNome(i.empreendimento_id)}</td>
                    <td>#{i.cliente_id}</td>
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
                  <th>#</th><th>Fundo</th><th>Cliente</th>
                  <th>Aplicado</th><th>Atual</th><th>Data Aplicação</th><th>Honorários</th>
                </tr>
              </thead>
              <tbody>
                {fundos.length === 0 ? emptyRow(7) : fundos.map((f: any) => (
                  <tr key={f.id}>
                    <td>{f.id}</td>
                    <td>{fundoNome(f.fundo_id)}</td>
                    <td>#{f.cliente_id}</td>
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

      {modal === 'cliente' && (
        <Modal title="Novo Cliente na Carteira" onClose={closeModal}>
          <Field label="ID do Cliente no Sistema *">
            <Inp k="usuario_cliente_id" type="number" placeholder="ID numérico do cliente" />
          </Field>
          <Field label="Tipo Pessoa">
            <Sel k="tipo_pessoa" options={[{ value: 'PF', label: 'PF — Pessoa Física' }, { value: 'PJ', label: 'PJ — Pessoa Jurídica' }]} />
          </Field>
          <Field label="Tipo Pro-Labore">
            <Sel k="pro_labore_tipo" options={[{ value: 'fixo', label: 'Fixo (mensal)' }, { value: 'percentual', label: 'Percentual sobre carteira' }]} />
          </Field>
          <Field label="Valor Pro-Labore (R$)">
            <Inp k="pro_labore_valor" type="number" placeholder="Ex: 5000" />
          </Field>
          <Field label="% Sucesso Geral">
            <Inp k="percentual_sucesso_geral" type="number" placeholder="Ex: 20" />
          </Field>
          <Field label="Observações">
            <textarea className={styles.input} rows={3} value={form.observacoes ?? ''} onChange={e => inp('observacoes', e.target.value)} />
          </Field>
          <button className={styles.btnPrimary} onClick={() => salvarCliente.mutate()} disabled={salvarCliente.isPending}>
            {salvarCliente.isPending ? 'Salvando...' : 'Salvar'}
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
            <Sel k="cliente_id" options={clientes.map((c: any) => ({ value: c.id, label: `#${c.id} — ID sistema ${c.usuario_cliente_id}` }))} />
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
            <Sel k="cliente_id" options={clientes.map((c: any) => ({ value: c.id, label: `#${c.id} — ID sistema ${c.usuario_cliente_id}` }))} />
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
            <Sel k="cliente_id" options={clientes.map((c: any) => ({ value: c.id, label: `#${c.id} — ID sistema ${c.usuario_cliente_id}` }))} />
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
