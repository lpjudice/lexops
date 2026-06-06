import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tarefasApi } from '../api/tarefas'
import type { StatusTarefa, Tarefa } from '../api/tarefas'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import { anotacoesApi } from '../api/anotacoes'
import { usuariosApi } from '../api/usuarios'
import { useAuth } from '../contexts/AuthContext'
import ComboBox from '../components/ComboBox'
import ClienteCombobox from '../components/ClienteCombobox'
import styles from './Page.module.css'
import t from './TarefasPage.module.css'

const STATUS_LABEL: Record<StatusTarefa, string> = {
  pendente: 'Pendente',
  em_andamento: 'Em andamento',
  concluido: 'Concluído',
  cancelado: 'Cancelado',
}

const STATUS_NEXT: Record<StatusTarefa, StatusTarefa> = {
  pendente: 'em_andamento',
  em_andamento: 'concluido',
  concluido: 'pendente',
  cancelado: 'pendente',
}

function formatDate(d?: string | null) {
  if (!d) return null
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

function diasRestantes(d?: string | null): number | null {
  if (!d) return null
  return Math.ceil((new Date(d).getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000)
}

interface TaskRow {
  titulo: string
  descricao: string
  data_limite: string
  tag: string
}

const EMPTY_ROW: TaskRow = { titulo: '', descricao: '', data_limite: '', tag: '' }

interface EditForm {
  titulo: string
  descricao: string
  responsavel: string
  data_limite: string
  tags: string
  cliente_id: string
  processo_id: string
  status: StatusTarefa
  confidencial?: boolean
}

export default function TarefasPage() {
  const qc = useQueryClient()
  const { usuario, isSuperAdmin } = useAuth()

  // ── Create form ───────────────────────────────────────────────────────
  const [showForm, setShowForm] = useState(false)
  const [rows, setRows] = useState<TaskRow[]>([{ ...EMPTY_ROW }])
  const [batchCliente, setBatchCliente] = useState('')
  const [batchProcesso, setBatchProcesso] = useState('')

  const addRow = () => setRows((p) => [...p, { ...EMPTY_ROW }])
  const removeRow = (i: number) => setRows((p) => p.filter((_, idx) => idx !== i))
  const updateRow = (i: number, field: keyof TaskRow, val: string) =>
    setRows((p) => p.map((r, idx) => (idx === i ? { ...r, [field]: val } : r)))

  // ── Filters ───────────────────────────────────────────────────────────
  const [filtroStatus, setFiltroStatus] = useState<StatusTarefa | ''>('pendente')
  const [filtroCliente, setFiltroCliente] = useState('')
  const [sortBy, setSortBy] = useState<'prazo_asc' | 'prazo_desc' | 'cliente_az'>('prazo_asc')

  // ── Card UI state ─────────────────────────────────────────────────────
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [batchResponsavel, setBatchResponsavel] = useState('')
  const [editForm, setEditForm] = useState<EditForm>({
    titulo: '', descricao: '', responsavel: '', data_limite: '', tags: '',
    cliente_id: '', processo_id: '', status: 'pendente',
  })

  // ── Queries ───────────────────────────────────────────────────────────
  const { data: tarefas = [], isLoading } = useQuery({
    queryKey: ['tarefas', filtroStatus],
    queryFn: () => tarefasApi.listar(filtroStatus ? { status: filtroStatus } : undefined),
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })

  const { data: anotacoes = [] } = useQuery({
    queryKey: ['anotacoes'],
    queryFn: () => anotacoesApi.listar(),
  })

  const { data: usuarios = [] } = useQuery({
    queryKey: ['usuarios'],
    queryFn: usuariosApi.listar,
  })

  // ── Mutations ─────────────────────────────────────────────────────────
  const criar = useMutation({
    mutationFn: (tasks: Parameters<typeof tarefasApi.criar>[0][]) =>
      Promise.all(tasks.map((tk) => tarefasApi.criar(tk))),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      setShowForm(false)
      setRows([{ ...EMPTY_ROW }])
      setBatchCliente('')
      setBatchProcesso('')
      setBatchResponsavel('')
    },
  })

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof tarefasApi.atualizar>[1] }) =>
      tarefasApi.atualizar(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      setEditingId(null)
    },
  })

  const deletar = useMutation({
    mutationFn: (id: string) => tarefasApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tarefas'] }),
    onError: () => alert('Sem permissão para excluir esta tarefa.'),
  })

  const solicitarAcesso = useMutation({
    mutationFn: (id: string) => tarefasApi.solicitarAcesso(id),
    onSuccess: (r) => { alert(r.mensagem); qc.invalidateQueries({ queryKey: ['tarefas'] }) },
    onError: () => alert('Erro ao solicitar acesso.'),
  })

  const concederAcesso = useMutation({
    mutationFn: ({ tarefaId, usuarioId }: { tarefaId: string; usuarioId: string }) =>
      tarefasApi.concederAcesso(tarefaId, usuarioId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tarefas'] }),
    onError: () => alert('Erro ao conceder acesso.'),
  })

  const revogarAcesso = useMutation({
    mutationFn: ({ tarefaId, usuarioId }: { tarefaId: string; usuarioId: string }) =>
      tarefasApi.revogarAcesso(tarefaId, usuarioId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tarefas'] }),
    onError: () => alert('Erro ao recusar solicitação.'),
  })

  const criarClienteRapido = async (raw: string): Promise<string> => {
    const [nome, tipo] = raw.split('|')
    const c = await clientesApi.criar({ nome, tipo: (tipo as 'PF' | 'PJ') ?? 'PF', incompleto: true })
    qc.invalidateQueries({ queryKey: ['clientes'] })
    return c.id
  }

  // ── Helpers ───────────────────────────────────────────────────────────
  const clienteNome = (id: string | null) =>
    id ? (clientes.find((c) => c.id === id)?.nome ?? null) : null

  const processoLabel = (id: string | null) => {
    if (!id) return null
    const p = processos.find((p) => p.id === id)
    if (!p) return null
    const cliente = clientes.find((c) => c.id === p.cliente_id)
    return cliente ? `${p.numero_cnj} · ${cliente.nome}` : p.numero_cnj
  }

  const anotacaoTitulo = (id: string | null) => {
    if (!id) return null
    const a = anotacoes.find((a) => a.id === id)
    return a ? (a.titulo || 'Atendimento') : null
  }

  const tarefasFiltradas = useMemo(() => {
    let arr = [...tarefas]
    if (filtroCliente) arr = arr.filter((t) => t.cliente_id === filtroCliente)
    if (sortBy === 'prazo_asc') {
      arr.sort((a, b) => {
        if (!a.data_limite && !b.data_limite) return 0
        if (!a.data_limite) return 1
        if (!b.data_limite) return -1
        return a.data_limite.localeCompare(b.data_limite)
      })
    } else if (sortBy === 'prazo_desc') {
      arr.sort((a, b) => {
        if (!a.data_limite && !b.data_limite) return 0
        if (!a.data_limite) return -1
        if (!b.data_limite) return 1
        return b.data_limite.localeCompare(a.data_limite)
      })
    } else if (sortBy === 'cliente_az') {
      arr.sort((a, b) => {
        const na = clienteNome(a.cliente_id) || ''
        const nb = clienteNome(b.cliente_id) || ''
        return na.localeCompare(nb, 'pt-BR')
      })
    }
    return arr
  }, [tarefas, filtroCliente, sortBy, clientes]) // eslint-disable-line react-hooks/exhaustive-deps

  const processoOptions = processos.map((p) => {
    const cliente = clientes.find((c) => c.id === p.cliente_id)
    return {
      value: p.id,
      label: p.numero_cnj,
      sublabel: cliente ? `${cliente.nome}${p.objeto ? ' · ' + p.objeto : ''}` : undefined,
    }
  })

  const openEdit = (tarefa: Tarefa) => {
    setEditingId(tarefa.id)
    setEditForm({
      titulo: tarefa.titulo,
      descricao: tarefa.descricao ?? '',
      responsavel: tarefa.responsavel ?? '',
      data_limite: tarefa.data_limite ?? '',
      tags: tarefa.tags ?? '',
      cliente_id: tarefa.cliente_id ?? '',
      processo_id: tarefa.processo_id ?? '',
      status: tarefa.status,
    })
    setExpandedId(null)
  }

  const submitEdit = () => {
    if (!editingId) return
    atualizar.mutate({
      id: editingId,
      data: {
        titulo: editForm.titulo,
        descricao: editForm.descricao || null,
        responsavel: editForm.responsavel || null,
        data_limite: editForm.data_limite || null,
        tags: editForm.tags || null,
        cliente_id: editForm.cliente_id || null,
        processo_id: editForm.processo_id || null,
        status: editForm.status,
        ...(editForm.confidencial !== undefined ? { confidencial: editForm.confidencial } : {}),
      },
    })
  }

  const submitCreate = (e: React.FormEvent) => {
    e.preventDefault()
    const valid = rows.filter((r) => r.titulo.trim())
    if (!valid.length) return
    criar.mutate(
      valid.map((r) => ({
        titulo: r.titulo.trim(),
        descricao: r.descricao || null,
        responsavel: batchResponsavel || null,
        data_limite: r.data_limite || null,
        tags: r.tag || null,
        cliente_id: batchCliente || null,
        processo_id: batchProcesso || null,
      }))
    )
  }

    // ── Calendar state ────────────────────────────────────────────────────
  const [viewMode, setViewMode] = useState<'list' | 'calendar'>('list')
  const [calYear, setCalYear] = useState(() => new Date().getFullYear())
  const [calMonth, setCalMonth] = useState(() => new Date().getMonth()) // 0-indexed
  const [_draggingId, setDraggingId] = useState<string | null>(null)

  const { data: todasTarefas = [] } = useQuery({
    queryKey: ['tarefas-todas'],
    queryFn: () => tarefasApi.listar(),
    enabled: viewMode === 'calendar',
  })

  const agendarCalendario = useMutation({
    mutationFn: (id: string) => tarefasApi.agendarCalendario(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      qc.invalidateQueries({ queryKey: ['tarefas-todas'] })
    },
  })

  const moverData = useMutation({
    mutationFn: ({ id, data_limite }: { id: string; data_limite: string }) =>
      tarefasApi.atualizar(id, { data_limite }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      qc.invalidateQueries({ queryKey: ['tarefas-todas'] })
    },
  })

  // Calendar helpers
  const MESES_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
  const DIAS_SEM = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb']

  function buildCalendarDays(year: number, month: number): (Date | null)[] {
    const firstDay = new Date(year, month, 1).getDay()
    const daysInMonth = new Date(year, month + 1, 0).getDate()
    const cells: (Date | null)[] = []
    for (let i = 0; i < firstDay; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d))
    return cells
  }

  function tarefasDodia(date: Date): Tarefa[] {
    const iso = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`
    return todasTarefas.filter((t) => t.data_limite === iso && t.status !== 'cancelado')
  }

  function handleDrop(e: React.DragEvent, date: Date) {
    e.preventDefault()
    const id = e.dataTransfer.getData('taskId')
    if (!id) return
    const iso = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`
    moverData.mutate({ id, data_limite: iso })
  }

  const prevMonth = () => {
    if (calMonth === 0) { setCalMonth(11); setCalYear(y => y - 1) }
    else setCalMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (calMonth === 11) { setCalMonth(0); setCalYear(y => y + 1) }
    else setCalMonth(m => m + 1)
  }

  const calDays = buildCalendarDays(calYear, calMonth)
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)

  const STATUS_FILTER: Array<StatusTarefa | ''> = ['', 'pendente', 'em_andamento', 'concluido']

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Tarefas</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            onClick={() => setViewMode(viewMode === 'list' ? 'calendar' : 'list')}
            style={{
              padding: '6px 14px', borderRadius: 8, border: '1px solid #e5e7eb',
              background: viewMode === 'calendar' ? '#1d1e20' : '#fff',
              color: viewMode === 'calendar' ? '#fff' : '#6b7280',
              fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {viewMode === 'calendar' ? '☰ Lista' : '📅 Calendário'}
          </button>
          <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancelar' : '+ Nova Tarefa'}
          </button>
        </div>
      </div>

      {/* ── Create form ─────────────────────────────────────────────── */}
      {showForm && (
        <form onSubmit={submitCreate} className={styles.form}>
          <div className={t.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Cliente (opcional)</label>
              <ClienteCombobox
                value={batchCliente}
                onChange={setBatchCliente}
                clientes={clientes}
                onCreateCliente={criarClienteRapido}
              />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Processo (opcional)</label>
              <ComboBox
                options={processoOptions}
                value={batchProcesso}
                onChange={setBatchProcesso}
                placeholder="Buscar por CNJ ou parte..."
              />
            </div>
          </div>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Responsável (opcional)</label>
            <select className={styles.input} value={batchResponsavel} onChange={(e) => setBatchResponsavel(e.target.value)}>
              <option value="">— Nenhum —</option>
              {usuarios.filter(u => u.ativo).map(u => (
                <option key={u.id} value={u.nome}>{u.nome}</option>
              ))}
              <option value="Terceiros">Terceiros</option>
            </select>
          </div>

          <div className={t.tasksBlock}>
            <div className={t.tasksHeader}>
              <span className={t.tasksTitle}>Tarefas</span>
              <button type="button" className={t.btnAddTask} onClick={addRow}>+ Adicionar</button>
            </div>
            {rows.map((row, i) => (
              <div key={i} className={t.taskRow}>
                <div className={t.taskMain}>
                  <input className={styles.input} placeholder="Tarefa *" required={i === 0}
                    value={row.titulo} onChange={(e) => updateRow(i, 'titulo', e.target.value)} />
                  <input className={`${styles.input} ${t.tagInput}`} placeholder="Tag curta"
                    value={row.tag} onChange={(e) => updateRow(i, 'tag', e.target.value)} />
                  <input type="date" className={styles.input} title="Prazo (opcional)"
                    value={row.data_limite} onChange={(e) => updateRow(i, 'data_limite', e.target.value)} />
                  {rows.length > 1 && (
                    <button type="button" className={t.btnRemoveTask} onClick={() => removeRow(i)}>×</button>
                  )}
                </div>
                <textarea
                  className={`${styles.input} ${t.detalhesInput}`}
                  rows={2}
                  placeholder="Detalhes / notas (opcional)"
                  value={row.descricao}
                  onChange={(e) => updateRow(i, 'descricao', e.target.value)}
                />
              </div>
            ))}
          </div>

          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {/* ── Filters (list mode only) ─────────────────────────────────── */}
      {viewMode === 'list' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          <div className={t.filtros} style={{ marginBottom: 0 }}>
            {STATUS_FILTER.map((s) => (
              <button key={s}
                className={`${t.filtroBtn} ${filtroStatus === s ? t.filtroBtnActive : ''}`}
                onClick={() => setFiltroStatus(s)}>
                {s === '' ? 'Todas' : STATUS_LABEL[s]}
              </button>
            ))}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
              style={{
                fontSize: 12, padding: '5px 10px', borderRadius: 999, border: '1px solid #e5e7eb',
                background: '#fff', color: '#6b7280', cursor: 'pointer', fontFamily: 'inherit', marginLeft: 'auto',
              }}
            >
              <option value="prazo_asc">Prazo ↑ (mais próximo)</option>
              <option value="prazo_desc">Prazo ↓ (mais distante)</option>
              <option value="cliente_az">Cliente A→Z</option>
            </select>
          </div>
          <div style={{ maxWidth: 300 }}>
            <ClienteCombobox
              value={filtroCliente}
              onChange={setFiltroCliente}
              clientes={clientes}
              onCreateCliente={criarClienteRapido}
            />
          </div>
        </div>
      )}

      {/* ── Calendar view ────────────────────────────────────────────── */}
      {viewMode === 'calendar' && (
        <div className={t.calendar}>
          <div className={t.calNav}>
            <button className={t.calNavBtn} onClick={prevMonth}>◄</button>
            <span className={t.calNavTitle}>{MESES_PT[calMonth]} {calYear}</span>
            <button className={t.calNavBtn} onClick={nextMonth}>►</button>
          </div>
          <div className={t.calGrid}>
            {DIAS_SEM.map((d) => (
              <div key={d} className={t.calDayHeader}>{d}</div>
            ))}
            {calDays.map((day, idx) => {
              if (!day) return <div key={`empty-${idx}`} className={t.calDayEmpty} />
              const isHoje = day.getTime() === hoje.getTime()
              const tasks = tarefasDodia(day)
              return (
                <div
                  key={day.toISOString()}
                  className={`${t.calDay} ${isHoje ? t.calDayHoje : ''}`}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => handleDrop(e, day)}
                >
                  <div className={t.calDayNum}>{day.getDate()}</div>
                  {tasks.map((task) => (
                    <div
                      key={task.id}
                      className={`${t.calChip} ${task.status === 'concluido' ? t.calChipConcluido : task.status === 'em_andamento' ? t.calChipAndamento : ''}`}
                      draggable
                      onDragStart={(e) => { e.dataTransfer.setData('taskId', task.id); setDraggingId(task.id) }}
                      onDragEnd={() => setDraggingId(null)}
                      title={task.titulo}
                    >
                      <span className={t.calChipTitulo}>{task.titulo}</span>
                      {!task.google_event_id && task.data_limite && (
                        <button
                          className={t.calBtnAgendar}
                          title="Agendar no Google Calendar"
                          onClick={(e) => { e.stopPropagation(); agendarCalendario.mutate(task.id) }}
                          disabled={agendarCalendario.isPending}
                        >📅</button>
                      )}
                      {task.google_event_id && (
                        <span className={t.calEventoIcon} title="Agendado no Google Calendar">✓📅</span>
                      )}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── List ─────────────────────────────────────────────────────── */}
      {viewMode === 'list' && (isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : tarefasFiltradas.length === 0 ? (
        <p className={styles.empty}>Nenhuma tarefa{filtroStatus ? ` com status "${STATUS_LABEL[filtroStatus as StatusTarefa]}"` : ''}.</p>
      ) : (
        <div className={t.lista}>
          {tarefasFiltradas.map((tarefa) => {
            const dias = diasRestantes(tarefa.data_limite)
            const atrasada = dias !== null && dias < 0 && tarefa.status !== 'concluido'
            const isExpanded = expandedId === tarefa.id
            const isEditing = editingId === tarefa.id
            const nomCliente = clienteNome(tarefa.cliente_id)
            const labelProcesso = processoLabel(tarefa.processo_id)
            const tituloAnotacao = anotacaoTitulo(tarefa.anotacao_id)

            const isCreator = usuario && tarefa.criado_por_id === usuario.id
            const canManage = isCreator || isSuperAdmin
            const acessoRestrito = tarefa.acesso_restrito
            const pedidos = tarefa.pedidos_acesso ?? []

            return (
              <div key={tarefa.id}
                className={`${t.card} ${atrasada ? t.atrasada : ''} ${tarefa.status === 'concluido' ? t.concluida : ''}`}
                style={tarefa.confidencial ? { borderLeft: '3px solid #a855f7' } : undefined}>

                {isEditing ? (
                  /* ── Inline edit form ──────────────────────────── */
                  <div className={t.editForm}>
                    <div className={t.twoCol}>
                      <div className={styles.formRow}>
                        <label className={styles.formLabel}>Tarefa</label>
                        <input className={styles.input} value={editForm.titulo}
                          onChange={(e) => setEditForm({ ...editForm, titulo: e.target.value })} />
                      </div>
                      <div className={styles.formRow}>
                        <label className={styles.formLabel}>Tag</label>
                        <input className={styles.input} placeholder="Tag curta" value={editForm.tags}
                          onChange={(e) => setEditForm({ ...editForm, tags: e.target.value })} />
                      </div>
                    </div>
                    <div className={t.twoCol}>
                      <div className={styles.formRow}>
                        <label className={styles.formLabel}>Cliente</label>
                        <ClienteCombobox
                          value={editForm.cliente_id}
                          onChange={(v) => setEditForm({ ...editForm, cliente_id: v })}
                          clientes={clientes}
                          onCreateCliente={criarClienteRapido}
                        />
                      </div>
                      <div className={styles.formRow}>
                        <label className={styles.formLabel}>Processo</label>
                        <ComboBox
                          options={[{ value: '', label: '— Nenhum —' }, ...processoOptions]}
                          value={editForm.processo_id}
                          onChange={(v) => setEditForm({ ...editForm, processo_id: v })}
                          placeholder="Buscar por CNJ..."
                        />
                      </div>
                    </div>
                    <div className={t.twoCol}>
                      <div className={styles.formRow}>
                        <label className={styles.formLabel}>Prazo</label>
                        <input type="date" className={styles.input} value={editForm.data_limite}
                          onChange={(e) => setEditForm({ ...editForm, data_limite: e.target.value })} />
                      </div>
                      <div className={styles.formRow}>
                        <label className={styles.formLabel}>Status</label>
                        <select className={styles.input} value={editForm.status}
                          onChange={(e) => setEditForm({ ...editForm, status: e.target.value as StatusTarefa })}>
                          <option value="pendente">Pendente</option>
                          <option value="em_andamento">Em andamento</option>
                          <option value="concluido">Concluído</option>
                          <option value="cancelado">Cancelado</option>
                        </select>
                      </div>
                    </div>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Responsável</label>
                      <select className={styles.input} value={editForm.responsavel} onChange={(e) => setEditForm({ ...editForm, responsavel: e.target.value })}>
                        <option value="">— Nenhum —</option>
                        {usuarios.filter(u => u.ativo).map(u => (
                          <option key={u.id} value={u.nome}>{u.nome}</option>
                        ))}
                        <option value="Terceiros">Terceiros</option>
                      </select>
                    </div>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Detalhes / notas</label>
                      <textarea className={styles.input} rows={3} value={editForm.descricao}
                        onChange={(e) => setEditForm({ ...editForm, descricao: e.target.value })} />
                    </div>
                    {canManage && (
                      <div className={styles.formRow} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <input
                          type="checkbox"
                          id={`conf-${tarefa.id}`}
                          checked={editForm.confidencial ?? tarefa.confidencial}
                          onChange={(e) => setEditForm({ ...editForm, confidencial: e.target.checked })}
                        />
                        <label htmlFor={`conf-${tarefa.id}`} style={{ fontSize: 13, color: '#7c3aed', cursor: 'pointer' }}>
                          🔒 Tarefa confidencial
                        </label>
                      </div>
                    )}
                    <div className={t.editAcoes}>
                      <button className={styles.btnPrimary} onClick={submitEdit} disabled={atualizar.isPending}>
                        {atualizar.isPending ? 'Salvando...' : 'Salvar'}
                      </button>
                      <button className={styles.btnTable} onClick={() => setEditingId(null)}>Cancelar</button>
                    </div>
                  </div>
                ) : acessoRestrito ? (
                  /* ── Restricted card: only lock + creator + cliente + prazo ── */
                  <>
                    <div className={t.cardTop}>
                      <div style={{ fontSize: 18, flexShrink: 0, color: '#a855f7' }}>🔒</div>
                      <div className={t.cardBody}>
                        <div className={t.tituloRow}>
                          <span className={t.titulo} style={{ color: '#7c3aed' }}>Tarefa confidencial</span>
                          <span style={{ fontSize: 11, background: '#f3e8ff', color: '#7c3aed', borderRadius: 4, padding: '1px 6px' }}>confidencial</span>
                        </div>
                        <div className={t.meta}>
                          {(nomCliente || tarefa.cliente_nome) && (
                            <span className={t.metaChip}>{nomCliente || tarefa.cliente_nome}</span>
                          )}
                          {tarefa.criado_por_nome && (
                            <span className={t.metaChip}>por {tarefa.criado_por_nome}</span>
                          )}
                          {tarefa.data_limite && (
                            <span className={`${t.metaPrazo} ${atrasada ? t.metaPrazoAtrasado : ''}`}>
                              {atrasada ? '⚠ ' : '📅 '}{formatDate(tarefa.data_limite)}
                              {dias !== null && tarefa.status !== 'concluido' && (
                                <> ({dias < 0 ? `${Math.abs(dias)}d atrás` : dias === 0 ? 'hoje' : `${dias}d`})</>
                              )}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className={t.cardActions}>
                        {tarefa.ja_solicitou ? (
                          <span style={{ fontSize: 11, background: '#f3f4f6', color: '#9ca3af', borderRadius: 6, padding: '3px 10px', border: '1px solid #e5e7eb', fontWeight: 500 }}>
                            Solicitado
                          </span>
                        ) : (
                          <button
                            className={styles.btnTable}
                            style={{ fontSize: 11 }}
                            onClick={() => solicitarAcesso.mutate(tarefa.id)}
                            disabled={solicitarAcesso.isPending}
                          >
                            Solicitar acesso
                          </button>
                        )}
                      </div>
                    </div>
                  </>
                ) : (
                  /* ── Card display ──────────────────────────────── */
                  <>
                    {/* Granted users list for creator/super_admin */}
                    {tarefa.confidencial && canManage && tarefa.usuarios_com_acesso_nomes.length > 0 && (
                      <div style={{ padding: '6px 12px', background: '#f5f3ff', borderBottom: '1px solid #ede9fe', display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: '#6d28d9' }}>
                          🔒 Acesso concedido a:
                        </span>
                        {tarefa.usuarios_com_acesso_nomes.map((u) => (
                          <span key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                            <span style={{ color: '#374151' }}>{u.nome}</span>
                            <button
                              className={styles.btnTable}
                              style={{ fontSize: 10, padding: '1px 6px', color: '#dc2626' }}
                              onClick={() => revogarAcesso.mutate({ tarefaId: tarefa.id, usuarioId: u.id })}
                              title="Revogar acesso"
                            >×</button>
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Pending access requests banner for creator/super_admin */}
                    {canManage && pedidos.length > 0 && (
                      <div style={{ padding: '6px 12px', background: '#fffbeb', borderBottom: '1px solid #fde68a', display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: '#92400e' }}>
                          🔔 {pedidos.length} pedido(s) de acesso:
                        </span>
                        {pedidos.map((req) => (
                          <span key={req.usuario_id} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                            <span style={{ color: '#374151' }}>{req.nome}</span>
                            <button
                              className={styles.btnPrimary}
                              style={{ fontSize: 10, padding: '1px 8px', background: '#059669' }}
                              onClick={() => concederAcesso.mutate({ tarefaId: tarefa.id, usuarioId: req.usuario_id })}
                            >✓</button>
                            <button
                              className={styles.btnTable}
                              style={{ fontSize: 10, padding: '1px 8px', color: '#dc2626' }}
                              onClick={() => revogarAcesso.mutate({ tarefaId: tarefa.id, usuarioId: req.usuario_id })}
                            >✕</button>
                          </span>
                        ))}
                      </div>
                    )}

                    <div className={t.cardTop}>
                      <button
                        className={`${t.checkBtn} ${tarefa.status === 'concluido' ? t.checked : tarefa.status === 'em_andamento' ? t.andamento : ''}`}
                        title="Avançar status"
                        onClick={() => atualizar.mutate({ id: tarefa.id, data: { status: STATUS_NEXT[tarefa.status] } })}
                      >
                        {tarefa.status === 'concluido' ? '✓' : tarefa.status === 'em_andamento' ? '◑' : '○'}
                      </button>

                      <div className={t.cardBody}>
                        <div className={t.tituloRow}>
                          {tarefa.confidencial && <span style={{ fontSize: 11, background: '#f3e8ff', color: '#7c3aed', borderRadius: 4, padding: '1px 6px', flexShrink: 0 }}>🔒 confidencial</span>}
                          {tarefa.tags?.split(',').map(t_ => t_.trim()).includes('telegram') && (
                            <span title="Criada via Telegram" style={{ fontSize: 11, background: '#e0f2fe', color: '#0369a1', borderRadius: 4, padding: '1px 6px', flexShrink: 0 }}>✈ telegram</span>
                          )}
                          <span className={t.titulo}>{tarefa.titulo}</span>
                          {tarefa.tags && !tarefa.tags.split(',').map(x => x.trim()).every(x => x === 'telegram') && (
                            <span className={t.tagChip}>{tarefa.tags.split(',').map(x => x.trim()).filter(x => x !== 'telegram').join(', ')}</span>
                          )}
                        </div>
                        <div className={t.meta}>
                          {nomCliente && <span className={t.metaChip}>{nomCliente}</span>}
                          {labelProcesso && <span className={t.metaChip}>{labelProcesso}</span>}
                          {tarefa.responsavel && <span className={t.metaChip}>→ {tarefa.responsavel}</span>}
                          {tarefa.criado_por_nome && !isCreator && (
                            <span className={t.metaChip} style={{ color: '#9ca3af' }}>por {tarefa.criado_por_nome}</span>
                          )}
                          {tarefa.data_limite && (
                            <span className={`${t.metaPrazo} ${atrasada ? t.metaPrazoAtrasado : ''}`}>
                              {atrasada ? '⚠ ' : '📅 '}{formatDate(tarefa.data_limite)}
                              {dias !== null && tarefa.status !== 'concluido' && (
                                <> ({dias < 0 ? `${Math.abs(dias)}d atrás` : dias === 0 ? 'hoje' : `${dias}d`})</>
                              )}
                            </span>
                          )}
                          {tituloAnotacao && (
                            <span className={t.metaAnotacao}>📋 {tituloAnotacao}</span>
                          )}
                          <span className={`${t.statusBadge} ${t[`status_${tarefa.status}`]}`}>
                            {STATUS_LABEL[tarefa.status]}
                          </span>
                        </div>
                      </div>

                      <div className={t.cardActions}>
                        {tarefa.descricao && (
                          <button
                            className={t.btnCollapse}
                            title={isExpanded ? 'Recolher notas' : 'Ver notas'}
                            onClick={() => setExpandedId(isExpanded ? null : tarefa.id)}
                          >
                            {isExpanded ? '▲' : '▼'}
                          </button>
                        )}
                        <button className={t.btnEdit} onClick={() => openEdit(tarefa)} title="Editar">✎</button>
                        {(!tarefa.confidencial || canManage) && (
                          <button className={styles.btnDanger}
                            onClick={() => { if (confirm('Remover tarefa?')) deletar.mutate(tarefa.id) }}>
                            ×
                          </button>
                        )}
                      </div>
                    </div>

                    {isExpanded && tarefa.descricao && (
                      <div className={t.expandedNotes}>{tarefa.descricao}</div>
                    )}
                  </>
                )}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
