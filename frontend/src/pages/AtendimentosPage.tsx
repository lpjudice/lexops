import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Lock, LockOpen } from 'lucide-react'
import { anotacoesApi } from '../api/anotacoes'
import type { AnotacaoCreate, TipoAnotacao } from '../api/anotacoes'
import { tarefasApi } from '../api/tarefas'
import type { Tarefa } from '../api/tarefas'
import { clientesApi } from '../api/clientes'
import AnamneseForm from '../components/AnamneseForm'
import ClienteCombobox from '../components/ClienteCombobox'
import { useAuth } from '../contexts/AuthContext'
import styles from './Page.module.css'
import at from './AtendimentosPage.module.css'

interface TaskItem { titulo: string; descricao: string; data_limite: string }

const TIPOS_ATENDIMENTO: TipoAnotacao[] = ['reuniao', 'ligacao', 'whatsapp', 'anamnese', 'reuniao_todo', 'outro']

const TIPO_ICON: Record<string, string> = {
  reuniao: '🤝', ligacao: '📞', whatsapp: '💬', anamnese: '📋', reuniao_todo: '✅', outro: '📝',
}

const TIPO_LABEL: Record<string, string> = {
  reuniao: 'Reunião', ligacao: 'Ligação', whatsapp: 'WhatsApp', anamnese: 'Anamnese', reuniao_todo: 'Reunião + To Do', outro: 'Outro',
}

function formatDate(d: string) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function AtendimentosPage() {
  const qc = useQueryClient()
  const { isSuperAdmin } = useAuth()
  const [showForm, setShowForm] = useState(false)
  const [filtroTipo, setFiltroTipo] = useState<TipoAnotacao | ''>('')
  const [filtroCliente, setFiltroCliente] = useState('')
  const [filtroDataInicio, setFiltroDataInicio] = useState('')
  const [filtroDataFim, setFiltroDataFim] = useState('')
  const [form, setForm] = useState<AnotacaoCreate>({
    cliente_id: '',
    tipo: 'reuniao',
    data_evento: new Date().toISOString().slice(0, 10),
    titulo: '',
    texto: '',
  })

  // ── Expand / edit state ───────────────────────────────────────────────
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Omit<AnotacaoCreate, 'cliente_id'>>({
    tipo: 'reuniao',
    data_evento: '',
    titulo: '',
    texto: '',
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const { data: todasTarefas = [] } = useQuery({
    queryKey: ['tarefas'],
    queryFn: () => tarefasApi.listar(),
  })

  const { data: todasAnotacoes = [], isLoading } = useQuery({
    queryKey: ['anotacoes-atendimentos'],
    queryFn: () => anotacoesApi.listar(),
  })

  const atendimentos = todasAnotacoes.filter((a) => {
    if (!TIPOS_ATENDIMENTO.includes(a.tipo as TipoAnotacao)) return false
    if (filtroTipo && a.tipo !== filtroTipo) return false
    if (filtroCliente) {
      const nome = clienteNome(a.cliente_id).toLowerCase()
      if (!nome.includes(filtroCliente.toLowerCase())) return false
    }
    if (filtroDataInicio && a.data_evento && a.data_evento < filtroDataInicio) return false
    if (filtroDataFim && a.data_evento && a.data_evento > filtroDataFim) return false
    return true
  })

  const [showAnamnese, setShowAnamnese] = useState(false)
  const [tasks, setTasks] = useState<TaskItem[]>([{ titulo: '', descricao: '', data_limite: '' }])

  const addTask = () => setTasks((p) => [...p, { titulo: '', descricao: '', data_limite: '' }])
  const removeTask = (i: number) => setTasks((p) => p.filter((_, idx) => idx !== i))
  const updateTask = (i: number, field: keyof TaskItem, val: string) =>
    setTasks((p) => p.map((t, idx) => idx === i ? { ...t, [field]: val } : t))

  const criar = useMutation({
    mutationFn: async (data: AnotacaoCreate) => {
      const anotacao = await anotacoesApi.criar(data)
      if (data.tipo === 'reuniao_todo') {
        for (const tk of tasks.filter((t) => t.titulo.trim())) {
          await tarefasApi.criar({
            titulo: tk.titulo.trim(),
            descricao: tk.descricao || null,
            data_limite: tk.data_limite || null,
            cliente_id: data.cliente_id || null,
            anotacao_id: anotacao.id,
          })
        }
      }
      return anotacao
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['anotacoes-atendimentos'] })
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      setShowForm(false)
      setShowAnamnese(false)
      setTasks([{ titulo: '', descricao: '', data_limite: '' }])
      setForm({ cliente_id: '', tipo: 'reuniao', data_evento: new Date().toISOString().slice(0, 10), titulo: '', texto: '' })
    },
  })

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<AnotacaoCreate> }) =>
      anotacoesApi.atualizar(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['anotacoes-atendimentos'] })
      setEditingId(null)
    },
  })

  const deletar = useMutation({
    mutationFn: (id: string) => anotacoesApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['anotacoes-atendimentos'] }),
  })

  const toggleConfidencial = useMutation({
    mutationFn: ({ id, confidencial }: { id: string; confidencial: boolean }) =>
      anotacoesApi.atualizar(id, { confidencial }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['anotacoes-atendimentos'] }),
  })

  const clienteNome = (id: string) => clientes.find((c) => c.id === id)?.nome ?? '—'

  const criarCliente = async (raw: string): Promise<string> => {
    const [nome, tipo] = raw.split('|')
    const c = await clientesApi.criar({ nome, tipo: (tipo as 'PF' | 'PJ') ?? 'PF', incompleto: true })
    qc.invalidateQueries({ queryKey: ['clientes'] })
    return c.id
  }

  const openEdit = (a: typeof todasAnotacoes[0]) => {
    setEditingId(a.id)
    setEditForm({ tipo: a.tipo as TipoAnotacao, data_evento: a.data_evento ?? '', titulo: a.titulo ?? '', texto: a.texto })
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Atendimentos</h1>
        <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Novo Atendimento'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); if (!form.cliente_id) return; criar.mutate(form) }}
          className={styles.form}
        >
          <div className={at.twoCol}>
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
              <label className={styles.formLabel}>Tipo</label>
              <select className={styles.input} value={form.tipo}
                onChange={(e) => {
                  const tp = e.target.value as TipoAnotacao
                  setForm({ ...form, tipo: tp, texto: '' })
                  setShowAnamnese(tp === 'anamnese')
                }}>
                {TIPOS_ATENDIMENTO.map((tp) => (
                  <option key={tp} value={tp}>{TIPO_LABEL[tp]}</option>
                ))}
              </select>
            </div>
          </div>
          <div className={at.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Data *</label>
              <input type="date" className={styles.input} value={form.data_evento} required
                onChange={(e) => setForm({ ...form, data_evento: e.target.value })} />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Título</label>
              <input className={styles.input} value={form.titulo ?? ''}
                onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
            </div>
          </div>
          {showAnamnese ? (
            <AnamneseForm
              onSave={(texto, titulo) => {
                criar.mutate({ ...form, texto, titulo: titulo || form.titulo || 'Anamnese' })
              }}
              onCancel={() => { setShowAnamnese(false); setForm({ ...form, tipo: 'reuniao', texto: '' }) }}
              isSaving={criar.isPending}
            />
          ) : (
            <>
              <div className={styles.formRow}>
                <label className={styles.formLabel}>
                  {form.tipo === 'reuniao_todo' ? 'Anotações da reunião' : 'Texto *'}
                </label>
                <textarea className={styles.input} rows={4} value={form.texto}
                  required={form.tipo !== 'reuniao_todo'}
                  placeholder={form.tipo === 'reuniao_todo' ? 'Resumo da reunião, decisões, contexto...' : ''}
                  onChange={(e) => setForm({ ...form, texto: e.target.value })} />
              </div>

              {form.tipo === 'reuniao_todo' && (
                <div className={at.tasksBlock}>
                  <div className={at.tasksHeader}>
                    <span className={at.tasksTitle}>To Dos</span>
                    <button type="button" className={at.btnAddTask} onClick={addTask}>+ Adicionar</button>
                  </div>
                  {tasks.map((tk, i) => (
                    <div key={i} className={at.taskRow}>
                      <div className={at.taskFields}>
                        <input className={styles.input} placeholder="Tarefa *"
                          value={tk.titulo}
                          onChange={(e) => updateTask(i, 'titulo', e.target.value)} />
                        <input className={styles.input} placeholder="Detalhes (opcional)"
                          value={tk.descricao}
                          onChange={(e) => updateTask(i, 'descricao', e.target.value)} />
                        <input type="date" className={styles.input} title="Prazo (opcional)"
                          value={tk.data_limite}
                          onChange={(e) => updateTask(i, 'data_limite', e.target.value)} />
                      </div>
                      {tasks.length > 1 && (
                        <button type="button" className={at.btnRemoveTask} onClick={() => removeTask(i)}>×</button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
                {criar.isPending ? 'Salvando...' : 'Salvar'}
              </button>
            </>
          )}
        </form>
      )}

      {/* Filtros */}
      <div className={at.filtrosWrapper}>
        <div className={at.filtrosTop}>
          <input
            className={at.filtroSelect}
            placeholder="Filtrar por cliente..."
            value={filtroCliente}
            onChange={(e) => setFiltroCliente(e.target.value)}
          />
          <input type="date" className={at.filtroData} value={filtroDataInicio}
            onChange={(e) => setFiltroDataInicio(e.target.value)} title="De" />
          <span className={at.filtroSep}>→</span>
          <input type="date" className={at.filtroData} value={filtroDataFim}
            onChange={(e) => setFiltroDataFim(e.target.value)} title="Até" />
          {(filtroCliente || filtroDataInicio || filtroDataFim) && (
            <button className={at.filtroLimpar}
              onClick={() => { setFiltroCliente(''); setFiltroDataInicio(''); setFiltroDataFim('') }}>
              Limpar
            </button>
          )}
        </div>
        <div className={at.filtros}>
          <button className={`${at.filtroBtn} ${filtroTipo === '' ? at.filtroBtnActive : ''}`}
            onClick={() => setFiltroTipo('')}>Todos</button>
          {TIPOS_ATENDIMENTO.map((tp) => (
            <button key={tp}
              className={`${at.filtroBtn} ${filtroTipo === tp ? at.filtroBtnActive : ''}`}
              onClick={() => setFiltroTipo(tp)}>
              {TIPO_ICON[tp]} {TIPO_LABEL[tp]}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : atendimentos.length === 0 ? (
        <p className={styles.empty}>Nenhum atendimento registrado.</p>
      ) : (
        <div className={at.lista}>
          {atendimentos.map((a) => {
            const tarefasVinculadas: Tarefa[] = todasTarefas.filter((t) => t.anotacao_id === a.id)
            const isExpanded = expandedId === a.id

            return (
            <div key={a.id} className={at.card}>
              {editingId === a.id ? (
                /* ── Inline edit ───────────────────────────────────── */
                <div className={at.editForm}>
                  <div className={at.twoCol}>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Tipo</label>
                      <select className={styles.input} value={editForm.tipo}
                        onChange={(e) => setEditForm({ ...editForm, tipo: e.target.value as TipoAnotacao })}>
                        {TIPOS_ATENDIMENTO.map((tp) => (
                          <option key={tp} value={tp}>{TIPO_LABEL[tp]}</option>
                        ))}
                      </select>
                    </div>
                    <div className={styles.formRow}>
                      <label className={styles.formLabel}>Data</label>
                      <input type="date" className={styles.input} value={editForm.data_evento}
                        onChange={(e) => setEditForm({ ...editForm, data_evento: e.target.value })} />
                    </div>
                  </div>
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Título</label>
                    <input className={styles.input} value={editForm.titulo ?? ''}
                      onChange={(e) => setEditForm({ ...editForm, titulo: e.target.value })} />
                  </div>
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Texto</label>
                    <textarea className={styles.input} rows={5} value={editForm.texto}
                      onChange={(e) => setEditForm({ ...editForm, texto: e.target.value })} />
                  </div>
                  <div className={at.editAcoes}>
                    <button className={styles.btnPrimary} disabled={atualizar.isPending}
                      onClick={() => atualizar.mutate({ id: a.id, data: editForm })}>
                      {atualizar.isPending ? 'Salvando...' : 'Salvar'}
                    </button>
                    <button className={styles.btnTable} onClick={() => setEditingId(null)}>Cancelar</button>
                  </div>
                </div>
              ) : (
                /* ── Normal display ────────────────────────────────── */
                <>
                  <div className={at.cardHeader}
                    onClick={() => setExpandedId(isExpanded ? null : a.id)}
                    style={{ cursor: (a.texto || tarefasVinculadas.length > 0) ? 'pointer' : 'default' }}>
                    <div className={at.cardLeft}>
                      <span className={at.tipoIcon}>{TIPO_ICON[a.tipo]}</span>
                      <div>
                        <div className={at.cardTitulo}>
                          {a.titulo || TIPO_LABEL[a.tipo]}
                          {a.confidencial && (
                            <span style={{ marginLeft: 6, color: '#9333ea', fontSize: 11, fontWeight: 600, verticalAlign: 'middle' }}>
                              🔒 confidencial
                            </span>
                          )}
                        </div>
                        <div className={at.cardMeta}>
                          <Link to={`/clientes/${a.cliente_id}`} className={at.clienteLink}
                            onClick={(e) => e.stopPropagation()}>
                            {clienteNome(a.cliente_id)}
                          </Link>
                          {tarefasVinculadas.length > 0 && (
                            <span className={at.tarefasBadge}>
                              ✓ {tarefasVinculadas.length} tarefa{tarefasVinculadas.length > 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className={at.cardRight}>
                      <span className={at.data}>{formatDate(a.data_evento)}</span>
                      {(a.texto || tarefasVinculadas.length > 0) && (
                        <span className={at.chevron}>{isExpanded ? '▲' : '▼'}</span>
                      )}
                      {/* Super-admin can toggle confidential on any annotation */}
                      {isSuperAdmin && (
                        <button
                          title={a.confidencial ? 'Tornar pública' : 'Tornar confidencial'}
                          onClick={(e) => { e.stopPropagation(); toggleConfidencial.mutate({ id: a.id, confidencial: !a.confidencial }) }}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px', color: a.confidencial ? '#9333ea' : '#9ca3af' }}
                        >
                          {a.confidencial ? <Lock size={13} /> : <LockOpen size={13} />}
                        </button>
                      )}
                      <button className={at.btnEdit}
                        onClick={(e) => { e.stopPropagation(); openEdit(a) }}
                        title="Editar">✎</button>
                      <button className={styles.btnDanger}
                        onClick={(e) => { e.stopPropagation(); if (confirm('Remover atendimento?')) deletar.mutate(a.id) }}>
                        ×
                      </button>
                    </div>
                  </div>
                  {isExpanded && (a.texto || tarefasVinculadas.length > 0) && (
                    <div className={at.cardBody}>
                      {a.texto && <p className={at.cardTexto}>{a.texto}</p>}
                      {tarefasVinculadas.length > 0 && (
                        <div className={at.tarefasSection}>
                          <div className={at.tarefasSectionTitle}>Tarefas vinculadas</div>
                          {tarefasVinculadas.map((t) => (
                            <div key={t.id} className={at.tarefaItem}>
                              <span className={`${at.tarefaStatus} ${t.status === 'concluido' ? at.tarefaConcluida : ''}`}>
                                {t.status === 'concluido' ? '✓' : '○'}
                              </span>
                              <div className={at.tarefaInfo}>
                                <span className={at.tarefaTitulo}>{t.titulo}</span>
                                {t.data_limite && (
                                  <span className={at.tarefaData}>
                                    prazo: {new Date(t.data_limite + 'T12:00:00').toLocaleDateString('pt-BR')}
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
