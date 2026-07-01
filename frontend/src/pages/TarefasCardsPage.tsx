import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { tarefaCardsApi } from '../api/tarefaCards'
import type { StatusTarefaCard, TarefaCard } from '../api/tarefaCards'
import { tarefaProjetosApi } from '../api/tarefaProjetos'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import { usuariosApi } from '../api/usuarios'
import { useAuth } from '../contexts/AuthContext'
import ClienteCombobox from '../components/ClienteCombobox'
import ComboBox from '../components/ComboBox'
import ProjetoCombobox from '../components/ProjetoCombobox'
import ResponsavelComboBox from '../components/ResponsavelComboBox'
import styles from './Page.module.css'
import cs from './TarefasCardsPage.module.css'

const STATUS_OPTS: { value: StatusTarefaCard; label: string }[] = [
  { value: 'pendente', label: 'Pendente' },
  { value: 'em_andamento', label: 'Em andamento' },
  { value: 'concluido', label: 'Concluído' },
  { value: 'cancelado', label: 'Cancelado' },
]

function fmtData(d?: string | null) {
  if (!d) return null
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}
function vencido(d?: string | null) {
  if (!d) return false
  return new Date(d + 'T23:59:59').getTime() < Date.now()
}

interface FormState {
  titulo: string
  descricao: string
  cliente_id: string
  processo_id: string
  projeto_id: string
  responsavel: { nome: string; email: string }
  data_limite: string
  confidencial: boolean
  subtasks: string[]
}

const emptyForm: FormState = {
  titulo: '', descricao: '', cliente_id: '', processo_id: '', projeto_id: '',
  responsavel: { nome: '', email: '' }, data_limite: '', confidencial: false, subtasks: [''],
}

export default function TarefasCardsPage() {
  const qc = useQueryClient()
  const { usuario, isSuperAdmin } = useAuth()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [filtroProjeto, setFiltroProjeto] = useState('')
  const [novaSubtask, setNovaSubtask] = useState<Record<string, string>>({})

  const { data: cards = [], isLoading } = useQuery({
    queryKey: ['tarefa-cards'],
    queryFn: () => tarefaCardsApi.listar(),
  })
  const { data: projetos = [] } = useQuery({ queryKey: ['tarefa-projetos'], queryFn: tarefaProjetosApi.listar })
  const { data: clientes = [] } = useQuery({ queryKey: ['clientes'], queryFn: () => clientesApi.listar() })
  const { data: processos = [] } = useQuery({ queryKey: ['processos'], queryFn: () => processosApi.listar() })
  const { data: usuarios = [] } = useQuery({ queryKey: ['usuarios'], queryFn: usuariosApi.listar })

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
  const addSubtask = useMutation({
    mutationFn: ({ id, texto }: { id: string; texto: string }) => tarefaCardsApi.addSubtask(id, texto),
    onSuccess: invalidate,
  })
  const toggleSubtask = useMutation({
    mutationFn: ({ id, concluida }: { id: string; concluida: boolean }) => tarefaCardsApi.toggleSubtask(id, concluida),
    onSuccess: invalidate,
  })
  const delSubtask = useMutation({ mutationFn: tarefaCardsApi.deletarSubtask, onSuccess: invalidate })
  const agendar = useMutation({
    mutationFn: tarefaCardsApi.agendarCalendario,
    onSuccess: () => { invalidate(); alert('Agendado no Google Calendar ✅') },
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Erro ao agendar'),
  })
  const solicitar = useMutation({
    mutationFn: tarefaCardsApi.solicitarAcesso,
    onSuccess: (r) => { invalidate(); alert(r.mensagem) },
  })
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
      data_limite: form.data_limite || null,
      confidencial: form.confidencial,
      subtasks: form.subtasks.filter((s) => s.trim()).map((texto, ordem) => ({ texto: texto.trim(), ordem })),
    })
  }

  // Agrupa por projeto (mantém "Sem projeto" por último)
  const grupos = useMemo(() => {
    const filtrados = filtroProjeto
      ? cards.filter((c) => c.projeto_id === filtroProjeto)
      : cards
    const map = new Map<string, { nome: string; cor: string; cards: TarefaCard[] }>()
    for (const c of filtrados) {
      const key = c.projeto_id || '__none__'
      if (!map.has(key)) {
        map.set(key, {
          nome: c.projeto_nome || 'Sem projeto',
          cor: c.projeto_cor || '#d1d5db',
          cards: [],
        })
      }
      map.get(key)!.cards.push(c)
    }
    return [...map.entries()].sort((a, b) => {
      if (a[0] === '__none__') return 1
      if (b[0] === '__none__') return -1
      return a[1].nome.localeCompare(b[1].nome)
    })
  }, [cards, filtroProjeto])

  const podeGerenciar = (c: TarefaCard) =>
    isSuperAdmin || (c.criado_por_id && usuario?.id === c.criado_por_id)

  return (
    <div>
      <div className={cs.toolbar}>
        <button className={styles.btnPrimary} onClick={() => { setShowForm((s) => !s); setForm(emptyForm) }}>
          {showForm ? 'Cancelar' : '+ Novo card'}
        </button>
        <div className={cs.filtroProjeto}>
          <select
            className={styles.input}
            value={filtroProjeto}
            onChange={(e) => setFiltroProjeto(e.target.value)}
          >
            <option value="">Todos os projetos</option>
            {projetos.filter((p) => !p.oculto).map((p) => (
              <option key={p.id} value={p.id}>{p.nome}</option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Formulário de criação ─────────────────────────────── */}
      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Título do card *</label>
            <input className={styles.input} value={form.titulo}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição</label>
            <textarea className={styles.input} rows={2} value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Projeto</label>
            <ProjetoCombobox projetos={projetos} value={form.projeto_id}
              onChange={(id) => setForm({ ...form, projeto_id: id })} onCriar={criarProjetoRapido} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Cliente</label>
            <ClienteCombobox value={form.cliente_id} clientes={clientes}
              onChange={(id) => setForm({ ...form, cliente_id: id })} onCreateCliente={criarClienteRapido} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Processo</label>
            <ComboBox options={processoOptions} value={form.processo_id}
              onChange={(v) => setForm({ ...form, processo_id: v })} placeholder="Buscar por CNJ..." />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Responsável</label>
            <ResponsavelComboBox value={form.responsavel} usuarios={usuarios}
              onChange={(v) => setForm({ ...form, responsavel: v })} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Prazo</label>
            <input type="date" className={styles.input} value={form.data_limite}
              onChange={(e) => setForm({ ...form, data_limite: e.target.value })} />
          </div>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Subtarefas</label>
            {form.subtasks.map((st, i) => (
              <div key={i} className={cs.subtaskFormRow}>
                <input className={styles.input} placeholder={`Subtarefa ${i + 1}`} value={st}
                  onChange={(e) => {
                    const arr = [...form.subtasks]; arr[i] = e.target.value
                    setForm({ ...form, subtasks: arr })
                  }} />
                {form.subtasks.length > 1 && (
                  <button type="button" className={cs.subtaskDel}
                    onClick={() => setForm({ ...form, subtasks: form.subtasks.filter((_, j) => j !== i) })}>×</button>
                )}
              </div>
            ))}
            <button type="button" className={cs.linkBtn} style={{ color: '#2563eb' }}
              onClick={() => setForm({ ...form, subtasks: [...form.subtasks, ''] })}>+ Adicionar subtarefa</button>
          </div>

          <label className={cs.confidencialRow}>
            <input type="checkbox" checked={form.confidencial}
              onChange={(e) => setForm({ ...form, confidencial: e.target.checked })} />
            🔒 Card confidencial (privacidade)
          </label>

          <button className={styles.btnPrimary} disabled={!form.titulo.trim() || criar.isPending} onClick={submitCreate}>
            {criar.isPending ? 'Salvando...' : 'Criar card'}
          </button>
        </div>
      )}

      {/* ── Lista agrupada por projeto ────────────────────────── */}
      {isLoading ? <p>Carregando...</p> : cards.length === 0 ? (
        <div className={styles.empty}>Nenhum card cadastrado</div>
      ) : (
        grupos.map(([key, g]) => (
          <section key={key} className={cs.projetoSection}>
            <h3 className={cs.projetoHeader}>
              <span className={cs.projetoDot} style={{ background: g.cor }} />
              {g.nome}
              <span className={cs.projetoCount}>{g.cards.length}</span>
            </h3>
            <div className={cs.cardGrid}>
              {g.cards.map((c) => {
                const done = c.subtasks.filter((s) => s.concluida).length
                return (
                  <div key={c.id} className={`${cs.card} ${cs[`card_${c.status}` as keyof typeof cs]} ${c.confidencial ? cs.card_confidencial : ''}`}>
                    {c.acesso_restrito ? (
                      <div className={cs.restrito}>
                        <div className={cs.restritoIcon}>🔒</div>
                        <div className={cs.restritoTxt}>Card confidencial</div>
                        {!c.ja_solicitou ? (
                          <button className={cs.linkBtn} style={{ color: '#7c3aed', fontWeight: 600 }}
                            onClick={() => solicitar.mutate(c.id)}>
                            Solicitar acesso
                          </button>
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
                          {c.subtasks.length > 0 && (
                            <div className={cs.subtaskProgress}>{done}/{c.subtasks.length} concluídas</div>
                          )}
                          {c.subtasks.map((st) => (
                            <div key={st.id} className={cs.subtaskRow}>
                              <input type="checkbox" checked={st.concluida}
                                onChange={(e) => toggleSubtask.mutate({ id: st.id, concluida: e.target.checked })} />
                              <span className={`${cs.subtaskText} ${st.concluida ? cs.subtaskDone : ''}`}>{st.texto}</span>
                              <button className={cs.subtaskDel} onClick={() => delSubtask.mutate(st.id)}>×</button>
                            </div>
                          ))}
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

                        {/* Pedidos de acesso pendentes (gestor) */}
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
                            c.google_event_id ? (
                              <span className={`${cs.linkBtn} ${cs.linkAgendado}`}>✓ Na agenda</span>
                            ) : (
                              <button className={`${cs.linkBtn} ${cs.linkAgendar}`} disabled={agendar.isPending}
                                onClick={() => agendar.mutate(c.id)}>📅 Agendar</button>
                            )
                          )}
                          <button className={`${cs.linkBtn} ${cs.linkExcluir}`}
                            onClick={() => { if (confirm('Excluir card?')) deletar.mutate(c.id) }}>Excluir</button>
                        </div>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
