import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conselhoApi } from '../api/conselho'
import type {
  CategoriaDiretriz, Contato, Diretriz, Evento, LogDiario, Parceiro, PipelineItem,
  StatusDiretriz, StatusParceiro, TipoParceiro,
} from '../api/conselho'
import ComboBox from '../components/ComboBox'
import type { ComboOption } from '../components/ComboBox'
import styles from './Page.module.css'
import cs from './ConselhoPage.module.css'

const CATEGORIAS: { value: CategoriaDiretriz; label: string }[] = [
  { value: 'operacional', label: 'Operacional' },
  { value: 'juridico', label: 'Jurídico' },
  { value: 'comercial', label: 'Comercial' },
  { value: 'parcerias', label: 'Parcerias' },
]
const STATUS_DIRETRIZ: StatusDiretriz[] = ['Não iniciado', 'Em andamento', 'Bloqueado', 'Concluído', 'Atrasado']
const TIPOS_PARCEIRO: TipoParceiro[] = ['Advogado', 'Contador', 'Assessor de investimentos', 'Outro']
const STATUS_PARCEIRO: StatusParceiro[] = ['Quente', 'Frio', 'Reativado']
const ESTAGIOS_PIPELINE = ['Prospecção', 'Contato inicial', 'Reunião agendada', 'Proposta enviada', 'Negociação', 'Fechado', 'Perdido']

function fmtData(d?: string | null) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

function diasDesde(d?: string | null) {
  if (!d) return Infinity
  return Math.floor((Date.now() - new Date(d + 'T12:00:00').getTime()) / 86400000)
}

function aplicarPlaceholders(template: string, primeiro: string, ultimo: string, evento: string) {
  return template
    .replaceAll('{primeiro}', primeiro)
    .replaceAll('{ultimo}', ultimo || '')
    .replaceAll('{evento}', evento)
}

export default function ConselhoPage() {
  const [aba, setAba] = useState<'diretrizes' | 'pipeline' | 'eventos' | 'parcerias' | 'metricas'>('diretrizes')

  return (
    <div>
      <div className={styles.pageHeader}>
        <div className={styles.pageTitle}>Painel do <strong>Conselho</strong></div>
      </div>
      <div className={cs.tabs}>
        {([
          ['diretrizes', 'Diretrizes'],
          ['pipeline', 'Pipeline'],
          ['eventos', 'Eventos & Contatos'],
          ['parcerias', 'Parcerias'],
          ['metricas', 'Métricas'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            className={`${cs.tabBtn} ${aba === key ? cs.tabBtnActive : ''}`}
            onClick={() => setAba(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {aba === 'diretrizes' && <DiretrizesTab />}
      {aba === 'pipeline' && <PipelineTab />}
      {aba === 'eventos' && <EventosContatosTab />}
      {aba === 'parcerias' && <ParceriasTab />}
      {aba === 'metricas' && <MetricasTab />}
    </div>
  )
}

// ───────────────────────────── Diretrizes ─────────────────────────────

function DiretrizesTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [categoria, setCategoria] = useState<CategoriaDiretriz>('operacional')
  const [titulo, setTitulo] = useState('')
  const [descricao, setDescricao] = useState('')
  const [prazo, setPrazo] = useState('')
  const [novaSubtask, setNovaSubtask] = useState<Record<string, string>>({})

  const { data: diretrizes = [], isLoading } = useQuery({
    queryKey: ['conselho-diretrizes'],
    queryFn: () => conselhoApi.listarDiretrizes(),
  })

  const criar = useMutation({
    mutationFn: conselhoApi.criarDiretriz,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] })
      setShowForm(false)
      setTitulo(''); setDescricao(''); setPrazo('')
    },
  })

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Diretriz> }) => conselhoApi.atualizarDiretriz(id, data as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] }),
  })

  const deletar = useMutation({
    mutationFn: conselhoApi.deletarDiretriz,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] }),
  })

  const addSubtask = useMutation({
    mutationFn: ({ id, texto }: { id: string; texto: string }) => conselhoApi.addSubtask(id, texto),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] }),
  })

  const toggleSubtask = useMutation({
    mutationFn: ({ id, concluida }: { id: string; concluida: boolean }) => conselhoApi.toggleSubtask(id, concluida),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] }),
  })

  return (
    <div>
      <button className={styles.btnPrimary} onClick={() => setShowForm((s) => !s)} style={{ marginBottom: 16 }}>
        {showForm ? 'Cancelar' : '+ Nova diretriz'}
      </button>

      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Categoria</label>
            <select className={styles.input} value={categoria} onChange={(e) => setCategoria(e.target.value as CategoriaDiretriz)}>
              {CATEGORIAS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Título</label>
            <input className={styles.input} value={titulo} onChange={(e) => setTitulo(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição</label>
            <textarea className={cs.textarea} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Prazo</label>
            <input type="date" className={styles.input} value={prazo} onChange={(e) => setPrazo(e.target.value)} />
          </div>
          <button
            className={styles.btnPrimary}
            disabled={!titulo || criar.isPending}
            onClick={() => criar.mutate({ categoria, titulo, descricao: descricao || undefined, prazo: prazo || undefined })}
          >
            Criar diretriz
          </button>
        </div>
      )}

      {isLoading ? <p>Carregando...</p> : diretrizes.length === 0 ? (
        <div className={styles.empty}>Nenhuma diretriz cadastrada</div>
      ) : (
        <div className={cs.cardGrid}>
          {diretrizes.map((d) => (
            <div key={d.id} className={`${cs.card} ${cs[`card_${d.categoria}` as keyof typeof cs]}`}>
              <div className={cs.cardTitle}>{d.titulo}</div>
              {d.descricao && <div className={cs.cardDesc}>{d.descricao}</div>}
              <div className={cs.cardMeta}>
                <select
                  className={styles.input}
                  style={{ padding: '4px 8px', fontSize: 12 }}
                  value={d.status}
                  onChange={(e) => atualizar.mutate({ id: d.id, data: { status: e.target.value as StatusDiretriz } })}
                >
                  {STATUS_DIRETRIZ.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <span style={{ fontSize: 11, color: '#9ca3af' }}>{fmtData(d.prazo)}</span>
              </div>
              {d.subtasks.map((st) => (
                <div key={st.id} className={cs.subtaskRow}>
                  <input
                    type="checkbox"
                    checked={st.concluida}
                    onChange={(e) => toggleSubtask.mutate({ id: st.id, concluida: e.target.checked })}
                  />
                  <span className={st.concluida ? cs.subtaskDone : ''}>{st.texto}</span>
                </div>
              ))}
              <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                <input
                  className={styles.input}
                  style={{ padding: '5px 8px', fontSize: 12 }}
                  placeholder="+ subtarefa"
                  value={novaSubtask[d.id] || ''}
                  onChange={(e) => setNovaSubtask((s) => ({ ...s, [d.id]: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && novaSubtask[d.id]) {
                      addSubtask.mutate({ id: d.id, texto: novaSubtask[d.id] })
                      setNovaSubtask((s) => ({ ...s, [d.id]: '' }))
                    }
                  }}
                />
              </div>
              <button className={styles.btnDanger} style={{ marginTop: 10 }} onClick={() => { if (confirm('Excluir diretriz?')) deletar.mutate(d.id) }}>
                Excluir
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ───────────────────────────── Pipeline ─────────────────────────────

function PipelineTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [nome, setNome] = useState('')
  const [origem, setOrigem] = useState('')
  const [tema, setTema] = useState('')

  const { data: pipeline = [], isLoading } = useQuery({
    queryKey: ['conselho-pipeline'],
    queryFn: () => conselhoApi.listarPipeline(),
  })

  const criar = useMutation({
    mutationFn: conselhoApi.criarPipeline,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conselho-pipeline'] })
      setShowForm(false); setNome(''); setOrigem(''); setTema('')
    },
  })
  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PipelineItem> }) => conselhoApi.atualizarPipeline(id, data as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-pipeline'] }),
  })
  const deletar = useMutation({
    mutationFn: conselhoApi.deletarPipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-pipeline'] }),
  })

  return (
    <div>
      <button className={styles.btnPrimary} onClick={() => setShowForm((s) => !s)} style={{ marginBottom: 16 }}>
        {showForm ? 'Cancelar' : '+ Nova oportunidade'}
      </button>
      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Nome</label>
            <input className={styles.input} value={nome} onChange={(e) => setNome(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Origem</label>
            <input className={styles.input} value={origem} onChange={(e) => setOrigem(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Tema</label>
            <input className={styles.input} value={tema} onChange={(e) => setTema(e.target.value)} />
          </div>
          <button className={styles.btnPrimary} disabled={!nome} onClick={() => criar.mutate({ nome, origem: origem || undefined, tema: tema || undefined })}>
            Criar
          </button>
        </div>
      )}
      {isLoading ? <p>Carregando...</p> : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Nome</th><th>Origem</th><th>Estágio</th><th>Último contato</th><th>Próxima ação</th><th>Ticket</th><th>Prob.</th><th></th>
              </tr>
            </thead>
            <tbody>
              {pipeline.map((p) => {
                const alerta = diasDesde(p.ultimo_contato) >= 10
                return (
                  <tr key={p.id} className={alerta ? cs.alertRow : ''}>
                    <td>{p.nome}</td>
                    <td>{p.origem || '—'}</td>
                    <td>
                      <select
                        className={styles.input}
                        style={{ padding: '4px 6px', fontSize: 12 }}
                        value={p.estagio}
                        onChange={(e) => atualizar.mutate({ id: p.id, data: { estagio: e.target.value } })}
                      >
                        {ESTAGIOS_PIPELINE.map((e) => <option key={e} value={e}>{e}</option>)}
                      </select>
                    </td>
                    <td>
                      <input
                        type="date"
                        className={styles.input}
                        style={{ padding: '4px 6px', fontSize: 12 }}
                        value={p.ultimo_contato || ''}
                        onChange={(e) => atualizar.mutate({ id: p.id, data: { ultimo_contato: e.target.value } })}
                      />
                    </td>
                    <td>{p.proxima_acao || '—'}</td>
                    <td>{p.ticket ? p.ticket.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '—'}</td>
                    <td>{p.probabilidade != null ? `${p.probabilidade}%` : '—'}</td>
                    <td><button className={styles.btnDanger} onClick={() => deletar.mutate(p.id)}>Excluir</button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {pipeline.length === 0 && <div className={styles.empty}>Nenhuma oportunidade no pipeline</div>}
        </div>
      )}
    </div>
  )
}

// ───────────────────────────── Eventos & Contatos ─────────────────────────────

function EventosContatosTab() {
  const [sub, setSub] = useState<'eventos' | 'contatos' | 'disparador'>('eventos')
  return (
    <div>
      <div className={cs.subTabs}>
        {([['eventos', 'Eventos'], ['contatos', 'Base de Contatos'], ['disparador', 'Disparador']] as const).map(([key, label]) => (
          <button key={key} className={`${cs.subTabBtn} ${sub === key ? cs.subTabBtnActive : ''}`} onClick={() => setSub(key)}>
            {label}
          </button>
        ))}
      </div>
      {sub === 'eventos' && <EventosSubTab />}
      {sub === 'contatos' && <ContatosSubTab />}
      {sub === 'disparador' && <DisparadorSubTab />}
    </div>
  )
}

function ContatoAutocomplete({ onSelect }: { onSelect: (c: Contato) => void }) {
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const { data: resultados = [] } = useQuery({
    queryKey: ['conselho-contatos-busca', query],
    queryFn: () => conselhoApi.buscarContatos(query),
    enabled: query.length > 1,
  })
  const criar = useMutation({
    mutationFn: (nome: string) => {
      const [primeiro, ...resto] = nome.trim().split(' ')
      return conselhoApi.criarContato({ primeiro_nome: primeiro, sobrenome: resto.join(' ') || undefined })
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['conselho-contatos'] })
      onSelect(c)
    },
  })
  const options: ComboOption[] = resultados.map((c) => ({
    value: c.id,
    label: `${c.primeiro_nome} ${c.sobrenome || ''}`.trim(),
    sublabel: c.email || c.whatsapp || undefined,
  }))
  return (
    <ComboBox
      options={options}
      value=""
      onChange={(v) => {
        setQuery('')
        const c = resultados.find((r) => r.id === v)
        if (c) onSelect(c)
      }}
      placeholder="Buscar contato por nome, e-mail ou WhatsApp..."
      onCreate={(q) => criar.mutate(q)}
      createLabel="Criar contato"
    />
  )
}

function EventosSubTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [nome, setNome] = useState('')
  const [data, setData] = useState('')
  const [expandido, setExpandido] = useState<string | null>(null)
  const [masterMsg, setMasterMsg] = useState('')

  const { data: eventos = [], isLoading } = useQuery({
    queryKey: ['conselho-eventos'],
    queryFn: () => conselhoApi.listarEventos(),
  })

  const criar = useMutation({
    mutationFn: conselhoApi.criarEvento,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['conselho-eventos'] }); setShowForm(false); setNome(''); setData('') },
  })
  const atualizar = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<Evento> }) => conselhoApi.atualizarEvento(id, payload as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })
  const deletar = useMutation({
    mutationFn: conselhoApi.deletarEvento,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })
  const addConvidado = useMutation({
    mutationFn: ({ eventoId, contatoId }: { eventoId: string; contatoId: string }) => conselhoApi.addConvidado(eventoId, contatoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })
  const atualizarConvidado = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { presenca_confirmada?: boolean; participacao_confirmada?: boolean } }) =>
      conselhoApi.atualizarConvidado(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })
  const removerConvidado = useMutation({
    mutationFn: conselhoApi.removerConvidado,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })

  const eventoExpandido = eventos.find((e) => e.id === expandido)

  return (
    <div>
      <button className={styles.btnPrimary} onClick={() => setShowForm((s) => !s)} style={{ marginBottom: 16 }}>
        {showForm ? 'Cancelar' : '+ Novo evento'}
      </button>
      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Nome do evento</label>
            <input className={styles.input} value={nome} onChange={(e) => setNome(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data</label>
            <input type="date" className={styles.input} value={data} onChange={(e) => setData(e.target.value)} />
          </div>
          <button className={styles.btnPrimary} disabled={!nome} onClick={() => criar.mutate({ nome, data: data || undefined })}>
            Criar evento
          </button>
        </div>
      )}

      {eventoExpandido ? (
        <div>
          <button className={styles.btnSmall} onClick={() => setExpandido(null)} style={{ marginBottom: 14 }}>← Voltar</button>
          <h3 style={{ marginBottom: 4 }}>{eventoExpandido.nome}</h3>
          <p style={{ fontSize: 12, color: '#9ca3af', marginBottom: 14 }}>{fmtData(eventoExpandido.data)}</p>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Mensagem master (placeholders: {'{primeiro}'}, {'{ultimo}'}, {'{evento}'})</label>
            <textarea
              className={cs.textarea}
              value={masterMsg || eventoExpandido.mensagem_master || ''}
              onChange={(e) => setMasterMsg(e.target.value)}
              onBlur={() => atualizar.mutate({ id: eventoExpandido.id, payload: { mensagem_master: masterMsg || eventoExpandido.mensagem_master || '' } })}
            />
          </div>

          <div className={styles.formRow} style={{ maxWidth: 420 }}>
            <label className={styles.formLabel}>Adicionar convidado</label>
            <ContatoAutocomplete onSelect={(c) => addConvidado.mutate({ eventoId: eventoExpandido.id, contatoId: c.id })} />
          </div>

          <div className={styles.tableCard} style={{ marginTop: 14 }}>
            {eventoExpandido.convidados.length === 0 && <div className={styles.empty}>Nenhum convidado ainda</div>}
            {eventoExpandido.convidados.map((cv) => (
              <div key={cv.id} className={cs.guestRow}>
                <span className={cs.guestName}>{cv.contato.primeiro_nome} {cv.contato.sobrenome || ''}</span>
                <label className={cs.checkboxLabel}>
                  <input type="checkbox" checked={cv.presenca_confirmada} onChange={(e) => atualizarConvidado.mutate({ id: cv.id, payload: { presenca_confirmada: e.target.checked } })} />
                  Presença
                </label>
                <label className={cs.checkboxLabel}>
                  <input type="checkbox" checked={cv.participacao_confirmada} onChange={(e) => atualizarConvidado.mutate({ id: cv.id, payload: { participacao_confirmada: e.target.checked } })} />
                  Participação
                </label>
                {cv.contato.whatsapp && (
                  <a className={`${cs.linkBtn} ${cs.linkWhatsapp}`} target="_blank" rel="noreferrer"
                     href={`https://wa.me/${cv.contato.whatsapp.replace(/\D/g, '')}?text=${encodeURIComponent(aplicarPlaceholders(eventoExpandido.mensagem_master || '', cv.contato.primeiro_nome, cv.contato.sobrenome || '', eventoExpandido.nome))}`}>
                    WhatsApp
                  </a>
                )}
                {cv.contato.email && (
                  <a className={`${cs.linkBtn} ${cs.linkEmail}`}
                     href={`mailto:${cv.contato.email}?subject=${encodeURIComponent(eventoExpandido.nome)}&body=${encodeURIComponent(aplicarPlaceholders(eventoExpandido.mensagem_master || '', cv.contato.primeiro_nome, cv.contato.sobrenome || '', eventoExpandido.nome))}`}>
                    E-mail
                  </a>
                )}
                <button className={styles.btnDanger} onClick={() => removerConvidado.mutate(cv.id)}>Remover</button>
              </div>
            ))}
          </div>
          <button className={styles.btnDanger} style={{ marginTop: 14 }} onClick={() => { if (confirm('Excluir evento?')) { deletar.mutate(eventoExpandido.id); setExpandido(null) } }}>
            Excluir evento
          </button>
        </div>
      ) : isLoading ? <p>Carregando...</p> : (
        <div className={cs.cardGrid}>
          {eventos.map((e) => {
            const presentes = e.convidados.filter((c) => c.presenca_confirmada).length
            const participantes = e.convidados.filter((c) => c.participacao_confirmada).length
            return (
              <div key={e.id} className={cs.eventCard} onClick={() => setExpandido(e.id)}>
                <div className={cs.cardTitle}>{e.nome}</div>
                <div style={{ fontSize: 12, color: '#9ca3af' }}>{fmtData(e.data)}</div>
                <div className={cs.eventStats}>
                  <span>{e.convidados.length} convidados</span>
                  <span>{presentes} presentes</span>
                  <span>{participantes} participaram</span>
                </div>
              </div>
            )
          })}
          {eventos.length === 0 && <div className={styles.empty}>Nenhum evento cadastrado</div>}
        </div>
      )}
    </div>
  )
}

function ContatosSubTab() {
  const qc = useQueryClient()
  const [filtroEvento, setFiltroEvento] = useState('')
  const [filtroPresenca, setFiltroPresenca] = useState('')
  const [filtroParticipacao, setFiltroParticipacao] = useState('')
  const [expandido, setExpandido] = useState<string | null>(null)
  const [showNovo, setShowNovo] = useState(false)
  const [primeiroNome, setPrimeiroNome] = useState('')
  const [sobrenome, setSobrenome] = useState('')
  const [email, setEmail] = useState('')
  const [whatsapp, setWhatsapp] = useState('')

  const { data: eventos = [] } = useQuery({ queryKey: ['conselho-eventos'], queryFn: () => conselhoApi.listarEventos() })
  const { data: contatos = [], isLoading } = useQuery({
    queryKey: ['conselho-contatos', filtroEvento, filtroPresenca, filtroParticipacao],
    queryFn: () => conselhoApi.listarContatos({
      evento_id: filtroEvento || undefined,
      presenca_confirmada: filtroPresenca ? filtroPresenca === 'sim' : undefined,
      participacao_confirmada: filtroParticipacao ? filtroParticipacao === 'sim' : undefined,
    }),
  })

  const criar = useMutation({
    mutationFn: conselhoApi.criarContato,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conselho-contatos'] })
      setShowNovo(false); setPrimeiroNome(''); setSobrenome(''); setEmail(''); setWhatsapp('')
    },
  })
  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Contato> }) => conselhoApi.atualizarContato(id, data as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-contatos'] }),
  })
  const deletar = useMutation({
    mutationFn: conselhoApi.deletarContato,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-contatos'] }),
  })

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <button className={styles.btnPrimary} onClick={() => setShowNovo((s) => !s)}>
          {showNovo ? 'Cancelar' : '+ Novo contato'}
        </button>
        <div className={styles.fieldGroup}>
          <span>Evento</span>
          <select value={filtroEvento} onChange={(e) => setFiltroEvento(e.target.value)}>
            <option value="">Todos</option>
            {eventos.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
          </select>
        </div>
        <div className={styles.fieldGroup}>
          <span>Presença</span>
          <select value={filtroPresenca} onChange={(e) => setFiltroPresenca(e.target.value)}>
            <option value="">Todos</option><option value="sim">Confirmada</option><option value="nao">Não confirmada</option>
          </select>
        </div>
        <div className={styles.fieldGroup}>
          <span>Participação</span>
          <select value={filtroParticipacao} onChange={(e) => setFiltroParticipacao(e.target.value)}>
            <option value="">Todos</option><option value="sim">Confirmada</option><option value="nao">Não confirmada</option>
          </select>
        </div>
      </div>

      {showNovo && (
        <div className={styles.form}>
          <div className={styles.formRow}><label className={styles.formLabel}>Primeiro nome</label><input className={styles.input} value={primeiroNome} onChange={(e) => setPrimeiroNome(e.target.value)} /></div>
          <div className={styles.formRow}><label className={styles.formLabel}>Sobrenome</label><input className={styles.input} value={sobrenome} onChange={(e) => setSobrenome(e.target.value)} /></div>
          <div className={styles.formRow}><label className={styles.formLabel}>E-mail</label><input className={styles.input} value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div className={styles.formRow}><label className={styles.formLabel}>WhatsApp</label><input className={styles.input} value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} /></div>
          <button className={styles.btnPrimary} disabled={!primeiroNome} onClick={() => criar.mutate({ primeiro_nome: primeiroNome, sobrenome: sobrenome || undefined, email: email || undefined, whatsapp: whatsapp || undefined })}>
            Criar contato
          </button>
        </div>
      )}

      {isLoading ? <p>Carregando...</p> : (
        <div className={styles.tableCard}>
          {contatos.map((c) => (
            <div key={c.id}>
              <div className={cs.guestRow} style={{ cursor: 'pointer' }} onClick={() => setExpandido(expandido === c.id ? null : c.id)}>
                <span className={cs.guestName}>{c.primeiro_nome} {c.sobrenome || ''}</span>
                <span style={{ fontSize: 12, color: '#9ca3af' }}>{c.eventos.join(', ') || 'Sem evento'}</span>
                {c.whatsapp && <a className={`${cs.linkBtn} ${cs.linkWhatsapp}`} onClick={(e) => e.stopPropagation()} target="_blank" rel="noreferrer" href={`https://wa.me/${c.whatsapp.replace(/\D/g, '')}`}>WhatsApp</a>}
                {c.email && <a className={`${cs.linkBtn} ${cs.linkEmail}`} onClick={(e) => e.stopPropagation()} href={`mailto:${c.email}`}>E-mail</a>}
                <button className={styles.btnDanger} onClick={(e) => { e.stopPropagation(); if (confirm('Excluir contato?')) deletar.mutate(c.id) }}>Excluir</button>
              </div>
              {expandido === c.id && (
                <div style={{ padding: '10px 18px 16px', background: '#fafafa' }}>
                  <div style={{ display: 'flex', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
                    <input className={styles.input} style={{ maxWidth: 200 }} defaultValue={c.email || ''} placeholder="E-mail"
                      onBlur={(e) => atualizar.mutate({ id: c.id, data: { email: e.target.value } })} />
                    <input className={styles.input} style={{ maxWidth: 200 }} defaultValue={c.whatsapp || ''} placeholder="WhatsApp"
                      onBlur={(e) => atualizar.mutate({ id: c.id, data: { whatsapp: e.target.value } })} />
                  </div>
                  <textarea className={cs.textarea} defaultValue={c.mensagem_global || ''} placeholder="Mensagem individual padrão"
                    onBlur={(e) => atualizar.mutate({ id: c.id, data: { mensagem_global: e.target.value } })} />
                  {c.notas.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      {c.notas.map((n) => (
                        <div key={n.id} style={{ fontSize: 12.5, padding: '4px 0', borderBottom: '1px solid #eee' }}>
                          <strong>{n.evento_nome || 'Geral'}</strong> ({fmtData(n.data)}): {n.texto}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          {contatos.length === 0 && <div className={styles.empty}>Nenhum contato encontrado</div>}
        </div>
      )}
    </div>
  )
}

function DisparadorSubTab() {
  const { data: eventos = [] } = useQuery({ queryKey: ['conselho-eventos'], queryFn: () => conselhoApi.listarEventos() })
  const [eventosSelecionados, setEventosSelecionados] = useState<Set<string>>(new Set())
  const [contatosSelecionados, setContatosSelecionados] = useState<Set<string>>(new Set())
  const [busca, setBusca] = useState('')
  const [msgWhatsapp, setMsgWhatsapp] = useState('Olá {primeiro}, tudo bem? Te convido para o {evento}!')
  const [msgEmail, setMsgEmail] = useState('Olá {primeiro},\n\nTe convido para o {evento}.\n\nAbraço.')

  const contatosPorEvento = useMemo(() => {
    const map = new Map<string, Contato[]>()
    for (const e of eventos) map.set(e.id, e.convidados.map((cv) => cv.contato))
    return map
  }, [eventos])

  const todosContatos = useMemo(() => {
    const seen = new Map<string, Contato & { eventoNome: string }>()
    for (const e of eventos) {
      for (const cv of e.convidados) {
        if (!seen.has(cv.contato.id)) seen.set(cv.contato.id, { ...cv.contato, eventoNome: e.nome })
      }
    }
    return Array.from(seen.values())
  }, [eventos])

  const contatosFiltrados = todosContatos
    .filter((c) => `${c.primeiro_nome} ${c.sobrenome || ''}`.toLowerCase().includes(busca.toLowerCase()))
    .sort((a, b) => a.primeiro_nome.localeCompare(b.primeiro_nome))

  function toggleEvento(eventoId: string) {
    const next = new Set(eventosSelecionados)
    const contatosEvento = contatosPorEvento.get(eventoId) || []
    if (next.has(eventoId)) {
      next.delete(eventoId)
      const nextC = new Set(contatosSelecionados)
      contatosEvento.forEach((c) => nextC.delete(c.id))
      setContatosSelecionados(nextC)
    } else {
      next.add(eventoId)
      const nextC = new Set(contatosSelecionados)
      contatosEvento.forEach((c) => nextC.add(c.id))
      setContatosSelecionados(nextC)
    }
    setEventosSelecionados(next)
  }

  function toggleContato(id: string) {
    const next = new Set(contatosSelecionados)
    if (next.has(id)) next.delete(id); else next.add(id)
    setContatosSelecionados(next)
  }

  const selecionados = todosContatos.filter((c) => contatosSelecionados.has(c.id))

  return (
    <div>
      <h4 style={{ marginBottom: 8 }}>1. Selecione eventos</h4>
      <div className={cs.dispatchList}>
        {eventos.map((e) => (
          <label key={e.id} className={cs.checkboxLabel} style={{ fontSize: 13 }}>
            <input type="checkbox" checked={eventosSelecionados.has(e.id)} onChange={() => toggleEvento(e.id)} />
            {e.nome} ({e.convidados.length} convidados)
          </label>
        ))}
      </div>

      <h4 style={{ marginBottom: 8 }}>2. Mensagens (placeholders: {'{primeiro}'}, {'{ultimo}'}, {'{evento}'})</h4>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>WhatsApp</label>
        <textarea className={cs.textarea} value={msgWhatsapp} onChange={(e) => setMsgWhatsapp(e.target.value)} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>E-mail</label>
        <textarea className={cs.textarea} value={msgEmail} onChange={(e) => setMsgEmail(e.target.value)} />
      </div>

      <h4 style={{ marginBottom: 8 }}>3. Contatos ({selecionados.length} selecionados)</h4>
      <input className={styles.input} style={{ maxWidth: 320, marginBottom: 10 }} placeholder="Buscar..." value={busca} onChange={(e) => setBusca(e.target.value)} />
      <div className={cs.dispatchList}>
        {contatosFiltrados.map((c) => (
          <label key={c.id} className={cs.checkboxLabel} style={{ fontSize: 13 }}>
            <input type="checkbox" checked={contatosSelecionados.has(c.id)} onChange={() => toggleContato(c.id)} />
            {c.primeiro_nome} {c.sobrenome || ''} <span style={{ color: '#9ca3af' }}>({c.eventoNome})</span>
          </label>
        ))}
      </div>

      <h4 style={{ marginBottom: 8 }}>4. Disparar</h4>
      {selecionados.length === 0 ? (
        <div className={styles.empty}>Selecione ao menos um contato</div>
      ) : (
        <div>
          <div style={{ marginBottom: 10 }}>
            <a
              className={`${cs.linkBtn} ${cs.linkEmail}`}
              href={`mailto:?bcc=${selecionados.filter((c) => c.email).map((c) => c.email).join(',')}&subject=Convite&body=${encodeURIComponent(msgEmail)}`}
            >
              E-mail único (todos em BCC)
            </a>
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 6 }}>E-mail individual:</div>
          <div style={{ marginBottom: 14 }}>
            {selecionados.filter((c) => c.email).map((c) => (
              <a key={c.id} className={`${cs.linkBtn} ${cs.linkEmail}`}
                 href={`mailto:${c.email}?subject=Convite&body=${encodeURIComponent(aplicarPlaceholders(msgEmail, c.primeiro_nome, c.sobrenome || '', (c as Contato & { eventoNome?: string }).eventoNome || ''))}`}>
                {c.primeiro_nome}
              </a>
            ))}
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 6 }}>WhatsApp individual:</div>
          <div>
            {selecionados.filter((c) => c.whatsapp).map((c) => (
              <a key={c.id} className={`${cs.linkBtn} ${cs.linkWhatsapp}`} target="_blank" rel="noreferrer"
                 href={`https://wa.me/${c.whatsapp!.replace(/\D/g, '')}?text=${encodeURIComponent(aplicarPlaceholders(msgWhatsapp, c.primeiro_nome, c.sobrenome || '', (c as Contato & { eventoNome?: string }).eventoNome || ''))}`}>
                {c.primeiro_nome}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ───────────────────────────── Parcerias ─────────────────────────────

function ParceriasTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [nome, setNome] = useState('')
  const [tipo, setTipo] = useState<TipoParceiro>('Advogado')

  const { data: parceiros = [], isLoading } = useQuery({ queryKey: ['conselho-parceiros'], queryFn: () => conselhoApi.listarParceiros() })

  const criar = useMutation({
    mutationFn: conselhoApi.criarParceiro,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['conselho-parceiros'] }); setShowForm(false); setNome('') },
  })
  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Parceiro> }) => conselhoApi.atualizarParceiro(id, data as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-parceiros'] }),
  })
  const deletar = useMutation({
    mutationFn: conselhoApi.deletarParceiro,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-parceiros'] }),
  })

  return (
    <div>
      <button className={styles.btnPrimary} onClick={() => setShowForm((s) => !s)} style={{ marginBottom: 16 }}>
        {showForm ? 'Cancelar' : '+ Nova parceria'}
      </button>
      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}><label className={styles.formLabel}>Nome</label><input className={styles.input} value={nome} onChange={(e) => setNome(e.target.value)} /></div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Tipo</label>
            <select className={styles.input} value={tipo} onChange={(e) => setTipo(e.target.value as TipoParceiro)}>
              {TIPOS_PARCEIRO.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <button className={styles.btnPrimary} disabled={!nome} onClick={() => criar.mutate({ nome, tipo })}>Criar</button>
        </div>
      )}
      {isLoading ? <p>Carregando...</p> : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead><tr><th>Nome</th><th>Tipo</th><th>Status</th><th>Último encaminhamento</th><th>Plano</th><th></th></tr></thead>
            <tbody>
              {parceiros.map((p) => (
                <tr key={p.id}>
                  <td>{p.nome}</td>
                  <td>{p.tipo}</td>
                  <td>
                    <select className={styles.input} style={{ padding: '4px 6px', fontSize: 12 }} value={p.status}
                      onChange={(e) => atualizar.mutate({ id: p.id, data: { status: e.target.value as StatusParceiro } })}>
                      {STATUS_PARCEIRO.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td>{fmtData(p.ultimo_encaminhamento)}</td>
                  <td>{p.plano || '—'}</td>
                  <td><button className={styles.btnDanger} onClick={() => deletar.mutate(p.id)}>Excluir</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {parceiros.length === 0 && <div className={styles.empty}>Nenhuma parceria cadastrada</div>}
        </div>
      )}
    </div>
  )
}

// ───────────────────────────── Métricas ─────────────────────────────

function MetricasTab() {
  const qc = useQueryClient()
  const [numero, setNumero] = useState('')
  const [nota, setNota] = useState('')

  const { data: metricas } = useQuery({ queryKey: ['conselho-metricas'], queryFn: () => conselhoApi.obterMetricas() })
  const { data: logs = [] } = useQuery({ queryKey: ['conselho-logs'], queryFn: () => conselhoApi.listarLogs() })

  const criarLog = useMutation({
    mutationFn: conselhoApi.criarLog,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conselho-logs'] })
      qc.invalidateQueries({ queryKey: ['conselho-metricas'] })
      setNumero(''); setNota('')
    },
  })

  return (
    <div>
      <div className={cs.metricGrid}>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.media_logs_7d.toFixed(1) ?? '—'}</div><div className={cs.metricLabel}>Média 7 dias</div></div>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.total_contatos ?? '—'}</div><div className={cs.metricLabel}>Total contatos</div></div>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.contatos_participaram_ao_menos_uma_vez ?? '—'}</div><div className={cs.metricLabel}>Participaram 1x+</div></div>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.contatos_reconvidados ?? '—'}</div><div className={cs.metricLabel}>Reconvidados</div></div>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.contatos_reiterados ?? '—'}</div><div className={cs.metricLabel}>Reiterados (2x+)</div></div>
      </div>

      <h4 style={{ marginBottom: 8 }}>Registro diário</h4>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, alignItems: 'flex-end' }}>
        <input className={styles.input} style={{ maxWidth: 140 }} type="number" placeholder="Número" value={numero} onChange={(e) => setNumero(e.target.value)} />
        <input className={styles.input} style={{ maxWidth: 240 }} placeholder="Nota (opcional)" value={nota} onChange={(e) => setNota(e.target.value)} />
        <button
          className={styles.btnPrimary}
          disabled={!numero}
          onClick={() => criarLog.mutate({ data: new Date().toISOString().slice(0, 10), numero: Number(numero), nota: nota || undefined })}
        >
          Registrar
        </button>
      </div>

      <div className={styles.tableCard}>
        <table className={styles.table}>
          <thead><tr><th>Data</th><th>Número</th><th>Nota</th></tr></thead>
          <tbody>
            {logs.map((l: LogDiario) => (
              <tr key={l.id}><td>{fmtData(l.data)}</td><td>{l.numero}</td><td>{l.nota || '—'}</td></tr>
            ))}
          </tbody>
        </table>
        {logs.length === 0 && <div className={styles.empty}>Nenhum registro ainda</div>}
      </div>
    </div>
  )
}
