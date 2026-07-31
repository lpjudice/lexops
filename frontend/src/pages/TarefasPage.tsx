import React, { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  DndContext,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  closestCenter,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { tarefasApi } from '../api/tarefas'
import type { StatusTarefa, Tarefa } from '../api/tarefas'
import { tarefaProjetosApi } from '../api/tarefaProjetos'
import type { TarefaProjeto } from '../api/tarefaProjetos'
import ProjetoCombobox from '../components/ProjetoCombobox'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import { anotacoesApi } from '../api/anotacoes'
import { useAuth } from '../contexts/AuthContext'
import ComboBox from '../components/ComboBox'
import ClienteCombobox from '../components/ClienteCombobox'
import ResponsavelComboBox from '../components/ResponsavelComboBox'
import { useFiltroMes } from '../components/useFiltroMes'
import styles from './Page.module.css'
import t from './TarefasPage.module.css'

function SortableCardWrapper({ id, isManual, children }: { id: string; isManual: boolean; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    position: 'relative',
  }
  return (
    <div ref={setNodeRef} style={style}>
      {isManual && (
        <span
          {...attributes}
          {...listeners}
          style={{
            position: 'absolute', left: -20, top: '50%', transform: 'translateY(-50%)',
            cursor: 'grab', color: '#9ca3af', fontSize: 18, lineHeight: 1,
            touchAction: 'none', userSelect: 'none', zIndex: 1,
          }}
          title="Arrastar para reordenar"
        >⠿</span>
      )}
      {children}
    </div>
  )
}

const STATUS_LABEL: Record<StatusTarefa, string> = {
  pendente: 'Pendente',
  em_andamento: 'Em andamento',
  concluido: 'Concluído',
  cancelado: 'Cancelado',
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

const CORES_PROJETO = [
  '#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f97316',
  '#eab308', '#22c55e', '#14b8a6', '#3b82f6', '#64748b',
]

interface EditForm {
  titulo: string
  descricao: string
  responsavel: string
  responsavel_email: string
  responsavel_id: string | null
  data_limite: string
  tags: string
  cliente_id: string
  processo_id: string
  projeto_id: string
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
  const [batchProjeto, setBatchProjeto] = useState('')

  // ── Gerenciar projetos ────────────────────────────────────────────────
  const [showGerenciarProjetos, setShowGerenciarProjetos] = useState(false)
  const [novoProjNome, setNovoProjNome] = useState('')
  const [novoProjCor, setNovoProjCor] = useState(CORES_PROJETO[0])
  const [editandoProj, setEditandoProj] = useState<TarefaProjeto | null>(null)

  const addRow = () => setRows((p) => [...p, { ...EMPTY_ROW }])
  const removeRow = (i: number) => setRows((p) => p.filter((_, idx) => idx !== i))
  const updateRow = (i: number, field: keyof TaskRow, val: string) =>
    setRows((p) => p.map((r, idx) => (idx === i ? { ...r, [field]: val } : r)))

  // ── Filters ───────────────────────────────────────────────────────────
  const [filtroProjeto, setFiltroProjeto] = useState('')
  const [filtroStatus, setFiltroStatus] = useState<StatusTarefa | ''>('pendente')
  const [visao, setVisao] = useState<'ativas' | 'arquivadas'>('ativas')
  const [filtroCliente, setFiltroCliente] = useState('')
  const [filtroResponsavel, setFiltroResponsavel] = useState('')
  const filtroPeriodo = useFiltroMes() // filtro por mês (padrão Despacho) — visão de concluídas
  const [sortBy, setSortBy] = useState<'manual' | 'recente' | 'prazo_asc' | 'prazo_desc' | 'titulo_az' | 'cliente_az' | 'responsavel_az'>('recente')
  const [orderedIds, setOrderedIds] = useState<string[]>([])

  // ── Status quick-menu ─────────────────────────────────────────────────
  const [statusMenuId, setStatusMenuId] = useState<string | null>(null)

  // ── Card UI state ─────────────────────────────────────────────────────
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [batchResponsavel, setBatchResponsavel] = useState<{ nome: string; email: string; id?: string | null }>({ nome: '', email: '', id: null })
  const [editForm, setEditForm] = useState<EditForm>({
    titulo: '', descricao: '', responsavel: '', responsavel_email: '', responsavel_id: null, data_limite: '', tags: '',
    cliente_id: '', processo_id: '', projeto_id: '', status: 'pendente',
  })

  // ── Queries ───────────────────────────────────────────────────────────
  const { data: tarefas = [], isLoading } = useQuery({
    queryKey: ['tarefas', filtroStatus, visao],
    queryFn: () => tarefasApi.listar({
      ...(filtroStatus && visao === 'ativas' ? { status: filtroStatus } : {}),
      arquivada: visao === 'arquivadas',
    }),
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

  const { data: projetos = [] } = useQuery({
    queryKey: ['tarefa-projetos'],
    queryFn: tarefaProjetosApi.listar,
  })

  // ── Mutations de projetos ─────────────────────────────────────────────
  const criarProjeto = useMutation({
    mutationFn: (data: { nome: string; cor: string }) => tarefaProjetosApi.criar(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tarefa-projetos'] }); setNovoProjNome(''); setNovoProjCor(CORES_PROJETO[0]) },
  })

  const atualizarProjeto = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<{ nome: string; cor: string; oculto: boolean }> }) =>
      tarefaProjetosApi.atualizar(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tarefa-projetos'] }); setEditandoProj(null) },
  })

  const deletarProjeto = useMutation({
    mutationFn: (id: string) => tarefaProjetosApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tarefa-projetos'] }),
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
      setBatchProjeto('')
      setBatchResponsavel({ nome: '', email: '' })
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

  const arquivar = useMutation({
    mutationFn: (id: string) => tarefasApi.arquivar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tarefas'] }),
  })
  const desarquivar = useMutation({
    mutationFn: (id: string) => tarefasApi.desarquivar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tarefas'] }),
  })
  const uploadAnexo = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => tarefasApi.uploadAnexo(id, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tarefas'] }),
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Erro ao anexar'),
  })
  const deletarAnexo = useMutation({
    mutationFn: (id: string) => tarefasApi.deletarAnexo(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tarefas'] }),
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

  const criarProjetoRapido = async (nome: string, cor: string): Promise<TarefaProjeto> => {
    const novo = await tarefaProjetosApi.criar({ nome, cor })
    qc.invalidateQueries({ queryKey: ['tarefa-projetos'] })
    return novo
  }

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
    if (filtroResponsavel) arr = arr.filter((t) => t.responsavel === filtroResponsavel)
    if (filtroProjeto) arr = arr.filter((t) => t.projeto_id === filtroProjeto)
    // Na visão Arquivadas o status é filtrado no cliente (o servidor não filtra por status ali)
    if (visao === 'arquivadas' && filtroStatus) arr = arr.filter((t) => t.status === filtroStatus)
    if (filtroStatus === 'concluido' && filtroPeriodo.aplicar) {
      arr = arr.filter((t) => filtroPeriodo.dentro(t.data_limite || t.updated_at))
    }

    if (sortBy === 'manual') {
      if (orderedIds.length > 0) {
        const idxMap = new Map(orderedIds.map((id, i) => [id, i]))
        arr.sort((a, b) => (idxMap.get(a.id) ?? 9999) - (idxMap.get(b.id) ?? 9999))
      } else {
        arr.sort((a, b) => (a.ordem ?? 9999) - (b.ordem ?? 9999))
      }
      return arr
    } else if (sortBy === 'recente') {
      // Em Arquivadas, "mais recente" = arquivada mais recentemente
      arr.sort((a, b) => (b.arquivada_em ?? b.created_at ?? '').localeCompare(a.arquivada_em ?? a.created_at ?? ''))
    } else if (sortBy === 'prazo_asc') {
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
    } else if (sortBy === 'titulo_az') {
      arr.sort((a, b) => a.titulo.localeCompare(b.titulo, 'pt-BR'))
    } else if (sortBy === 'cliente_az') {
      arr.sort((a, b) => {
        const na = clienteNome(a.cliente_id) || ''
        const nb = clienteNome(b.cliente_id) || ''
        return na.localeCompare(nb, 'pt-BR')
      })
    } else if (sortBy === 'responsavel_az') {
      arr.sort((a, b) => (a.responsavel ?? '').localeCompare(b.responsavel ?? '', 'pt-BR'))
    }
    return arr
  }, [tarefas, filtroCliente, filtroResponsavel, filtroProjeto, filtroStatus, visao, sortBy, orderedIds, clientes,
      filtroPeriodo.aplicar, filtroPeriodo.range.de?.getTime(), filtroPeriodo.range.ate?.getTime()]) // eslint-disable-line react-hooks/exhaustive-deps

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
      responsavel_email: tarefa.responsavel_email ?? '',
      responsavel_id: tarefa.responsavel_id ?? null,
      data_limite: tarefa.data_limite ?? '',
      tags: tarefa.tags ?? '',
      cliente_id: tarefa.cliente_id ?? '',
      processo_id: tarefa.processo_id ?? '',
      projeto_id: tarefa.projeto_id ?? '',
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
        responsavel_email: editForm.responsavel_email || null,
        responsavel_id: editForm.responsavel_id || null,
        data_limite: editForm.data_limite || null,
        tags: editForm.tags || null,
        cliente_id: editForm.cliente_id || null,
        processo_id: editForm.processo_id || null,
        projeto_id: editForm.projeto_id || null,
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
        responsavel: batchResponsavel.nome || null,
        responsavel_email: batchResponsavel.email || null,
        responsavel_id: batchResponsavel.id || null,
        data_limite: r.data_limite || null,
        tags: r.tag || null,
        cliente_id: batchCliente || null,
        processo_id: batchProcesso || null,
        projeto_id: batchProjeto || null,
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

  // ── Drag-to-reorder (modo manual) ─────────────────────────────────────
  const reordenar = useMutation({
    mutationFn: (ids: string[]) => tarefasApi.reordenar(ids),
  })

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
  )

  // Inicializa/sincroniza orderedIds quando as tarefas chegam do servidor
  useEffect(() => {
    if (tarefas.length > 0 && orderedIds.length === 0) {
      const sorted = [...tarefas].sort((a, b) => (a.ordem ?? 9999) - (b.ordem ?? 9999))
      setOrderedIds(sorted.map((t) => t.id))
    }
  }, [tarefas]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = orderedIds.indexOf(String(active.id))
    const newIndex = orderedIds.indexOf(String(over.id))
    if (oldIndex === -1 || newIndex === -1) return
    const newIds = arrayMove(orderedIds, oldIndex, newIndex)
    setOrderedIds(newIds)
    reordenar.mutate(newIds)
  }

  function moverParaCima(id: string) {
    const idx = orderedIds.indexOf(id)
    if (idx <= 0) return
    const newIds = arrayMove(orderedIds, idx, idx - 1)
    setOrderedIds(newIds)
    reordenar.mutate(newIds)
  }

  function moverParaBaixo(id: string) {
    const idx = orderedIds.indexOf(id)
    if (idx === -1 || idx >= orderedIds.length - 1) return
    const newIds = arrayMove(orderedIds, idx, idx + 1)
    setOrderedIds(newIds)
    reordenar.mutate(newIds)
  }

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
          <div style={{ display: 'inline-flex', border: '1px solid #e5e7eb', borderRadius: 999, overflow: 'hidden' }}>
            {(['ativas', 'arquivadas'] as const).map((v) => (
              <button key={v}
                onClick={() => { setVisao(v); if (v === 'arquivadas') { setViewMode('list'); setShowForm(false); setSortBy('recente') } }}
                style={{
                  padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                  background: visao === v ? '#1d1e20' : '#fff', color: visao === v ? '#fff' : '#6b7280',
                }}>
                {v === 'ativas' ? 'Ativas' : '🗄 Arquivadas'}
              </button>
            ))}
          </div>
          {visao === 'ativas' && (
            <>
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
            </>
          )}
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
            <label className={styles.formLabel}>Projeto (opcional)</label>
            <ProjetoCombobox
              projetos={projetos}
              value={batchProjeto}
              onChange={setBatchProjeto}
              onCriar={criarProjetoRapido}
            />
          </div>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Responsável (opcional)</label>
            <ResponsavelComboBox
              value={batchResponsavel}
              onChange={setBatchResponsavel}
            />
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
          {/* Status tabs + ordenação */}
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
              <option value="manual">⠿ Ordem manual</option>
              <option value="recente">Mais recentes primeiro</option>
              <option value="prazo_asc">Prazo ↑ (mais próximo)</option>
              <option value="prazo_desc">Prazo ↓ (mais distante)</option>
              <option value="titulo_az">Tarefa A→Z</option>
              <option value="cliente_az">Cliente A→Z</option>
              <option value="responsavel_az">Responsável A→Z</option>
            </select>
          </div>

          {/* Filtros secundários */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ width: 260 }}>
              <ClienteCombobox
                value={filtroCliente}
                onChange={setFiltroCliente}
                clientes={clientes}
                onCreateCliente={criarClienteRapido}
              />
            </div>
            <select
              value={filtroResponsavel}
              onChange={(e) => setFiltroResponsavel(e.target.value)}
              style={{ fontSize: 12, padding: '5px 10px', borderRadius: 999, border: '1px solid #e5e7eb', background: '#fff', color: filtroResponsavel ? '#1d1e20' : '#9ca3af', cursor: 'pointer', fontFamily: 'inherit' }}
            >
              <option value="">Responsável (todos)</option>
              {[...new Set(tarefas.map(t => t.responsavel).filter(Boolean))].sort().map(r => (
                <option key={r!} value={r!}>{r}</option>
              ))}
            </select>
            {projetos.filter(p => !p.oculto).length > 0 && (
              <select
                value={filtroProjeto}
                onChange={(e) => setFiltroProjeto(e.target.value)}
                style={{
                  fontSize: 12, padding: '5px 10px', borderRadius: 999, cursor: 'pointer', fontFamily: 'inherit',
                  border: filtroProjeto
                    ? `2px solid ${projetos.find(p => p.id === filtroProjeto)?.cor ?? '#6366f1'}`
                    : '1px solid #e5e7eb',
                  background: filtroProjeto
                    ? `${projetos.find(p => p.id === filtroProjeto)?.cor ?? '#6366f1'}15`
                    : '#fff',
                  color: filtroProjeto
                    ? (projetos.find(p => p.id === filtroProjeto)?.cor ?? '#6366f1')
                    : '#9ca3af',
                  fontWeight: filtroProjeto ? 700 : 400,
                }}
              >
                <option value="">Projeto (todos)</option>
                {projetos.filter(p => !p.oculto).map(p => (
                  <option key={p.id} value={p.id}>{p.nome}</option>
                ))}
              </select>
            )}
            {(filtroCliente || filtroResponsavel || filtroProjeto) && (
              <button
                onClick={() => { setFiltroCliente(''); setFiltroResponsavel(''); setFiltroProjeto('') }}
                style={{ fontSize: 11, color: '#9ca3af', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
              >
                Limpar filtros
              </button>
            )}
            <button
              onClick={() => setShowGerenciarProjetos(true)}
              style={{ fontSize: 11, color: '#6366f1', background: 'none', border: '1px solid #e0e7ff', borderRadius: 999, padding: '4px 10px', cursor: 'pointer', fontFamily: 'inherit', marginLeft: 'auto' }}
            >
              ⊞ Projetos
            </button>
          </div>
        </div>
      )}

      {/* Filtro por mês — visão de tarefas concluídas (padrão Despacho) */}
      {viewMode === 'list' && filtroStatus === 'concluido' && filtroPeriodo.node}

      {/* ── Modal: Gerenciar Projetos ────────────────────────────────── */}
      {showGerenciarProjetos && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={(e) => { if (e.target === e.currentTarget) setShowGerenciarProjetos(false) }}>
          <div style={{ background: '#fff', borderRadius: 16, padding: 28, minWidth: 360, maxWidth: 480, width: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Projetos</h2>
              <button onClick={() => setShowGerenciarProjetos(false)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#9ca3af' }}>×</button>
            </div>

            {/* Lista de projetos existentes */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
              {projetos.length === 0 && <p style={{ fontSize: 13, color: '#9ca3af', margin: 0 }}>Nenhum projeto criado ainda.</p>}
              {projetos.map(proj => (
                <div key={proj.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: 10, border: '1px solid #e5e7eb', background: proj.oculto ? '#fafafa' : '#fff' }}>
                  <span style={{ width: 14, height: 14, borderRadius: '50%', background: proj.cor, flexShrink: 0, display: 'inline-block' }} />
                  {editandoProj?.id === proj.id ? (
                    <>
                      <input
                        value={editandoProj.nome}
                        onChange={(e) => setEditandoProj({ ...editandoProj, nome: e.target.value })}
                        style={{ flex: 1, fontSize: 13, padding: '3px 8px', borderRadius: 6, border: '1px solid #e5e7eb', fontFamily: 'inherit' }}
                        autoFocus
                      />
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {CORES_PROJETO.map(c => (
                          <button key={c} onClick={() => setEditandoProj({ ...editandoProj, cor: c })}
                            style={{ width: 16, height: 16, borderRadius: '50%', background: c, border: editandoProj.cor === c ? '2px solid #1d1e20' : '2px solid transparent', cursor: 'pointer', padding: 0 }} />
                        ))}
                      </div>
                      <button onClick={() => atualizarProjeto.mutate({ id: proj.id, data: { nome: editandoProj.nome, cor: editandoProj.cor } })}
                        style={{ fontSize: 12, background: '#6366f1', color: '#fff', border: 'none', borderRadius: 6, padding: '3px 10px', cursor: 'pointer', fontFamily: 'inherit' }}>
                        Salvar
                      </button>
                      <button onClick={() => setEditandoProj(null)}
                        style={{ fontSize: 12, background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: '#6b7280', fontFamily: 'inherit' }}>
                        ×
                      </button>
                    </>
                  ) : (
                    <>
                      <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: proj.oculto ? '#9ca3af' : '#1d1e20' }}>
                        {proj.nome}
                        {proj.oculto && <span style={{ fontSize: 11, marginLeft: 6, color: '#9ca3af' }}>(oculto)</span>}
                      </span>
                      <button onClick={() => setEditandoProj(proj)}
                        style={{ fontSize: 12, background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: '#6b7280', fontFamily: 'inherit' }}>
                        ✎
                      </button>
                      <button
                        onClick={() => atualizarProjeto.mutate({ id: proj.id, data: { oculto: !proj.oculto } })}
                        title={proj.oculto ? 'Mostrar projeto' : 'Ocultar projeto'}
                        style={{ fontSize: 12, background: 'none', border: '1px solid #e5e7eb', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: '#6b7280', fontFamily: 'inherit' }}>
                        {proj.oculto ? '👁' : '🙈'}
                      </button>
                      <button
                        onClick={() => { if (confirm(`Excluir projeto "${proj.nome}"? As tarefas não serão excluídas.`)) deletarProjeto.mutate(proj.id) }}
                        style={{ fontSize: 12, background: 'none', border: '1px solid #fecaca', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: '#dc2626', fontFamily: 'inherit' }}>
                        ×
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>

            {/* Form criar novo projeto */}
            <div style={{ borderTop: '1px solid #f3f4f6', paddingTop: 16 }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', margin: '0 0 10px' }}>Novo projeto</p>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  value={novoProjNome}
                  onChange={(e) => setNovoProjNome(e.target.value)}
                  placeholder="Nome do projeto"
                  style={{ flex: 1, minWidth: 140, fontSize: 13, padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb', fontFamily: 'inherit' }}
                  onKeyDown={(e) => { if (e.key === 'Enter' && novoProjNome.trim()) criarProjeto.mutate({ nome: novoProjNome.trim(), cor: novoProjCor }) }}
                />
                <div style={{ display: 'flex', gap: 4 }}>
                  {CORES_PROJETO.map(c => (
                    <button key={c} onClick={() => setNovoProjCor(c)}
                      style={{ width: 18, height: 18, borderRadius: '50%', background: c, border: novoProjCor === c ? '2px solid #1d1e20' : '2px solid transparent', cursor: 'pointer', padding: 0 }} />
                  ))}
                </div>
                <button
                  onClick={() => { if (novoProjNome.trim()) criarProjeto.mutate({ nome: novoProjNome.trim(), cor: novoProjCor }) }}
                  disabled={!novoProjNome.trim() || criarProjeto.isPending}
                  style={{ fontSize: 13, background: '#6366f1', color: '#fff', border: 'none', borderRadius: 8, padding: '6px 16px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                  Criar
                </button>
              </div>
            </div>
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
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={tarefasFiltradas.map((t) => t.id)} strategy={verticalListSortingStrategy}>
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
              <SortableCardWrapper key={tarefa.id} id={tarefa.id} isManual={sortBy === 'manual'}>
              <div
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
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Projeto</label>
                      <ProjetoCombobox
                        projetos={projetos}
                        value={editForm.projeto_id}
                        onChange={(v) => setEditForm({ ...editForm, projeto_id: v })}
                        onCriar={criarProjetoRapido}
                      />
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
                      <ResponsavelComboBox
                        value={{ nome: editForm.responsavel, email: editForm.responsavel_email, id: editForm.responsavel_id }}
                        onChange={(v) => setEditForm({ ...editForm, responsavel: v.nome, responsavel_email: v.email, responsavel_id: v.id ?? null })}
                      />
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
                      {/* Status quick-menu */}
                      <div style={{ position: 'relative', flexShrink: 0 }}>
                        <button
                          className={`${t.checkBtn} ${tarefa.status === 'concluido' ? t.checked : tarefa.status === 'em_andamento' ? t.andamento : ''}`}
                          title="Alterar status"
                          onClick={() => setStatusMenuId(statusMenuId === tarefa.id ? null : tarefa.id)}
                        >
                          {tarefa.status === 'concluido' ? '✓' : tarefa.status === 'em_andamento' ? '◑' : '○'}
                        </button>
                        {statusMenuId === tarefa.id && (
                          <div
                            style={{ position: 'absolute', left: 0, top: '110%', zIndex: 20, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, boxShadow: '0 4px 16px rgba(0,0,0,.12)', padding: 4, minWidth: 160 }}
                            onMouseLeave={() => setStatusMenuId(null)}
                          >
                            {tarefa.status !== 'em_andamento' && (
                              <button onClick={() => { atualizar.mutate({ id: tarefa.id, data: { status: 'em_andamento' } }); setStatusMenuId(null) }}
                                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '7px 12px', fontSize: 13, cursor: 'pointer', background: 'none', border: 'none', borderRadius: 7, color: '#d97706', fontFamily: 'inherit' }}>
                                ◑ Em Andamento
                              </button>
                            )}
                            <button onClick={() => { atualizar.mutate({ id: tarefa.id, data: { status: 'concluido' } }); setStatusMenuId(null) }}
                              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '7px 12px', fontSize: 13, cursor: 'pointer', background: 'none', border: 'none', borderRadius: 7, color: '#059669', fontFamily: 'inherit' }}>
                              ✓ Concluído
                            </button>
                            {tarefa.status !== 'pendente' && (
                              <button onClick={() => { atualizar.mutate({ id: tarefa.id, data: { status: 'pendente' } }); setStatusMenuId(null) }}
                                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '7px 12px', fontSize: 13, cursor: 'pointer', background: 'none', border: 'none', borderRadius: 7, color: '#9ca3af', fontFamily: 'inherit' }}>
                                ○ Pendente
                              </button>
                            )}
                          </div>
                        )}
                      </div>

                      <div className={t.cardBody}>
                        <div className={t.tituloRow}>
                          {tarefa.projeto_nome && (
                            <span style={{
                              fontSize: 11, fontWeight: 700, borderRadius: 4, padding: '2px 8px', flexShrink: 0,
                              background: tarefa.projeto_cor ? `${tarefa.projeto_cor}22` : '#e0e7ff',
                              color: tarefa.projeto_cor ?? '#6366f1',
                              border: `1px solid ${tarefa.projeto_cor ?? '#6366f1'}44`,
                              letterSpacing: '0.02em',
                            }}>
                              {tarefa.projeto_nome}
                            </span>
                          )}
                          {tarefa.confidencial && <span style={{ fontSize: 11, background: '#f3e8ff', color: '#7c3aed', borderRadius: 4, padding: '1px 6px', flexShrink: 0 }}>🔒 confidencial</span>}
                          {tarefa.tags?.split(',').map(t_ => t_.trim()).includes('telegram') && (
                            <span title="Criada via Telegram" style={{ fontSize: 11, background: '#e0f2fe', color: '#0369a1', borderRadius: 4, padding: '1px 6px', flexShrink: 0 }}>✈ telegram</span>
                          )}
                          {tarefa.criado_automaticamente && (
                            <span title="Criada automaticamente pelo gestor jurídico (Despacho)" style={{ fontSize: 11, background: '#f3e8ff', color: '#7c3aed', borderRadius: 4, padding: '1px 6px', flexShrink: 0 }}>🤖 automático</span>
                          )}
                          {tarefa.prazo_id && (
                            <a href={`/prazos?destaque=${tarefa.prazo_id}`} title="Ver prazo vinculado" onClick={(e) => e.stopPropagation()}
                              style={{ fontSize: 11, background: '#dbeafe', color: '#1d4ed8', borderRadius: 4, padding: '1px 6px', flexShrink: 0, textDecoration: 'none' }}>
                              🔗 prazo
                            </a>
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
                          {tarefa.criado_por_nome && (
                            <span className={t.metaChip} style={{ color: '#9ca3af' }}>por {tarefa.criado_por_nome}</span>
                          )}
                          {tarefa.created_at && (
                            <span className={t.metaChip} style={{ color: '#9ca3af' }}>
                              {new Date(tarefa.created_at).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })}
                            </span>
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
                        {sortBy === 'manual' && (
                          <>
                            <button
                              className={t.btnReorder}
                              title="Mover para cima"
                              onClick={() => moverParaCima(tarefa.id)}
                            >↑</button>
                            <button
                              className={t.btnReorder}
                              title="Mover para baixo"
                              onClick={() => moverParaBaixo(tarefa.id)}
                            >↓</button>
                          </>
                        )}
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
                          <label className={t.btnEdit} title="Anexar arquivo" style={{ cursor: 'pointer' }}>
                            📎
                            <input type="file" style={{ display: 'none' }} disabled={uploadAnexo.isPending}
                              onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadAnexo.mutate({ id: tarefa.id, file: f }); e.currentTarget.value = '' }} />
                          </label>
                        )}
                        {visao === 'arquivadas' ? (
                          <button className={t.btnEdit} title="Desarquivar" disabled={desarquivar.isPending}
                            onClick={() => desarquivar.mutate(tarefa.id)}>↩</button>
                        ) : (
                          <button className={t.btnEdit} title="Arquivar" disabled={arquivar.isPending}
                            onClick={() => arquivar.mutate(tarefa.id)}>🗄</button>
                        )}
                        {(!tarefa.confidencial || canManage) && (
                          <button className={styles.btnDanger}
                            onClick={() => { if (confirm('Remover tarefa?')) deletar.mutate(tarefa.id) }}>
                            ×
                          </button>
                        )}
                      </div>
                    </div>

                    {(tarefa.anexos && tarefa.anexos.length > 0) && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                        {tarefa.anexos.map((a) => (
                          <span key={a.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, background: '#eff6ff', color: '#1d4ed8', borderRadius: 6, padding: '2px 6px', maxWidth: 220 }}>
                            <a href={a.drive_link || '#'} target="_blank" rel="noreferrer" title={a.nome_arquivo}
                              style={{ color: 'inherit', textDecoration: 'none', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 180 }}>📎 {a.nome_arquivo}</a>
                            <button onClick={() => deletarAnexo.mutate(a.id)} title="Remover"
                              style={{ border: 'none', background: 'none', color: '#93c5fd', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}>×</button>
                          </span>
                        ))}
                      </div>
                    )}

                    {isExpanded && tarefa.descricao && (
                      <div className={t.expandedNotes}>{tarefa.descricao}</div>
                    )}
                  </>
                )}
              </div>
              </SortableCardWrapper>
            )
          })}
        </div>
          </SortableContext>
        </DndContext>
      ))}
    </div>
  )
}
