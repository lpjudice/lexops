import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { tarefaCardsApi } from '../api/tarefaCards'
import type { StatusTarefaCard, TarefaCard } from '../api/tarefaCards'
import { tarefaProjetosApi } from '../api/tarefaProjetos'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import { useAuth } from '../contexts/AuthContext'
import ClienteCombobox from '../components/ClienteCombobox'
import ComboBox from '../components/ComboBox'
import Modal from '../components/Modal'
import ProjetoCombobox from '../components/ProjetoCombobox'
import ResponsavelComboBox from '../components/ResponsavelComboBox'
import { useFiltroMes } from '../components/useFiltroMes'
import styles from './Page.module.css'
import cs from './TarefasCardsPage.module.css'

const STATUS_OPTS: { value: StatusTarefaCard; label: string }[] = [
  { value: 'pendente', label: 'Pendente' },
  { value: 'em_andamento', label: 'Em andamento' },
  { value: 'concluido', label: 'Concluído' },
  { value: 'cancelado', label: 'Cancelado' },
]
const STATUS_FILTER: ('' | StatusTarefaCard)[] = ['', 'pendente', 'em_andamento', 'concluido', 'cancelado']
const STATUS_LABEL: Record<string, string> = {
  '': 'Todos', pendente: 'Pendente', em_andamento: 'Em andamento', concluido: 'Concluído', cancelado: 'Cancelado',
}
type FiltroVenc = '' | 'atrasadas' | 'hoje' | 'semana' | 'com_prazo' | 'sem_prazo'
const VENC_OPTS: { value: FiltroVenc; label: string }[] = [
  { value: '', label: 'Vencimento: todos' },
  { value: 'atrasadas', label: 'Atrasadas' },
  { value: 'hoje', label: 'Vence hoje' },
  { value: 'semana', label: 'Próximos 7 dias' },
  { value: 'com_prazo', label: 'Com prazo' },
  { value: 'sem_prazo', label: 'Sem prazo' },
]

function fmtData(d?: string | null) {
  if (!d) return null
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}
function diasAte(d: string) {
  const alvo = new Date(d + 'T00:00:00')
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0)
  return Math.round((alvo.getTime() - hoje.getTime()) / 86400000)
}
function vencido(d?: string | null) {
  if (!d) return false
  return diasAte(d) < 0
}

interface FormState {
  titulo: string
  descricao: string
  cliente_id: string
  processo_id: string
  projeto_id: string
  responsavel: { nome: string; email: string; id?: string | null }
  data_limite: string
  confidencial: boolean
  subtasks: string[]
}
const emptyForm: FormState = {
  titulo: '', descricao: '', cliente_id: '', processo_id: '', projeto_id: '',
  responsavel: { nome: '', email: '', id: null }, data_limite: '', confidencial: false, subtasks: [''],
}

export default function TarefasCardsPage() {
  const qc = useQueryClient()
  const { usuario, isSuperAdmin } = useAuth()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [editCard, setEditCard] = useState<TarefaCard | null>(null)

  // Filtros
  const [filtroStatus, setFiltroStatus] = useState<'' | StatusTarefaCard>('')
  const [filtroVenc, setFiltroVenc] = useState<FiltroVenc>('')
  const [filtroResp, setFiltroResp] = useState<string[]>([])
  const [filtroProjetos, setFiltroProjetos] = useState<string[]>([])
  const [filtroCriador, setFiltroCriador] = useState<string[]>([])
  const filtroMes = useFiltroMes()  // filtra por mês (prazo do card)

  const [novaSubtask, setNovaSubtask] = useState<Record<string, string>>({})
  const [editSub, setEditSub] = useState<{ id: string; texto: string } | null>(null)

  const [visao, setVisao] = useState<'ativas' | 'arquivadas'>('ativas')
  const [sortArq, setSortArq] = useState<'recente' | 'prazo' | 'titulo' | 'cliente'>('recente')

  const { data: cards = [], isLoading } = useQuery({
    queryKey: ['tarefa-cards', visao],
    queryFn: () => tarefaCardsApi.listar({ arquivada: visao === 'arquivadas' }),
  })
  const { data: projetos = [] } = useQuery({ queryKey: ['tarefa-projetos'], queryFn: tarefaProjetosApi.listar })
  const { data: clientes = [] } = useQuery({ queryKey: ['clientes'], queryFn: () => clientesApi.listar() })
  const { data: processos = [] } = useQuery({ queryKey: ['processos'], queryFn: () => processosApi.listar() })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['tarefa-cards'] })

  const criar = useMutation({
    mutationFn: tarefaCardsApi.criar,
    onSuccess: () => { invalidate(); setShowForm(false); setForm(emptyForm) },
  })
  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TarefaCard> }) => tarefaCardsApi.atualizar(id, data as never),
    onSuccess: invalidate,
  })
  const deletar = useMutation({ mutationFn: tarefaCardsApi.deletar, onSuccess: invalidate })
  const arquivar = useMutation({ mutationFn: tarefaCardsApi.arquivar, onSuccess: invalidate })
  const desarquivar = useMutation({ mutationFn: tarefaCardsApi.desarquivar, onSuccess: invalidate })
  const uploadAnexoCard = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => tarefaCardsApi.uploadAnexoCard(id, file),
    onSuccess: invalidate,
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Erro ao anexar'),
  })
  const uploadAnexoSub = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => tarefaCardsApi.uploadAnexoSubtask(id, file),
    onSuccess: invalidate,
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Erro ao anexar'),
  })
  const deletarAnexo = useMutation({ mutationFn: tarefaCardsApi.deletarAnexo, onSuccess: invalidate })
  const addSubtask = useMutation({
    mutationFn: ({ id, texto }: { id: string; texto: string }) => tarefaCardsApi.addSubtask(id, texto),
    onSuccess: invalidate,
  })
  const toggleSubtask = useMutation({
    mutationFn: ({ id, concluida }: { id: string; concluida: boolean }) => tarefaCardsApi.toggleSubtask(id, concluida),
    onSuccess: invalidate,
  })
  const editarSubtask = useMutation({
    mutationFn: ({ id, texto }: { id: string; texto: string }) => tarefaCardsApi.editarSubtask(id, texto),
    onSuccess: () => { invalidate(); setEditSub(null) },
  })
  const delSubtask = useMutation({ mutationFn: tarefaCardsApi.deletarSubtask, onSuccess: invalidate })
  const setPrazoSub = useMutation({
    mutationFn: ({ id, data }: { id: string; data: string | null }) => tarefaCardsApi.setSubtaskPrazo(id, data),
    onSuccess: invalidate,
  })
  const agendar = useMutation({
    mutationFn: tarefaCardsApi.agendarCalendario,
    onSuccess: () => { invalidate(); alert('Agendado no Google Calendar ✅') },
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Erro ao agendar'),
  })
  const solicitar = useMutation({ mutationFn: tarefaCardsApi.solicitarAcesso, onSuccess: (r) => { invalidate(); alert(r.mensagem) } })
  const conceder = useMutation({
    mutationFn: ({ cardId, usuarioId }: { cardId: string; usuarioId: string }) => tarefaCardsApi.concederAcesso(cardId, usuarioId),
    onSuccess: invalidate,
  })

  const criarProjetoRapido = async (nome: string, cor: string) => {
    const p = await tarefaProjetosApi.criar({ nome, cor })
    qc.invalidateQueries({ queryKey: ['tarefa-projetos'] })
    return p
  }
  const criarClienteRapido = async (nome: string) => {
    const c = await clientesApi.criar({ nome, tipo: 'PF', incompleto: true })
    qc.invalidateQueries({ queryKey: ['clientes'] })
    return c.id
  }

  const processoOptions = useMemo(
    () => processos.map((p) => {
      const c = clientes.find((cl) => cl.id === p.cliente_id)
      return { value: p.id, label: p.numero_cnj, sublabel: c?.nome }
    }),
    [processos, clientes],
  )

  // Responsáveis distintos presentes nos cards
  const responsaveis = useMemo(
    () => [...new Set(cards.map((c) => c.responsavel).filter((r): r is string => !!r))].sort((a, b) => a.localeCompare(b)),
    [cards],
  )

  // Criadores distintos (id → nome); cards sem dono = "Sistema"
  const criadores = useMemo(() => {
    const map = new Map<string, string>()
    let temSistema = false
    for (const c of cards) {
      if (c.criado_por_id) map.set(c.criado_por_id, c.criado_por_nome || 'Usuário')
      else temSistema = true
    }
    const arr = [...map.entries()].sort((a, b) => a[1].localeCompare(b[1]))
    return { lista: arr, temSistema }
  }, [cards])

  const toggleProjetoFiltro = (id: string) =>
    setFiltroProjetos((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  const toggleRespFiltro = (nome: string) =>
    setFiltroResp((prev) => prev.includes(nome) ? prev.filter((x) => x !== nome) : [...prev, nome])
  const toggleCriadorFiltro = (id: string) =>
    setFiltroCriador((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])

  const submitCreate = () => {
    if (!form.titulo.trim()) return
    criar.mutate({
      titulo: form.titulo.trim(),
      descricao: form.descricao || null,
      cliente_id: form.cliente_id || null,
      processo_id: form.processo_id || null,
      projeto_id: form.projeto_id || null,
      responsavel: form.responsavel.nome || null,
      responsavel_email: form.responsavel.email || null,
      responsavel_id: form.responsavel.id || null,
      data_limite: form.data_limite || null,
      confidencial: form.confidencial,
      subtasks: form.subtasks.filter((s) => s.trim()).map((texto, ordem) => ({ texto: texto.trim(), ordem })),
    })
  }

  // ── Filtragem + agrupamento por projeto ──────────────────────────────────
  const passaFiltro = (c: TarefaCard) => {
    if (filtroStatus && c.status !== filtroStatus) return false
    if (filtroResp.length > 0 && !filtroResp.includes(c.responsavel || '__none__')) return false
    if (filtroCriador.length > 0 && !filtroCriador.includes(c.criado_por_id || '__sistema__')) return false
    if (filtroProjetos.length > 0 && !filtroProjetos.includes(c.projeto_id || '__none__')) return false
    if (filtroMes.aplicar && !filtroMes.dentro(c.data_limite)) return false
    if (filtroVenc) {
      const d = c.data_limite
      if (filtroVenc === 'sem_prazo' && d) return false
      if (filtroVenc === 'com_prazo' && !d) return false
      if (filtroVenc === 'atrasadas' && !(d && diasAte(d) < 0)) return false
      if (filtroVenc === 'hoje' && !(d && diasAte(d) === 0)) return false
      if (filtroVenc === 'semana' && !(d && diasAte(d) >= 0 && diasAte(d) <= 7)) return false
    }
    return true
  }

  const grupos = useMemo(() => {
    const map = new Map<string, { nome: string; cor: string; cards: TarefaCard[] }>()
    for (const c of cards.filter(passaFiltro)) {
      const key = c.projeto_id || '__none__'
      if (!map.has(key)) map.set(key, { nome: c.projeto_nome || 'Sem projeto', cor: c.projeto_cor || '#d1d5db', cards: [] })
      map.get(key)!.cards.push(c)
    }
    // Dentro de cada projeto: cards COM prazo primeiro (mais próximo antes),
    // cards SEM prazo depois (mantendo a ordem de chegada entre si).
    for (const g of map.values()) {
      g.cards.sort((a, b) => {
        if (a.data_limite && !b.data_limite) return -1
        if (!a.data_limite && b.data_limite) return 1
        if (a.data_limite && b.data_limite) return a.data_limite.localeCompare(b.data_limite)
        return 0
      })
    }
    return [...map.entries()].sort((a, b) => {
      if (a[0] === '__none__') return 1
      if (b[0] === '__none__') return -1
      return a[1].nome.localeCompare(b[1].nome)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, filtroStatus, filtroVenc, filtroResp, filtroCriador, filtroProjetos,
      filtroMes.aplicar, filtroMes.range.de?.getTime(), filtroMes.range.ate?.getTime()])

  const podeGerenciar = (c: TarefaCard) => isSuperAdmin || (c.criado_por_id && usuario?.id === c.criado_por_id)
  const totalFiltrado = grupos.reduce((n, [, g]) => n + g.cards.length, 0)

  // Visão Arquivadas: lista plana filtrada + ordenável (recente por padrão)
  const arquivadasOrdenadas = useMemo(() => {
    const arr = cards.filter(passaFiltro)
    arr.sort((a, b) => {
      if (sortArq === 'titulo') return a.titulo.localeCompare(b.titulo)
      if (sortArq === 'cliente') return (a.cliente_nome || '').localeCompare(b.cliente_nome || '')
      if (sortArq === 'prazo') return (a.data_limite || '9999').localeCompare(b.data_limite || '9999')
      // recente: por data de arquivamento desc (fallback updated_at)
      return (b.arquivada_em || b.updated_at || '').localeCompare(a.arquivada_em || a.updated_at || '')
    })
    return arr
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, sortArq, filtroStatus, filtroVenc, filtroResp, filtroCriador, filtroProjetos,
      filtroMes.aplicar, filtroMes.range.de?.getTime(), filtroMes.range.ate?.getTime()])

  const renderCard = (c: TarefaCard) => {
    const done = c.subtasks.filter((s) => s.concluida).length
    return (
                  <div key={c.id} className={`${cs.card} ${cs[`card_${c.status}` as keyof typeof cs]} ${c.confidencial ? cs.card_confidencial : ''}`}>
                    {c.acesso_restrito ? (
                      <div className={cs.restrito}>
                        <div className={cs.restritoIcon}>🔒</div>
                        <div className={cs.restritoTxt}>Card confidencial</div>
                        {!c.ja_solicitou ? (
                          <button className={cs.linkBtn} style={{ color: '#7c3aed', fontWeight: 600 }}
                            onClick={() => solicitar.mutate(c.id)}>Solicitar acesso</button>
                        ) : <span className={cs.projetoCount}>Acesso solicitado</span>}
                      </div>
                    ) : (
                      <>
                        <div className={cs.cardTopRow}>
                          <div className={cs.cardTitle}>{c.titulo}</div>
                          {c.confidencial && <span className={cs.lockBadge}>🔒</span>}
                        </div>
                        {c.descricao && <div className={cs.cardDesc}>{c.descricao}</div>}

                        <div className={cs.chips}>
                          {c.responsavel && <span className={cs.chip}>👤 {c.responsavel}</span>}
                          {c.cliente_nome && <span className={cs.chip}>🏢 {c.cliente_nome}</span>}
                          {c.processo_numero && <span className={cs.chip}>⚖️ {c.processo_numero}</span>}
                          {c.data_limite && (
                            <span className={`${cs.chip} ${vencido(c.data_limite) && c.status !== 'concluido' ? cs.chipVencido : cs.chipPrazo}`}>
                              📅 {fmtData(c.data_limite)}
                            </span>
                          )}
                        </div>

                        <div className={cs.cardMeta}>
                          <select className={cs.statusSelect} value={c.status}
                            onChange={(e) => atualizar.mutate({ id: c.id, data: { status: e.target.value as StatusTarefaCard } })}>
                            {STATUS_OPTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                          </select>
                        </div>

                        {/* Subtarefas */}
                        <div className={cs.subtasks}>
                          {c.subtasks.length > 0 && <div className={cs.subtaskProgress}>{done}/{c.subtasks.length} concluídas</div>}
                          <div className={cs.subtaskList}>
                          {c.subtasks.map((st) => (
                            <div key={st.id}>
                            <div className={cs.subtaskRow}>
                              <input type="checkbox" checked={st.concluida}
                                onChange={(e) => toggleSubtask.mutate({ id: st.id, concluida: e.target.checked })} />
                              {editSub?.id === st.id ? (
                                <input autoFocus className={cs.subEditInput} value={editSub.texto}
                                  onChange={(e) => setEditSub({ id: st.id, texto: e.target.value })}
                                  onBlur={() => editSub.texto.trim() ? editarSubtask.mutate({ id: st.id, texto: editSub.texto.trim() }) : setEditSub(null)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' && editSub.texto.trim()) editarSubtask.mutate({ id: st.id, texto: editSub.texto.trim() })
                                    if (e.key === 'Escape') setEditSub(null)
                                  }} />
                              ) : (
                                <span className={`${cs.subtaskText} ${st.concluida ? cs.subtaskDone : ''}`}
                                  onDoubleClick={() => setEditSub({ id: st.id, texto: st.texto })}>{st.texto}</span>
                              )}
                              <SubtaskPrazo
                                value={st.data_limite || null}
                                max={c.data_limite || null}
                                vencido={vencido(st.data_limite) && !st.concluida}
                                onChange={(d) => setPrazoSub.mutate({ id: st.id, data: d })}
                              />
                              <button className={cs.subEdit} title="Editar" onClick={() => setEditSub({ id: st.id, texto: st.texto })}>✎</button>
                              <label className={cs.subAnexoBtn} title="Anexar arquivo">
                                📎
                                <input type="file" style={{ display: 'none' }} disabled={uploadAnexoSub.isPending}
                                  onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadAnexoSub.mutate({ id: st.id, file: f }); e.currentTarget.value = '' }} />
                              </label>
                              <button className={cs.subtaskDel} title="Excluir" onClick={() => delSubtask.mutate(st.id)}>×</button>
                            </div>
                            {st.anexos && st.anexos.length > 0 && (
                              <div className={cs.subAnexosLine}>
                                {st.anexos.map((a) => (
                                  <span key={a.id} className={cs.anexoChip}>
                                    <a href={a.drive_link || '#'} target="_blank" rel="noreferrer" title={a.nome_arquivo}>📎 {a.nome_arquivo}</a>
                                    <button className={cs.anexoDel} title="Remover" onClick={() => deletarAnexo.mutate(a.id)}>×</button>
                                  </span>
                                ))}
                              </div>
                            )}
                            </div>
                          ))}
                          </div>
                          <input className={cs.addSubtask} placeholder="+ subtarefa (Enter)"
                            value={novaSubtask[c.id] || ''}
                            onChange={(e) => setNovaSubtask((s) => ({ ...s, [c.id]: e.target.value }))}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' && novaSubtask[c.id]?.trim()) {
                                addSubtask.mutate({ id: c.id, texto: novaSubtask[c.id].trim() })
                                setNovaSubtask((s) => ({ ...s, [c.id]: '' }))
                              }
                            }} />
                        </div>

                        <AnexoUploader
                          anexos={c.anexos || []}
                          onUpload={(f) => uploadAnexoCard.mutate({ id: c.id, file: f })}
                          onDelete={(id) => deletarAnexo.mutate(id)}
                          uploading={uploadAnexoCard.isPending}
                        />

                        {podeGerenciar(c) && c.pedidos_acesso.length > 0 && (
                          <div style={{ marginTop: 8, fontSize: 11 }}>
                            <div style={{ color: '#92400e', marginBottom: 4 }}>Pedidos de acesso:</div>
                            {c.pedidos_acesso.map((p) => (
                              <div key={p.usuario_id} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                                <span>{p.nome}</span>
                                <button className={cs.linkBtn} style={{ color: '#10b981' }}
                                  onClick={() => conceder.mutate({ cardId: c.id, usuarioId: p.usuario_id })}>conceder</button>
                              </div>
                            ))}
                          </div>
                        )}

                        <div className={cs.cardActions}>
                          {c.data_limite && (
                            c.google_event_id
                              ? <span className={`${cs.linkBtn} ${cs.linkAgendado}`}>✓ Na agenda</span>
                              : <button className={`${cs.linkBtn} ${cs.linkAgendar}`} disabled={agendar.isPending}
                                  onClick={() => agendar.mutate(c.id)}>📅 Agendar</button>
                          )}
                          <button className={`${cs.linkBtn} ${cs.linkEditar}`} onClick={() => setEditCard(c)}>✎ Editar</button>
                          {visao === 'arquivadas' ? (
                            <button className={`${cs.linkBtn} ${cs.linkEditar}`} disabled={desarquivar.isPending}
                              onClick={() => desarquivar.mutate(c.id)}>↩ Desarquivar</button>
                          ) : (
                            <button className={`${cs.linkBtn} ${cs.linkEditar}`} disabled={arquivar.isPending}
                              onClick={() => arquivar.mutate(c.id)}>🗄 Arquivar</button>
                          )}
                          <button className={`${cs.linkBtn} ${cs.linkExcluir}`}
                            onClick={() => { if (confirm('Excluir card?')) deletar.mutate(c.id) }}>Excluir</button>
                        </div>
                      </>
                    )}
                  </div>
    )
  }

  return (
    <div>
      <div className={cs.toolbar}>
        {visao === 'ativas' && (
          <button className={styles.btnPrimary} onClick={() => { setShowForm((s) => !s); setForm(emptyForm) }}>
            {showForm ? 'Cancelar' : '+ Novo card'}
          </button>
        )}
        <div className={cs.statusTabs} style={{ marginLeft: 'auto' }}>
          <button className={`${cs.statusTab} ${visao === 'ativas' ? cs.statusTabActive : ''}`}
            onClick={() => setVisao('ativas')}>Ativas</button>
          <button className={`${cs.statusTab} ${visao === 'arquivadas' ? cs.statusTabActive : ''}`}
            onClick={() => { setVisao('arquivadas'); setShowForm(false) }}>🗄 Arquivadas</button>
        </div>
      </div>

      {/* ── Formulário de criação ─────────────────────────────── */}
      {showForm && (
        <div className={styles.form}>
          <CardFields
            form={form} setForm={setForm} projetos={projetos} clientes={clientes}
            processoOptions={processoOptions} criarProjetoRapido={criarProjetoRapido} criarClienteRapido={criarClienteRapido}
            showSubtasks
          />
          <button className={styles.btnPrimary} disabled={!form.titulo.trim() || criar.isPending} onClick={submitCreate}>
            {criar.isPending ? 'Salvando...' : 'Criar card'}
          </button>
        </div>
      )}

      {/* ── Filtros ────────────────────────────────────────────── */}
      <div className={cs.filters}>
        <div className={cs.statusTabs}>
          {STATUS_FILTER.map((s) => (
            <button key={s} className={`${cs.statusTab} ${filtroStatus === s ? cs.statusTabActive : ''}`}
              onClick={() => setFiltroStatus(s)}>{STATUS_LABEL[s]}</button>
          ))}
        </div>
        <select className={cs.filterSelect} value={filtroVenc} onChange={(e) => setFiltroVenc(e.target.value as FiltroVenc)}>
          {VENC_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {/* Filtro por mês (prazo do card) — padrão Despacho */}
      {filtroMes.node}

      {/* Filtro multi-responsável (chips) */}
      {(responsaveis.length > 0 || cards.some((c) => !c.responsavel)) && (
        <div className={cs.projetoChips}>
          <span className={cs.chipsLabel}>Responsável:</span>
          {responsaveis.map((r) => (
            <button key={r} className={`${cs.projChip} ${filtroResp.includes(r) ? cs.projChipOn : ''}`}
              onClick={() => toggleRespFiltro(r)}>👤 {r}</button>
          ))}
          {cards.some((c) => !c.responsavel) && (
            <button className={`${cs.projChip} ${filtroResp.includes('__none__') ? cs.projChipOn : ''}`}
              onClick={() => toggleRespFiltro('__none__')}>Sem responsável</button>
          )}
          {filtroResp.length > 0 && (
            <button className={cs.linkBtn} style={{ color: '#6b7280' }} onClick={() => setFiltroResp([])}>limpar</button>
          )}
        </div>
      )}

      {/* Filtro multi-criador (chips) */}
      {(criadores.lista.length > 0 || criadores.temSistema) && (
        <div className={cs.projetoChips}>
          <span className={cs.chipsLabel}>Criado por:</span>
          {criadores.lista.map(([id, nome]) => (
            <button key={id} className={`${cs.projChip} ${filtroCriador.includes(id) ? cs.projChipOn : ''}`}
              onClick={() => toggleCriadorFiltro(id)}>{nome}</button>
          ))}
          {criadores.temSistema && (
            <button className={`${cs.projChip} ${filtroCriador.includes('__sistema__') ? cs.projChipOn : ''}`}
              onClick={() => toggleCriadorFiltro('__sistema__')}>⚙️ Sistema</button>
          )}
          {filtroCriador.length > 0 && (
            <button className={cs.linkBtn} style={{ color: '#6b7280' }} onClick={() => setFiltroCriador([])}>limpar</button>
          )}
        </div>
      )}

      {/* Filtro multi-projeto (chips) */}
      {(projetos.some((p) => !p.oculto) || cards.some((c) => !c.projeto_id)) && (
        <div className={cs.projetoChips}>
          <span className={cs.chipsLabel}>Projeto:</span>
          {projetos.filter((p) => !p.oculto).map((p) => (
            <button key={p.id} className={`${cs.projChip} ${filtroProjetos.includes(p.id) ? cs.projChipOn : ''}`}
              onClick={() => toggleProjetoFiltro(p.id)}>
              <span className={cs.projetoDot} style={{ background: p.cor }} />{p.nome}
            </button>
          ))}
          <button className={`${cs.projChip} ${filtroProjetos.includes('__none__') ? cs.projChipOn : ''}`}
            onClick={() => toggleProjetoFiltro('__none__')}>
            <span className={cs.projetoDot} style={{ background: '#d1d5db' }} />Sem projeto
          </button>
          {filtroProjetos.length > 0 && (
            <button className={cs.linkBtn} style={{ color: '#6b7280' }} onClick={() => setFiltroProjetos([])}>limpar</button>
          )}
        </div>
      )}

      {/* Sort — só na visão Arquivadas (mais recente por padrão) */}
      {visao === 'arquivadas' && (
        <div style={{ marginBottom: 12 }}>
          <select className={cs.filterSelect} value={sortArq} onChange={(e) => setSortArq(e.target.value as typeof sortArq)}>
            <option value="recente">Mais recente primeiro</option>
            <option value="prazo">Prazo ↑</option>
            <option value="titulo">Título A→Z</option>
            <option value="cliente">Cliente A→Z</option>
          </select>
        </div>
      )}

      {/* ── Lista ────────────────────────────────────────────── */}
      {isLoading ? <p>Carregando...</p> : visao === 'arquivadas' ? (
        arquivadasOrdenadas.length === 0 ? (
          <div className={styles.empty}>{cards.length === 0 ? 'Nenhuma tarefa arquivada.' : 'Nenhuma arquivada com os filtros atuais.'}</div>
        ) : (
          <div className={cs.cardGrid}>{arquivadasOrdenadas.map(renderCard)}</div>
        )
      ) : cards.length === 0 ? (
        <div className={styles.empty}>Nenhum card cadastrado</div>
      ) : totalFiltrado === 0 ? (
        <div className={styles.empty}>Nenhum card com os filtros atuais</div>
      ) : (
        grupos.map(([key, g]) => (
          <section key={key} className={cs.projetoSection}>
            <h3 className={cs.projetoHeader}>
              <span className={cs.projetoDot} style={{ background: g.cor }} />
              {g.nome}
              <span className={cs.projetoCount}>{g.cards.length}</span>
            </h3>
            <div className={cs.cardGrid}>
              {g.cards.map(renderCard)}
            </div>
          </section>
        ))
      )}

      {/* ── Modal de edição do card ───────────────────────────── */}
      {editCard && (
        <EditCardModal
          card={editCard} onClose={() => setEditCard(null)}
          projetos={projetos} clientes={clientes} processoOptions={processoOptions}
          criarProjetoRapido={criarProjetoRapido} criarClienteRapido={criarClienteRapido}
          onSave={(data) => atualizar.mutate({ id: editCard.id, data: data as never }, { onSuccess: () => setEditCard(null) })}
          saving={atualizar.isPending}
        />
      )}
    </div>
  )
}

// ─────────────────────────── Anexos (Google Drive) ─────────────────────────
function AnexoUploader({ anexos, onUpload, onDelete, uploading }: {
  anexos: { id: string; nome_arquivo: string; drive_link: string | null }[]
  onUpload: (file: File) => void
  onDelete: (id: string) => void
  uploading: boolean
}) {
  return (
    <div className={cs.anexos}>
      {anexos.map((a) => (
        <span key={a.id} className={cs.anexoChip}>
          <a href={a.drive_link || '#'} target="_blank" rel="noreferrer" title={a.nome_arquivo}>📎 {a.nome_arquivo}</a>
          <button className={cs.anexoDel} title="Remover" onClick={() => onDelete(a.id)}>×</button>
        </span>
      ))}
      <label className={cs.anexoAdd}>
        {uploading ? '⏳ enviando…' : '📎 anexar'}
        <input type="file" style={{ display: 'none' }} disabled={uploading}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.currentTarget.value = '' }} />
      </label>
    </div>
  )
}

// ─────────────────── Prazo interno da subtarefa (discreto) ──────────────────
function SubtaskPrazo({ value, max, vencido, onChange }: {
  value: string | null
  max: string | null                // prazo do card macro — limite superior
  vencido: boolean
  onChange: (d: string | null) => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  const abrir = () => {
    const el = ref.current
    if (!el) return
    // showPicker abre o calendário nativo; fallback para focus
    if (typeof el.showPicker === 'function') el.showPicker()
    else el.focus()
  }
  const curta = value ? new Date(value + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) : null
  return (
    <span className={cs.subPrazoWrap}>
      <button
        type="button"
        className={`${cs.subPrazoBtn} ${value ? cs.subPrazoSet : ''} ${vencido ? cs.subPrazoVencido : ''}`}
        title={value ? `Prazo interno: ${new Date(value + 'T12:00:00').toLocaleDateString('pt-BR')} (clique p/ alterar)` : 'Definir prazo interno (≤ prazo do card)'}
        onClick={abrir}
      >
        {curta || '📅'}
      </button>
      <input
        ref={ref}
        type="date"
        className={cs.subPrazoInput}
        value={value || ''}
        max={max || undefined}
        onChange={(e) => onChange(e.target.value || null)}
      />
    </span>
  )
}

// ─────────────────────────── Campos compartilhados ──────────────────────────
interface CardFieldsProps {
  form: FormState
  setForm: (f: FormState) => void
  projetos: import('../api/tarefaProjetos').TarefaProjeto[]
  clientes: import('../api/clientes').Cliente[]
  processoOptions: { value: string; label: string; sublabel?: string }[]
  criarProjetoRapido: (nome: string, cor: string) => Promise<import('../api/tarefaProjetos').TarefaProjeto>
  criarClienteRapido: (nome: string) => Promise<string>
  showSubtasks?: boolean
}
function CardFields({ form, setForm, projetos, clientes, processoOptions, criarProjetoRapido, criarClienteRapido, showSubtasks }: CardFieldsProps) {
  return (
    <>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Título do card *</label>
        <input className={styles.input} value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Descrição</label>
        <textarea className={styles.input} rows={2} value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Projeto</label>
        <ProjetoCombobox projetos={projetos} value={form.projeto_id} onChange={(id) => setForm({ ...form, projeto_id: id })} onCriar={criarProjetoRapido} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Cliente</label>
        <ClienteCombobox value={form.cliente_id} clientes={clientes} onChange={(id) => setForm({ ...form, cliente_id: id })} onCreateCliente={criarClienteRapido} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Processo</label>
        <ComboBox options={processoOptions} value={form.processo_id} onChange={(v) => setForm({ ...form, processo_id: v })} placeholder="Buscar por CNJ..." />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Responsável</label>
        <ResponsavelComboBox value={form.responsavel} onChange={(v) => setForm({ ...form, responsavel: v })} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Prazo</label>
        <input type="date" className={styles.input} value={form.data_limite} onChange={(e) => setForm({ ...form, data_limite: e.target.value })} />
      </div>
      {showSubtasks && (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Subtarefas</label>
          {form.subtasks.map((st, i) => (
            <div key={i} className={cs.subtaskFormRow}>
              <input className={styles.input} placeholder={`Subtarefa ${i + 1}`} value={st}
                onChange={(e) => { const arr = [...form.subtasks]; arr[i] = e.target.value; setForm({ ...form, subtasks: arr }) }} />
              {form.subtasks.length > 1 && (
                <button type="button" className={cs.subtaskDel}
                  onClick={() => setForm({ ...form, subtasks: form.subtasks.filter((_, j) => j !== i) })}>×</button>
              )}
            </div>
          ))}
          <button type="button" className={cs.linkBtn} style={{ color: '#2563eb' }}
            onClick={() => setForm({ ...form, subtasks: [...form.subtasks, ''] })}>+ Adicionar subtarefa</button>
        </div>
      )}
      <label className={cs.confidencialRow}>
        <input type="checkbox" checked={form.confidencial} onChange={(e) => setForm({ ...form, confidencial: e.target.checked })} />
        🔒 Card confidencial (privacidade)
      </label>
    </>
  )
}

// ─────────────────────────── Modal de edição ────────────────────────────────
interface EditModalProps {
  card: TarefaCard
  onClose: () => void
  onSave: (data: Record<string, unknown>) => void
  saving: boolean
  projetos: import('../api/tarefaProjetos').TarefaProjeto[]
  clientes: import('../api/clientes').Cliente[]
  processoOptions: { value: string; label: string; sublabel?: string }[]
  criarProjetoRapido: (nome: string, cor: string) => Promise<import('../api/tarefaProjetos').TarefaProjeto>
  criarClienteRapido: (nome: string) => Promise<string>
}
function EditCardModal({ card, onClose, onSave, saving, projetos, clientes, processoOptions, criarProjetoRapido, criarClienteRapido }: EditModalProps) {
  const [form, setForm] = useState<FormState>({
    titulo: card.titulo,
    descricao: card.descricao || '',
    cliente_id: card.cliente_id || '',
    processo_id: card.processo_id || '',
    projeto_id: card.projeto_id || '',
    responsavel: { nome: card.responsavel || '', email: card.responsavel_email || '', id: card.responsavel_id || null },
    data_limite: card.data_limite || '',
    confidencial: card.confidencial,
    subtasks: [''],
  })
  return (
    <Modal title="Editar card" onClose={onClose} width={520}>
      <CardFields
        form={form} setForm={setForm} projetos={projetos} clientes={clientes}
        processoOptions={processoOptions} criarProjetoRapido={criarProjetoRapido} criarClienteRapido={criarClienteRapido}
      />
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button className={styles.btnPrimary} disabled={!form.titulo.trim() || saving}
          onClick={() => onSave({
            titulo: form.titulo.trim(),
            descricao: form.descricao || null,
            cliente_id: form.cliente_id || null,
            processo_id: form.processo_id || null,
            projeto_id: form.projeto_id || null,
            responsavel: form.responsavel.nome || null,
            responsavel_email: form.responsavel.email || null,
            responsavel_id: form.responsavel.id || null,
            data_limite: form.data_limite || null,
            confidencial: form.confidencial,
          })}>
          {saving ? 'Salvando...' : 'Salvar alterações'}
        </button>
        <button className={cs.linkBtn} style={{ color: '#6b7280' }} onClick={onClose}>Cancelar</button>
      </div>
    </Modal>
  )
}
