import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { prazosApi } from '../api/prazos'
import type { PrazoCreate, TipoPrazo, StatusPrazo } from '../api/prazos'
import { processosApi } from '../api/processos'
import { clientesApi } from '../api/clientes'
import { usuariosApi } from '../api/usuarios'
import styles from './Page.module.css'
import prazosStyles from './PrazosPage.module.css'

const TIPOS: TipoPrazo[] = [
  'contestacao', 'recurso', 'contrarrazoes', 'manifestacao',
  'audiencia', 'pericia', 'outro',
]

const PECAS = [
  'Contestação', 'Recurso de Apelação', 'Recurso Ordinário', 'Agravo Interno',
  'Agravo Regimental', 'Embargos de Declaração', 'Contrarrazões de Apelação',
  'Manifestação', 'Impugnação', 'Réplica', 'Memorial', 'Alegações Finais',
  'Petição Simples', 'Pedido de Prazo', 'Outro',
]

const EMPTY: PrazoCreate = {
  processo_id: '', tipo: 'contestacao', descricao: '',
  peca_necessaria: '', responsavel: '', data_publicacao: '', dias_prazo: 15,
  tipo_contagem: 'uteis', status: 'pendente',
}

function diasRestantes(data?: string): number | null {
  if (!data) return null
  const diff = new Date(data).getTime() - new Date().setHours(0, 0, 0, 0)
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function urgenciaClass(dias: number | null): string {
  if (dias === null) return ''
  if (dias < 0) return prazosStyles.vencido
  if (dias <= 2) return prazosStyles.urgente
  if (dias <= 5) return prazosStyles.atencao
  return prazosStyles.ok
}

function formatDate(d?: string) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

type TabStatus = 'todas' | 'ativo' | 'pendente' | 'cumprido' | 'perdido' | 'ignorado'

export default function PrazosPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<PrazoCreate>(EMPTY)
  const [editando, setEditando] = useState<string | null>(null)
  const [editPeca, setEditPeca] = useState('')
  const [editResponsavel, setEditResponsavel] = useState('')
  const [tabStatus, setTabStatus] = useState<TabStatus>('ativo')

  const { data: prazos = [], isLoading } = useQuery({
    queryKey: ['prazos'],
    queryFn: () => prazosApi.listar(),
  })
  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })
  const { data: usuarios = [] } = useQuery({
    queryKey: ['usuarios'],
    queryFn: usuariosApi.listar,
  })

  const criar = useMutation({
    mutationFn: prazosApi.criar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prazos'] })
      setShowForm(false)
      setForm(EMPTY)
    },
  })

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof prazosApi.atualizar>[1] }) =>
      prazosApi.atualizar(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prazos'] })
      setEditando(null)
    },
  })

  const deletar = useMutation({
    mutationFn: (id: string) => prazosApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['prazos'] }),
    onError: () => alert('Não foi possível remover este prazo.'),
  })

  const getProcesso = (id: string) => processos.find((p) => p.id === id)
  const getCliente = (processoId: string) => {
    const proc = getProcesso(processoId)
    return proc ? clientes.find((c) => c.id === proc.cliente_id) : undefined
  }

  const hoje = new Date(); hoje.setHours(0, 0, 0, 0)

  const tabCounts: Record<TabStatus, number> = {
    todas: prazos.length,
    ativo: prazos.filter(p => p.status === 'pendente' && p.data_limite && new Date(p.data_limite + 'T00:00:00') >= hoje).length,
    pendente: prazos.filter(p => p.status === 'pendente').length,
    cumprido: prazos.filter(p => p.status === 'cumprido').length,
    perdido: prazos.filter(p => p.status === 'perdido').length,
    ignorado: prazos.filter(p => p.status === 'ignorado').length,
  }

  const prazosVisiveis = prazos.filter(p => {
    if (tabStatus === 'todas') return true
    if (tabStatus === 'ativo') return p.status === 'pendente' && p.data_limite && new Date(p.data_limite + 'T00:00:00') >= hoje
    if (tabStatus === 'pendente') return p.status === 'pendente'
    return p.status === tabStatus
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Prazos</h1>
        <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Novo Prazo'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); criar.mutate(form) }}
          className={styles.form}
        >
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Processo *</label>
            <select className={styles.input} value={form.processo_id}
              onChange={(e) => setForm({ ...form, processo_id: e.target.value })} required>
              <option value="">Selecione...</option>
              {processos.map((p) => {
                const cliente = clientes.find((c) => c.id === p.cliente_id)
                return (
                  <option key={p.id} value={p.id}>
                    {p.numero_cnj}{cliente ? ` — ${cliente.nome}` : ''}
                  </option>
                )
              })}
            </select>
          </div>
          <div className={prazosStyles.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Tipo *</label>
              <select className={styles.input} value={form.tipo}
                onChange={(e) => setForm({ ...form, tipo: e.target.value as TipoPrazo })}>
                {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Peça necessária</label>
              <select className={styles.input} value={form.peca_necessaria ?? ''}
                onChange={(e) => setForm({ ...form, peca_necessaria: e.target.value })}>
                <option value="">— Selecione —</option>
                {PECAS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data da Publicação *</label>
            <input type="date" className={styles.input} value={form.data_publicacao}
              onChange={(e) => setForm({ ...form, data_publicacao: e.target.value })} required />
          </div>
          <div className={prazosStyles.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Dias do prazo *</label>
              <input type="number" className={styles.input} value={form.dias_prazo} min={1}
                onChange={(e) => setForm({ ...form, dias_prazo: Number(e.target.value) })} required />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Contagem</label>
              <select className={styles.input} value={form.tipo_contagem}
                onChange={(e) => setForm({ ...form, tipo_contagem: e.target.value as 'uteis' | 'corridos' })}>
                <option value="uteis">Dias úteis</option>
                <option value="corridos">Dias corridos</option>
              </select>
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Responsável</label>
            <select className={styles.input} value={form.responsavel ?? ''} onChange={(e) => setForm({ ...form, responsavel: e.target.value || undefined })}>
              <option value="">— Nenhum —</option>
              {usuarios.filter(u => u.ativo).map(u => (
                <option key={u.id} value={u.nome}>{u.nome}</option>
              ))}
              <option value="Terceiros">Terceiros</option>
            </select>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição</label>
            <textarea className={styles.input} rows={2} value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
          </div>
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Calculando e salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {/* Status tabs */}
      {!isLoading && prazos.length > 0 && (
        <div className={prazosStyles.tabs}>
          {(['todas', 'ativo', 'pendente', 'cumprido', 'perdido', 'ignorado'] as TabStatus[]).map((tab) => (
            <button
              key={tab}
              className={`${prazosStyles.tab} ${tabStatus === tab ? prazosStyles.tabActive : ''}`}
              onClick={() => setTabStatus(tab)}
            >
              {tab === 'todas' ? 'Todas' : tab === 'ativo' ? 'Ativo' : tab === 'pendente' ? 'Pendente' : tab === 'cumprido' ? 'Cumprido' : tab === 'perdido' ? 'Perdido' : 'Ignorado'}
              <span className={prazosStyles.tabCount}>{tabCounts[tab]}</span>
            </button>
          ))}
        </div>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : prazos.length === 0 ? (
        <p className={styles.empty}>Nenhum prazo cadastrado.</p>
      ) : prazosVisiveis.length === 0 ? (
        <p className={styles.empty}>Nenhum prazo nesta categoria.</p>
      ) : (
        <div className={prazosStyles.lista}>
          {prazosVisiveis.map((p) => {
            const dias = diasRestantes(p.data_limite)
            const proc = getProcesso(p.processo_id)
            const cliente = getCliente(p.processo_id)
            return (
              <div key={p.id} className={`${prazosStyles.card} ${urgenciaClass(dias)}`}>
                <div className={prazosStyles.cardHeader}>
                  <div className={prazosStyles.cardInfo}>
                    <div className={prazosStyles.cardTop}>
                      {cliente && <span className={prazosStyles.clienteNome}>{cliente.nome}</span>}
                      <code className={prazosStyles.cnj}>{proc?.numero_cnj ?? p.processo_id.slice(0,8)}</code>
                      {proc?.materia && <span className={prazosStyles.materia}>{proc.materia}</span>}
                    </div>
                    <div className={prazosStyles.cardBottom}>
                      <span className={`${styles.badge} ${prazosStyles[`tipo_${p.tipo}`]}`}>{p.tipo}</span>
                      {p.criado_automaticamente && (
                        <span title="Criado automaticamente pelo gestor jurídico (Despacho)"
                          style={{ fontSize: 11, fontWeight: 700, color: '#7c3aed', background: '#f3e8ff', padding: '2px 8px', borderRadius: 999 }}>
                          🤖 Automático
                        </span>
                      )}
                      {(p.tarefas_vinculadas?.length ?? 0) > 0 && (
                        <a href="/tarefas" title={p.tarefas_vinculadas!.map(t => t.titulo).join('; ')}
                          style={{ fontSize: 11, fontWeight: 700, color: '#1d4ed8', background: '#dbeafe', padding: '2px 8px', borderRadius: 999, textDecoration: 'none' }}>
                          🔗 {p.tarefas_vinculadas!.length} tarefa(s)
                        </a>
                      )}
                      {p.peca_necessaria && editando !== p.id && (
                        <span className={prazosStyles.pecaChip}>
                          {p.peca_necessaria}
                          <button
                            className={prazosStyles.pecaChipEdit}
                            title="Alterar peça"
                            onClick={() => { setEditando(p.id); setEditPeca(p.peca_necessaria ?? ''); setEditResponsavel(p.responsavel ?? '') }}
                          >✎</button>
                        </span>
                      )}
                      {!p.peca_necessaria && editando !== p.id && (
                        <button className={prazosStyles.btnAddPeca}
                          onClick={() => { setEditando(p.id); setEditPeca(''); setEditResponsavel(p.responsavel ?? '') }}>
                          + Peça
                        </button>
                      )}
                      <span className={prazosStyles.datas}>
                        Publicado: {formatDate(p.data_publicacao)}
                        {' · '}
                        <strong className={urgenciaClass(dias)}>Limite: {formatDate(p.data_limite)}</strong>
                        {' · '}
                        <span className={`${prazosStyles.restam} ${urgenciaClass(dias)}`}>
                          {dias === null ? '—' : dias < 0 ? `${Math.abs(dias)}d atrás` : `${dias}d restantes`}
                        </span>
                        {p.responsavel && (
                          <span style={{ color: '#6b7280' }}>{' · '}Resp: {p.responsavel}</span>
                        )}
                      </span>
                    </div>

                    {editando === p.id && (
                      <div className={prazosStyles.pecaEditor}>
                        <select className={styles.input}
                          value={editPeca}
                          onChange={(e) => setEditPeca(e.target.value)}>
                          <option value="">— Selecione —</option>
                          {PECAS.map((pc) => <option key={pc} value={pc}>{pc}</option>)}
                        </select>
                        <select className={styles.input} value={editResponsavel} onChange={(e) => setEditResponsavel(e.target.value)}>
                          <option value="">— Nenhum —</option>
                          {usuarios.filter(u => u.ativo).map(u => (
                            <option key={u.id} value={u.nome}>{u.nome}</option>
                          ))}
                          <option value="Terceiros">Terceiros</option>
                        </select>
                        <button className={styles.btnPrimary} style={{ fontSize: '12px', padding: '6px 12px' }}
                          disabled={atualizar.isPending}
                          onClick={() => atualizar.mutate({ id: p.id, data: { peca_necessaria: editPeca || undefined, responsavel: editResponsavel || undefined } })}>
                          Salvar
                        </button>
                        <button className={styles.btnDanger} onClick={() => setEditando(null)}>Cancelar</button>
                      </div>
                    )}
                  </div>

                  <div className={prazosStyles.cardActions}>
                    <select className={prazosStyles.statusSelect} value={p.status}
                      onChange={(e) => atualizar.mutate({ id: p.id, data: { status: e.target.value as StatusPrazo } })}>
                      <option value="pendente">pendente</option>
                      <option value="cumprido">cumprido</option>
                      <option value="perdido">perdido</option>
                      <option value="ignorado">ignorado</option>
                    </select>
                    <button className={styles.btnDanger}
                      onClick={() => { if (confirm('Remover prazo?')) deletar.mutate(p.id) }}>
                      ×
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
