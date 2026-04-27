import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { processosApi } from '../api/processos'
import { clientesApi } from '../api/clientes'
import { andamentosApi } from '../api/andamentos'
import type { ProcessoCreate, EstadoProcesso, FaseProcesso, StatusProcesso, PoloProcesso, SistemaJuridico, GrauProcesso, ProcessoClienteIn } from '../api/processos'
import ClienteCombobox from '../components/ClienteCombobox'
import ProcessoChat from '../components/ProcessoChat'
import AndamentosSection from '../components/AndamentosSection'
import SincronizarModal from '../components/SincronizarModal'
import styles from './Page.module.css'
import ps from './ProcessosPage.module.css'

const ESTADOS: EstadoProcesso[] = ['ES', 'SP', 'AM', 'RJ', 'outro']
const TRIBUNAIS: Record<string, string> = { ES: 'TJES', SP: 'TJSP', AM: 'TJAM', RJ: 'TJRJ', outro: '' }
const STATUS_OPTS: StatusProcesso[] = ['ativo', 'suspenso', 'arquivado', 'encerrado']
const FASES: FaseProcesso[] = ['conhecimento', 'recursal', 'execucao', 'cumprimento_sentenca', 'outro']
const POLOS: PoloProcesso[] = [
  'autor', 'reu', 'litisconsorte', 'assistente', 'opoente', 'interveniente',
  'perito', 'avaliador', 'interessado',
  'embargante', 'embargado', 'apelante', 'apelado',
  'agravante', 'agravado', 'recorrente', 'recorrido',
  'outro',
]
const POLO_LABEL: Record<PoloProcesso, string> = {
  autor: 'Autor', reu: 'Réu', litisconsorte: 'Litisconsorte', assistente: 'Assistente',
  opoente: 'Opoente', interveniente: 'Interveniente', perito: 'Perito',
  avaliador: 'Avaliador', interessado: 'Interessado',
  embargante: 'Embargante', embargado: 'Embargado',
  apelante: 'Apelante', apelado: 'Apelado',
  agravante: 'Agravante', agravado: 'Agravado',
  recorrente: 'Recorrente', recorrido: 'Recorrido',
  outro: 'Outro',
}
const SISTEMA_OPTS: Array<{ value: SistemaJuridico; label: string }> = [
  { value: 'esaj', label: 'eSAJ' },
  { value: 'projudi', label: 'Projudi' },
  { value: 'ejud', label: 'eJUD' },
  { value: 'pje', label: 'PJe' },
]
const GRAU_OPTS: Array<{ value: GrauProcesso; label: string }> = [
  { value: '1grau', label: '1º Grau' },
  { value: '2grau', label: '2º Grau' },
  { value: 'stj', label: 'STJ' },
  { value: 'stf', label: 'STF' },
  { value: 'outro', label: 'Outro' },
]

const EMPTY: ProcessoCreate = {
  numero_cnj: '', cliente_id: '', vara: '', comarca: '',
  estado: 'ES', tribunal: 'TJES', materia: '', fase: undefined, status: 'ativo', objeto: '',
  serventia: '', foro: '', sistema_juridico: null, grau: null, grau_texto: '',
  clientes_litisconsorcio: [],
}

function maskCNJ(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 20)
  if (d.length <= 7) return d
  if (d.length <= 9) return `${d.slice(0,7)}-${d.slice(7)}`
  if (d.length <= 13) return `${d.slice(0,7)}-${d.slice(7,9)}.${d.slice(9)}`
  if (d.length <= 14) return `${d.slice(0,7)}-${d.slice(7,9)}.${d.slice(9,13)}.${d.slice(13)}`
  if (d.length <= 16) return `${d.slice(0,7)}-${d.slice(7,9)}.${d.slice(9,13)}.${d.slice(13,14)}.${d.slice(14)}`
  return `${d.slice(0,7)}-${d.slice(7,9)}.${d.slice(9,13)}.${d.slice(13,14)}.${d.slice(14,16)}.${d.slice(16)}`
}

export default function ProcessosPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ProcessoCreate>(EMPTY)
  const [erro, setErro] = useState<string | null>(null)
  const [expandido, setExpandido] = useState<string | null>(null)
  const [editando, setEditando] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Partial<ProcessoCreate>>({})
  const [showSyncModal, setShowSyncModal] = useState(false)
  const [detalheAberto, setDetalheAberto] = useState<string | null>(null)
  // Litisconsórcio state for create form
  const [createLitis, setCreateLitis] = useState<ProcessoClienteIn[]>([])
  // Litisconsórcio state for edit form
  const [editLitis, setEditLitis] = useState<ProcessoClienteIn[]>([])
  // Filters
  const [filtroTribunal, setFiltroTribunal] = useState('')
  const [filtroUltMov, setFiltroUltMov] = useState<'todos' | '7d' | '30d' | '90d' | 'sem'>('todos')
  const [filtroPolo, setFiltroPolo] = useState('')
  const [ordemAlfa, setOrdemAlfa] = useState(false)

  const { data: processos = [], isLoading } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const { data: jusbrSession } = useQuery({
    queryKey: ['jusbr-session'],
    queryFn: () => andamentosApi.obterSessaoJusBR(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const criar = useMutation({
    mutationFn: processosApi.criar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['processos'] })
      setShowForm(false)
      setForm(EMPTY)
      setCreateLitis([])
      setErro(null)
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detail ?? 'Erro ao salvar processo')
    },
  })

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ProcessoCreate> }) =>
      processosApi.atualizar(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['processos'] })
      setEditando(null)
      setEditLitis([])
    },
  })

  const deletar = useMutation({
    mutationFn: (id: string) => processosApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['processos'] }),
  })

  const criarCliente = async (raw: string): Promise<string> => {
    const [nome, tipo] = raw.split('|')
    const c = await clientesApi.criar({ nome, tipo: (tipo as 'PF' | 'PJ') ?? 'PF', incompleto: true })
    qc.invalidateQueries({ queryKey: ['clientes'] })
    return c.id
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setErro(null)
    if (!form.cliente_id) { setErro('Selecione ou crie um cliente'); return }
    if (!form.numero_cnj) { setErro('Número CNJ é obrigatório'); return }
    criar.mutate({ ...form, clientes_litisconsorcio: createLitis.filter((cl) => cl.cliente_id) })
  }

  const handleEstado = (estado: EstadoProcesso) =>
    setForm({ ...form, estado, tribunal: TRIBUNAIS[estado] || '' })

  const clienteNome = (id: string) => clientes.find((c) => c.id === id)?.nome ?? '—'

  const tribunaisUnicos = useMemo(() => {
    const set = new Set(processos.map((p) => p.tribunal).filter(Boolean) as string[])
    return Array.from(set).sort()
  }, [processos])

  const processosFiltrados = useMemo(() => {
    let lista = [...processos]
    if (filtroTribunal) lista = lista.filter((p) => p.tribunal === filtroTribunal)
    if (filtroPolo) lista = lista.filter((p) => p.polo === filtroPolo)
    if (filtroUltMov === 'sem') {
      lista = lista.filter((p) => !p.ultimo_andamento_data)
    } else if (filtroUltMov !== 'todos') {
      const dias = { '7d': 7, '30d': 30, '90d': 90 }[filtroUltMov]!
      const limite = new Date()
      limite.setDate(limite.getDate() - dias)
      lista = lista.filter(
        (p) => p.ultimo_andamento_data && new Date(p.ultimo_andamento_data) >= limite
      )
    }
    if (ordemAlfa) lista.sort((a, b) => a.numero_cnj.localeCompare(b.numero_cnj))
    return lista
  }, [processos, filtroTribunal, filtroUltMov, filtroPolo, ordemAlfa])

  const jusbrStatusLabel = useMemo(() => {
    if (!jusbrSession?.active) return 'jus.br: sessão inativa'
    const expiry = jusbrSession.expires_at
      ? new Date(jusbrSession.expires_at).toLocaleString('pt-BR', {
          day: '2-digit',
          month: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        })
      : 'sem expiração detectada'
    return jusbrSession.has_refresh_token
      ? `jus.br: ativo até ${expiry} • refresh ok`
      : `jus.br: ativo até ${expiry} • sem refresh`
  }, [jusbrSession])

  // Litisconsórcio helpers
  const addLitis = (forEdit: boolean) => {
    if (forEdit) setEditLitis((prev) => [...prev, { cliente_id: '', polo: null, principal: false }])
    else setCreateLitis((prev) => [...prev, { cliente_id: '', polo: null, principal: false }])
  }
  const updateLitis = (i: number, field: keyof ProcessoClienteIn, val: unknown, forEdit: boolean) => {
    const setter = forEdit ? setEditLitis : setCreateLitis
    setter((prev) => prev.map((cl, idx) => idx === i ? { ...cl, [field]: val } : cl))
  }
  const removeLitis = (i: number, forEdit: boolean) => {
    const setter = forEdit ? setEditLitis : setCreateLitis
    setter((prev) => prev.filter((_, idx) => idx !== i))
  }


  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Processos</h1>
        <div className={ps.headerActions}>
          <span
            className={`${ps.jusbrStatus} ${jusbrSession?.active ? ps.jusbrStatusAtivo : ps.jusbrStatusInativo}`}
            title={jusbrSession?.active
              ? 'Sessão do jus.br disponível para sincronização'
              : 'Sessão do jus.br indisponível; atualize antes de usar a sincronização autenticada'}
          >
            {jusbrStatusLabel}
          </span>
          <button className={styles.btnTable} onClick={() => setShowSyncModal(true)}>
            ⟳ Sincronizar andamentos
          </button>
          <button className={styles.btnPrimary} onClick={() => { setShowForm(!showForm); setErro(null) }}>
            {showForm ? 'Cancelar' : '+ Novo Processo'}
          </button>
        </div>
      </div>

      {showSyncModal && (
        <SincronizarModal processos={processos} onClose={() => setShowSyncModal(false)} />
      )}

      {showForm && (
        <form onSubmit={handleSubmit} className={styles.form}>
          {erro && <div className={ps.formErro}>{erro}</div>}

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Cliente *</label>
            <ClienteCombobox
              value={form.cliente_id}
              onChange={(id) => setForm({ ...form, cliente_id: id })}
              clientes={clientes}
              onCreateCliente={criarCliente}
            />
          </div>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Nº CNJ *</label>
            <input
              className={styles.input}
              placeholder="0000000-00.0000.0.00.0000"
              value={form.numero_cnj}
              onChange={(e) => setForm({ ...form, numero_cnj: maskCNJ(e.target.value) })}
            />
          </div>

          <div className={ps.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Estado</label>
              <select className={styles.input} value={form.estado}
                onChange={(e) => handleEstado(e.target.value as EstadoProcesso)}>
                {ESTADOS.map((e) => <option key={e} value={e}>{e}</option>)}
              </select>
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Tribunal</label>
              <input className={styles.input} value={form.tribunal}
                onChange={(e) => setForm({ ...form, tribunal: e.target.value })} />
            </div>
          </div>

          <div className={ps.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Vara (nº)</label>
              <input className={styles.input} placeholder="Ex: 3" value={form.vara ?? ''}
                onChange={(e) => setForm({ ...form, vara: e.target.value })} />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Serventia</label>
              <input className={styles.input} placeholder="Fazenda Pública, Cível..." value={form.serventia ?? ''}
                onChange={(e) => setForm({ ...form, serventia: e.target.value })} />
            </div>
          </div>

          <div className={ps.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Comarca</label>
              <input className={styles.input} value={form.comarca ?? ''}
                onChange={(e) => setForm({ ...form, comarca: e.target.value })} />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Foro</label>
              <input className={styles.input} placeholder="Central, Hely Lopes Meirelles..." value={form.foro ?? ''}
                onChange={(e) => setForm({ ...form, foro: e.target.value })} />
            </div>
          </div>

          <div className={ps.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Sistema jurídico</label>
              <select className={styles.input} value={form.sistema_juridico ?? ''}
                onChange={(e) => setForm({ ...form, sistema_juridico: (e.target.value as SistemaJuridico) || null })}>
                <option value="">Não informado</option>
                {SISTEMA_OPTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Grau</label>
              <select className={styles.input} value={form.grau ?? ''}
                onChange={(e) => setForm({ ...form, grau: (e.target.value as GrauProcesso) || null, grau_texto: '' })}>
                <option value="">Não informado</option>
                {GRAU_OPTS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
              </select>
            </div>
          </div>
          {form.grau === 'outro' && (
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Instância (descrição)</label>
              <input className={styles.input} placeholder="Descreva..." value={form.grau_texto ?? ''}
                onChange={(e) => setForm({ ...form, grau_texto: e.target.value })} />
            </div>
          )}

          <div className={ps.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Fase</label>
              <select className={styles.input} value={form.fase ?? ''}
                onChange={(e) => setForm({ ...form, fase: (e.target.value as FaseProcesso) || undefined })}>
                <option value="">—</option>
                {FASES.map((f) => <option key={f} value={f}>{f.replace('_', ' ')}</option>)}
              </select>
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Status</label>
              <select className={styles.input} value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value as StatusProcesso })}>
                {STATUS_OPTS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Matéria</label>
            <input className={styles.input} value={form.materia}
              onChange={(e) => setForm({ ...form, materia: e.target.value })} />
          </div>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Polo do cliente</label>
            <div className={ps.poloChips}>
              {POLOS.map((polo) => (
                <button key={polo} type="button"
                  className={`${ps.poloChip} ${form.polo === polo ? ps.poloChipActive : ''}`}
                  onClick={() => setForm({ ...form, polo: form.polo === polo ? undefined : polo })}>
                  {POLO_LABEL[polo]}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Objeto</label>
            <textarea className={styles.input} rows={2} value={form.objeto}
              onChange={(e) => setForm({ ...form, objeto: e.target.value })} />
          </div>

          {/* Litisconsórcio */}
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Litisconsortes</label>
            {createLitis.map((cl, i) => (
              <div key={i} className={ps.litisRow}>
                <ClienteCombobox
                  value={cl.cliente_id}
                  onChange={(v) => updateLitis(i, 'cliente_id', v, false)}
                  clientes={clientes}
                  onCreateCliente={criarCliente}
                />
                <select className={styles.input} value={cl.polo ?? ''}
                  onChange={(e) => updateLitis(i, 'polo', (e.target.value as PoloProcesso) || null, false)}>
                  <option value="">Polo...</option>
                  {POLOS.map((p) => <option key={p} value={p}>{POLO_LABEL[p]}</option>)}
                </select>
                <button type="button" className={styles.btnDanger} onClick={() => removeLitis(i, false)}>×</button>
              </div>
            ))}
            <button type="button" className={styles.btnTable} onClick={() => addLitis(false)}>
              + Litisconsorte
            </button>
          </div>

          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {/* Filtros */}
      {processos.length > 0 && (
        <div className={ps.filtros}>
          <select className={ps.filtroSelect} value={filtroTribunal} onChange={(e) => setFiltroTribunal(e.target.value)}>
            <option value="">Todos os tribunais</option>
            {tribunaisUnicos.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className={ps.filtroSelect} value={filtroUltMov} onChange={(e) => setFiltroUltMov(e.target.value as typeof filtroUltMov)}>
            <option value="todos">Qualquer movimentação</option>
            <option value="7d">Últimos 7 dias</option>
            <option value="30d">Últimos 30 dias</option>
            <option value="90d">Últimos 90 dias</option>
            <option value="sem">Sem movimentação</option>
          </select>
          <select className={ps.filtroSelect} value={filtroPolo} onChange={(e) => setFiltroPolo(e.target.value)}>
            <option value="">Qualquer polo</option>
            {POLOS.map((p) => <option key={p} value={p}>{POLO_LABEL[p]}</option>)}
          </select>
          <button
            className={`${ps.filtroBtn} ${ordemAlfa ? ps.filtroBtnActive : ''}`}
            onClick={() => setOrdemAlfa((o) => !o)}
          >
            A–Z
          </button>
        </div>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : processos.length === 0 ? (
        <p className={styles.empty}>Nenhum processo cadastrado.</p>
      ) : processosFiltrados.length === 0 ? (
        <p className={styles.empty}>Nenhum processo com os filtros selecionados.</p>
      ) : (
        <div className={ps.lista}>
          {processosFiltrados.map((p) => (
            <div key={p.id} className={ps.card}>
              {/* Header do card */}
              <div className={ps.cardHeader}>
                <div
                  className={ps.cardInfo}
                  style={{ cursor: 'pointer' }}
                  title="Clique para ver detalhes"
                  onClick={() => setDetalheAberto(detalheAberto === p.id ? null : p.id)}
                >
                  <code className={ps.cnj}>{p.numero_cnj}</code>
                  <span className={ps.clienteNome}>{clienteNome(p.cliente_id)}</span>
                  {p.polo && <span className={ps.poloTag}>{POLO_LABEL[p.polo as PoloProcesso]}</span>}
                  {(p.clientes_litisconsorcio ?? []).length > 0 && (
                    <span className={ps.litisTag}>
                      +{(p.clientes_litisconsorcio ?? []).length} litisconsorte{(p.clientes_litisconsorcio ?? []).length > 1 ? 's' : ''}
                    </span>
                  )}
                  {p.tribunal && <span className={ps.chip}>{p.tribunal}</span>}
                  {p.materia && <span className={ps.materia}>{p.materia}</span>}
                  <span className={`${styles.badge} ${styles[`status_${p.status}`]}`}>{p.status}</span>
                  {p.ultimo_andamento_data && (
                    <span className={ps.ultimoAndamento} title={p.ultimo_andamento_desc ?? ''}>
                      {p.ultimo_andamento_data.split('-').reverse().join('/')}
                    </span>
                  )}
                </div>
                <div className={ps.cardActions}>
                  <button className={styles.btnTable}
                    onClick={() => {
                      setExpandido(expandido === p.id ? null : p.id)
                      setEditando(null)
                    }}>
                    {expandido === p.id ? '▲ Fechar' : '▼ Docs / Chat / Andamentos'}
                    {!expandido && (p.andamentos_nao_lidos ?? 0) > 0 && (
                      <span className={ps.naoLidosBadge}>{p.andamentos_nao_lidos}</span>
                    )}
                  </button>
                  <button className={styles.btnTable}
                    onClick={() => {
                      setEditando(editando === p.id ? null : p.id)
                      setEditForm({ numero_cnj: p.numero_cnj, cliente_id: p.cliente_id, vara: p.vara, comarca: p.comarca, estado: p.estado, tribunal: p.tribunal, materia: p.materia, fase: p.fase, status: p.status, objeto: p.objeto, polo: p.polo, serventia: p.serventia, foro: p.foro, sistema_juridico: p.sistema_juridico, grau: p.grau, grau_texto: p.grau_texto })
                      setEditLitis((p.clientes_litisconsorcio ?? []).map((cl) => ({ cliente_id: cl.cliente_id, polo: (cl.polo as PoloProcesso | null) ?? null, principal: cl.principal ?? false })))
                      setExpandido(null)
                    }}>
                    {editando === p.id ? 'Cancelar' : 'Editar'}
                  </button>
                  <button className={styles.btnDanger}
                    onClick={() => { if (confirm(`Remover ${p.numero_cnj}?`)) deletar.mutate(p.id) }}>
                    ×
                  </button>
                </div>
              </div>

              {/* Painel de detalhes do processo */}
              {detalheAberto === p.id && (
                <div className={ps.infoPanel}>
                  {(p.vara || p.serventia) && (
                    <div className={ps.infoField}>
                      <span className={ps.infoLabel}>Vara / Serventia</span>
                      <span className={ps.infoValue}>
                        {[p.vara ? `${p.vara}ª Vara` : null, p.serventia].filter(Boolean).join(' — ')}
                      </span>
                    </div>
                  )}
                  {(p.comarca || p.foro) && (
                    <div className={ps.infoField}>
                      <span className={ps.infoLabel}>Comarca / Foro</span>
                      <span className={ps.infoValue}>
                        {[p.comarca, p.foro].filter(Boolean).join(' — Foro ')}
                      </span>
                    </div>
                  )}
                  {p.sistema_juridico && (
                    <div className={ps.infoField}>
                      <span className={ps.infoLabel}>Sistema</span>
                      <span className={ps.infoValue}>
                        {SISTEMA_OPTS.find((s) => s.value === p.sistema_juridico)?.label ?? p.sistema_juridico}
                      </span>
                    </div>
                  )}
                  {p.grau && (
                    <div className={ps.infoField}>
                      <span className={ps.infoLabel}>Grau</span>
                      <span className={ps.infoValue}>
                        {GRAU_OPTS.find((g) => g.value === p.grau)?.label ?? p.grau}
                        {p.grau === 'outro' && p.grau_texto ? ` — ${p.grau_texto}` : ''}
                      </span>
                    </div>
                  )}
                  {p.fase && (
                    <div className={ps.infoField}>
                      <span className={ps.infoLabel}>Fase</span>
                      <span className={ps.infoValue}>{p.fase.replace('_', ' ')}</span>
                    </div>
                  )}
                  {p.objeto && (
                    <div className={`${ps.infoField} ${ps.infoFieldFull}`}>
                      <span className={ps.infoLabel}>Objeto</span>
                      <span className={ps.infoValue}>{p.objeto}</span>
                    </div>
                  )}
                  {(p.clientes_litisconsorcio ?? []).length > 0 && (
                    <div className={`${ps.infoField} ${ps.infoFieldFull}`}>
                      <span className={ps.infoLabel}>Litisconsortes</span>
                      <div className={ps.litisChips}>
                        {(p.clientes_litisconsorcio ?? []).map((cl) => (
                          <span key={cl.cliente_id} className={ps.litisChip}>
                            {cl.nome}{cl.polo ? ` · ${POLO_LABEL[cl.polo as PoloProcesso] ?? cl.polo}` : ''}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Painel de edição */}
              {editando === p.id && (
                <div className={ps.editPanel}>
                  <div className={ps.twoCol}>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Nº CNJ</label>
                      <input className={styles.input} value={editForm.numero_cnj ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, numero_cnj: maskCNJ(e.target.value) })} />
                    </div>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Status</label>
                      <select className={styles.input} value={editForm.status}
                        onChange={(e) => setEditForm({ ...editForm, status: e.target.value as StatusProcesso })}>
                        {STATUS_OPTS.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                  </div>
                  <div className={ps.twoCol}>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Tribunal</label>
                      <input className={styles.input} value={editForm.tribunal ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, tribunal: e.target.value })} />
                    </div>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Vara</label>
                      <input className={styles.input} value={editForm.vara ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, vara: e.target.value })} />
                    </div>
                  </div>
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Matéria</label>
                    <input className={styles.input} value={editForm.materia ?? ''}
                      onChange={(e) => setEditForm({ ...editForm, materia: e.target.value })} />
                  </div>
                  <div className={ps.twoCol}>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Serventia</label>
                      <input className={styles.input} placeholder="Fazenda Pública, Cível..." value={editForm.serventia ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, serventia: e.target.value })} />
                    </div>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Foro</label>
                      <input className={styles.input} placeholder="Central, Hely Lopes..." value={editForm.foro ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, foro: e.target.value })} />
                    </div>
                  </div>
                  <div className={ps.twoCol}>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Sistema jurídico</label>
                      <select className={styles.input} value={editForm.sistema_juridico ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, sistema_juridico: (e.target.value as SistemaJuridico) || null })}>
                        <option value="">Não informado</option>
                        {SISTEMA_OPTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </select>
                    </div>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Grau</label>
                      <select className={styles.input} value={editForm.grau ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, grau: (e.target.value as GrauProcesso) || null, grau_texto: '' })}>
                        <option value="">Não informado</option>
                        {GRAU_OPTS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
                      </select>
                    </div>
                  </div>
                  {editForm.grau === 'outro' && (
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Instância</label>
                      <input className={styles.input} value={editForm.grau_texto ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, grau_texto: e.target.value })} />
                    </div>
                  )}
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Polo do cliente</label>
                    <div className={ps.poloChips}>
                      {POLOS.map((polo) => (
                        <button key={polo} type="button"
                          className={`${ps.poloChip} ${editForm.polo === polo ? ps.poloChipActive : ''}`}
                          onClick={() => setEditForm({ ...editForm, polo: editForm.polo === polo ? undefined : polo })}>
                          {POLO_LABEL[polo]}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Fase</label>
                    <select className={styles.input} value={editForm.fase ?? ''}
                      onChange={(e) => setEditForm({ ...editForm, fase: (e.target.value as FaseProcesso) || undefined })}>
                      <option value="">—</option>
                      {FASES.map((f) => <option key={f} value={f}>{f.replace('_', ' ')}</option>)}
                    </select>
                  </div>
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Objeto</label>
                    <textarea className={styles.input} rows={2} value={editForm.objeto ?? ''}
                      onChange={(e) => setEditForm({ ...editForm, objeto: e.target.value })} />
                  </div>
                  {/* Litisconsórcio edit */}
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Litisconsortes</label>
                    {editLitis.map((cl, i) => (
                      <div key={i} className={ps.litisRow}>
                        <ClienteCombobox
                          value={cl.cliente_id}
                          onChange={(v) => updateLitis(i, 'cliente_id', v, true)}
                          clientes={clientes}
                          onCreateCliente={criarCliente}
                        />
                        <select className={styles.input} value={cl.polo ?? ''}
                          onChange={(e) => updateLitis(i, 'polo', (e.target.value as PoloProcesso) || null, true)}>
                          <option value="">Polo...</option>
                          {POLOS.map((pol) => <option key={pol} value={pol}>{POLO_LABEL[pol]}</option>)}
                        </select>
                        <button type="button" className={styles.btnDanger} onClick={() => removeLitis(i, true)}>×</button>
                      </div>
                    ))}
                    <button type="button" className={styles.btnTable} onClick={() => addLitis(true)}>
                      + Litisconsorte
                    </button>
                  </div>
                  <button className={styles.btnPrimary} disabled={atualizar.isPending}
                    onClick={() => atualizar.mutate({ id: p.id, data: { ...editForm, clientes_litisconsorcio: editLitis.filter((cl) => cl.cliente_id) } })}>
                    {atualizar.isPending ? 'Salvando...' : 'Salvar alterações'}
                  </button>
                </div>
              )}

              {/* Painel de docs + chat + andamentos */}
              {expandido === p.id && (
                <div className={ps.docsPanel}>
                  <ProcessoChat processoId={p.id} clienteId={p.cliente_id} processoNome={p.numero_cnj} />
                  <AndamentosSection
                    processoId={p.id}
                    tribunal={p.tribunal}
                    ultimoAndamentoData={p.ultimo_andamento_data}
                    ultimoCheck={p.ultimo_check}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
