import { useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import { anotacoesApi } from '../api/anotacoes'
import { financeiroApi } from '../api/financeiro'
import type { HonorarioCreate, RecebimentoCreate } from '../api/financeiro'
import { contratosApi } from '../api/contratos'
import api from '../api/client'
import type { AnotacaoCreate, TipoAnotacao } from '../api/anotacoes'
import ClienteIA from '../components/ClienteIA'
import AnamneseForm from '../components/AnamneseForm'
import PropostaForm from '../components/PropostaForm'
import styles from './Page.module.css'
import detailStyles from './ClienteDetailPage.module.css'

const TIPOS_ANOTACAO: TipoAnotacao[] = ['reuniao', 'ligacao', 'whatsapp', 'email', 'documento', 'anamnese', 'outro']

const TIPO_ICON: Record<string, string> = {
  reuniao: '🤝', ligacao: '📞', whatsapp: '💬', email: '✉️',
  documento: '📄', anamnese: '📋', outro: '📝',
  prazo: '⏰', publicacao: '📰',
}

const TIPO_COLOR: Record<string, string> = {
  anotacao: detailStyles.itemAnotacao,
  prazo: detailStyles.itemPrazo,
  publicacao: detailStyles.itemPublicacao,
  email: detailStyles.itemEmail,
}

function formatDate(d: string) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}

type Aba = 'timeline' | 'anotacoes' | 'emails' | 'processos' | 'financeiro' | 'contratos' | 'ia'

export default function ClienteDetailPage() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const [aba, setAba] = useState<Aba>('timeline')
  const [showForm, setShowForm] = useState(false)
  const [expandido, setExpandido] = useState<string | null>(null)
  const [editandoAnotacao, setEditandoAnotacao] = useState<string | null>(null)
  const [editAnotacaoForm, setEditAnotacaoForm] = useState<{ titulo: string; texto: string; tipo: TipoAnotacao }>({ titulo: '', texto: '', tipo: 'outro' })
  const [showEmailForm, setShowEmailForm] = useState(false)
  const [emailInput, setEmailInput] = useState('')
  const [batchUploading, setBatchUploading] = useState(false)
  const [batchResultado, setBatchResultado] = useState<string | null>(null)
  const batchFileRef = useRef<HTMLInputElement>(null)
  const [propostaAberta, setPropostaAberta] = useState<string | null>(null) // anotacao.id
  const [form, setForm] = useState<AnotacaoCreate>({
    cliente_id: id!,
    tipo: 'reuniao',
    data_evento: new Date().toISOString().slice(0, 10),
    titulo: '',
    texto: '',
  })

  const { data: cliente, isError: clienteError, isLoading: clienteLoading } = useQuery({
    queryKey: ['cliente', id],
    queryFn: () => clientesApi.obter(id!),
    retry: 1,
  })

  const { data: timeline = [], isLoading: loadingTimeline } = useQuery({
    queryKey: ['timeline', id],
    queryFn: () => anotacoesApi.timeline(id!),
    enabled: aba === 'timeline' || aba === 'emails',
    staleTime: 5 * 60 * 1000,   // re-usa o cache por 5 min ao trocar de aba
    gcTime: 15 * 60 * 1000,
  })

  const { data: anotacoes = [], isLoading: loadingAnotacoes } = useQuery({
    queryKey: ['anotacoes', id],
    queryFn: () => anotacoesApi.listar({ cliente_id: id }),
    enabled: aba === 'anotacoes',
  })

  const { data: processos = [] } = useQuery({
    queryKey: ['processos', id],
    queryFn: () => processosApi.listar({ cliente_id: id }),
    enabled: aba === 'processos',
  })

  const { data: honorarios = [] } = useQuery({
    queryKey: ['honorarios', id],
    queryFn: () => financeiroApi.listarHonorarios({ cliente_id: id }),
    enabled: aba === 'financeiro',
  })

  const { data: contratos = [] } = useQuery({
    queryKey: ['contratos-cliente', id],
    queryFn: () => contratosApi.listar({ cliente_id: id }),
    enabled: aba === 'contratos',
  })

  // Financeiro form
  const [showHonorarioForm, setShowHonorarioForm] = useState(false)
  const [honForm, setHonForm] = useState<Partial<HonorarioCreate>>({
    descricao: '', tipo: 'fixo', valor_total: 0,
  })
  const [expandidoHon, setExpandidoHon] = useState<string | null>(null)
  const [recForm, setRecForm] = useState<Partial<RecebimentoCreate>>({
    valor: 0, data_recebimento: new Date().toISOString().slice(0, 10), forma_pagamento: 'pix',
  })

  const criarHonorario = useMutation({
    mutationFn: (data: HonorarioCreate) => financeiroApi.criarHonorario(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['honorarios', id] })
      setShowHonorarioForm(false)
      setHonForm({ descricao: '', tipo: 'fixo', valor_total: 0 })
    },
  })

  const adicionarRecebimento = useMutation({
    mutationFn: ({ honId, data }: { honId: string; data: RecebimentoCreate }) =>
      financeiroApi.adicionarRecebimento(honId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['honorarios', id] }),
  })

  const criar = useMutation({
    mutationFn: anotacoesApi.criar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['anotacoes', id] })
      qc.invalidateQueries({ queryKey: ['timeline', id] })
      setShowForm(false)
      setForm({ cliente_id: id!, tipo: 'reuniao', data_evento: new Date().toISOString().slice(0, 10), titulo: '', texto: '' })
    },
  })

  const atualizarAnotacao = useMutation({
    mutationFn: ({ aid, data }: { aid: string; data: Parameters<typeof anotacoesApi.atualizar>[1] }) =>
      anotacoesApi.atualizar(aid, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['anotacoes', id] })
      qc.invalidateQueries({ queryKey: ['timeline', id] })
      setEditandoAnotacao(null)
    },
  })

  const deletarAnotacao = useMutation({
    mutationFn: (aid: string) => anotacoesApi.deletar(aid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['anotacoes', id] })
      qc.invalidateQueries({ queryKey: ['timeline', id] })
    },
  })

  const atualizarCliente = useMutation({
    mutationFn: (data: { email?: string }) => clientesApi.atualizar(id!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cliente', id] })
      setShowEmailForm(false)
      setEmailInput('')
    },
  })

  const handleBatchUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBatchUploading(true)
    setBatchResultado(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const r = await api.post<{ id: string; numero_cnj: string }[]>(
        `/clientes/${id}/processos/batch`, form
      )
      qc.invalidateQueries({ queryKey: ['processos', id] })
      qc.invalidateQueries({ queryKey: ['processos'] })
      setBatchResultado(`${r.data.length} processo(s) importado(s) com sucesso.`)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setBatchResultado(`Erro: ${detail ?? 'falha ao importar'}`)
    } finally {
      setBatchUploading(false)
      if (batchFileRef.current) batchFileRef.current.value = ''
    }
  }

  const emailsTimeline = timeline.filter((i) => i.tipo === 'email')

  if (clienteLoading) return <p className={styles.empty}>Carregando...</p>
  if (clienteError || !cliente) return <p className={styles.empty}>Erro ao carregar cliente. <a href="/clientes">← Voltar</a></p>

  return (
    <div>
      {/* Cabeçalho */}
      <div className={detailStyles.header}>
        <Link to="/clientes" className={detailStyles.back}>← Clientes</Link>
        <div>
          <h1 className={styles.pageTitle}>{cliente.nome}</h1>
          <div className={detailStyles.clienteMeta}>
            <span className={styles.badge}>{cliente.tipo}</span>
            {cliente.cpf_cnpj && <span>{cliente.cpf_cnpj}</span>}
            {cliente.email && <span>✉️ {cliente.email}</span>}
            {cliente.telefone && <span>📞 {cliente.telefone}</span>}
          </div>
        </div>
      </div>

      {/* Projeto info + path */}
      <div className={detailStyles.projetoInfo}>
        {cliente.projeto_nome && (
          <>
            <span className={detailStyles.projetoNome}>{cliente.projeto_nome}</span>
            <code className={detailStyles.worktreeNome}>{cliente.worktree_nome}</code>
          </>
        )}
        <code className={detailStyles.pathLocal} title="Pasta de uploads do cliente (servidor)">
          📁 ./uploads/clientes/{cliente.id}/
        </code>
        {(() => {
          const pastaBase = localStorage.getItem('gestor_pasta_clientes') || '/Users/lucasjudice/Dropbox/Clientes/LexOps'
          const pastaCliente = `${pastaBase}/${cliente.nome}`
          return (
            <button
              className={detailStyles.pathLocal}
              title={`Copiar caminho: ${pastaCliente} (depois use Cmd+Shift+G no Finder)`}
              style={{ color: '#00b090', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'monospace', fontSize: 'inherit', padding: 0, marginLeft: 8 }}
              onClick={() => navigator.clipboard.writeText(pastaCliente)}
            >
              📂 Copiar pasta ↗
            </button>
          )
        })()}
      </div>

      {/* Abas */}
      <div className={detailStyles.abas}>
        {(['timeline', 'anotacoes', 'emails', 'processos', 'financeiro', 'contratos', 'ia'] as Aba[]).map((a) => (
          <button
            key={a}
            className={`${detailStyles.aba} ${aba === a ? detailStyles.abaAtiva : ''}`}
            onClick={() => setAba(a)}
          >
            {a === 'timeline' ? 'Timeline' :
             a === 'anotacoes' ? 'Anotações' :
             a === 'emails' ? `Emails${emailsTimeline.length ? ` (${emailsTimeline.length})` : ''}` :
             a === 'processos' ? 'Processos' :
             a === 'financeiro' ? `Financeiro${honorarios.length ? ` (${honorarios.length})` : ''}` :
             a === 'contratos' ? `Contratos${contratos.length ? ` (${contratos.length})` : ''}` :
             'IA & Docs'}
          </button>
        ))}
      </div>

      {/* ── Timeline ── */}
      {aba === 'timeline' && (
        <div className={detailStyles.timeline}>
          {loadingTimeline ? (
            <p className={styles.empty}>Carregando timeline...</p>
          ) : timeline.length === 0 ? (
            <p className={styles.empty}>Nenhum evento registrado.</p>
          ) : (
            timeline.map((item, i) => (
              <div key={`${item.referencia_id}-${i}`} className={`${detailStyles.timelineItem} ${TIPO_COLOR[item.tipo]}`}>
                <div className={detailStyles.timelineIcon}>
                  {TIPO_ICON[item.tipo === 'anotacao' ? (item.meta.tipo as string) : item.tipo] || '•'}
                </div>
                <div className={detailStyles.timelineContent}>
                  <div className={detailStyles.timelineHeader}>
                    <strong>{item.titulo}</strong>
                    <span className={detailStyles.timelineData}>{formatDate(item.data)}</span>
                  </div>
                  {item.subtitulo && <div className={detailStyles.subtitulo}>{item.subtitulo}</div>}
                  {item.texto && (
                    <p
                      className={`${detailStyles.timelineTexto} ${expandido === `${item.referencia_id}-${i}` ? detailStyles.expandido : ''}`}
                      onClick={() => setExpandido(expandido === `${item.referencia_id}-${i}` ? null : `${item.referencia_id}-${i}`)}
                    >
                      {item.texto}
                    </p>
                  )}
                  {item.tipo === 'prazo' && !!item.meta.status && (
                    <span className={detailStyles[`prazoStatus_${String(item.meta.status)}`]}>
                      {String(item.meta.status)}
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Anotações ── */}
      {aba === 'anotacoes' && (
        <div>
          <div className={detailStyles.abaHeader}>
            <button className={styles.btnPrimary} onClick={() => {
              setForm({ ...form, tipo: 'reuniao' })
              setShowForm(!showForm)
            }}>
              {showForm && form.tipo !== 'anamnese' ? 'Cancelar' : '+ Nova Anotação'}
            </button>
            {!showForm && (
              <button className={detailStyles.btnAnamnese} onClick={() => {
                setForm({ ...form, tipo: 'anamnese' })
                setShowForm(true)
              }}>
                📋 Nova Anamnese
              </button>
            )}
          </div>

          {showForm && (
            form.tipo === 'anamnese' ? (
              <AnamneseForm
                isSaving={criar.isPending}
                onCancel={() => { setShowForm(false); setForm({ ...form, tipo: 'reuniao' }) }}
                onSave={(texto, titulo) => criar.mutate({ ...form, texto, titulo })}
              />
            ) : (
              <form
                onSubmit={(e) => { e.preventDefault(); criar.mutate(form) }}
                className={styles.form}
              >
                <div className={detailStyles.twoCol}>
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Tipo</label>
                    <select className={styles.input} value={form.tipo}
                      onChange={(e) => setForm({ ...form, tipo: e.target.value as TipoAnotacao })}>
                      {TIPOS_ANOTACAO.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Data</label>
                    <input type="date" className={styles.input} value={form.data_evento}
                      onChange={(e) => setForm({ ...form, data_evento: e.target.value })} required />
                  </div>
                </div>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>Título</label>
                  <input className={styles.input} value={form.titulo}
                    onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
                </div>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>Texto *</label>
                  <textarea className={styles.input} rows={5} value={form.texto}
                    onChange={(e) => setForm({ ...form, texto: e.target.value })} required />
                </div>
                <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
                  {criar.isPending ? 'Salvando...' : 'Salvar'}
                </button>
              </form>
            )
          )}

          {loadingAnotacoes ? <p className={styles.empty}>Carregando...</p> :
           anotacoes.length === 0 ? <p className={styles.empty}>Nenhuma anotação.</p> : (
            <div className={detailStyles.anotacoesList}>
              {anotacoes.map((a) => (
                <div key={a.id} className={detailStyles.anotacaoCard}>
                  <div className={detailStyles.anotacaoHeader}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span>{TIPO_ICON[a.tipo]}</span>
                      <strong>{a.titulo || a.tipo}</strong>
                      <span className={detailStyles.anotacaoData}>{formatDate(a.data_evento)}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button className={styles.btnTable}
                        onClick={() => {
                          if (editandoAnotacao === a.id) { setEditandoAnotacao(null); return }
                          setEditandoAnotacao(a.id)
                          setEditAnotacaoForm({ titulo: a.titulo ?? '', texto: a.texto, tipo: a.tipo as TipoAnotacao })
                        }}>
                        {editandoAnotacao === a.id ? 'Cancelar' : 'Editar'}
                      </button>
                      <button className={styles.btnDanger}
                        onClick={() => { if (confirm('Remover anotação?')) deletarAnotacao.mutate(a.id) }}>
                        ×
                      </button>
                    </div>
                  </div>
                  {editandoAnotacao === a.id ? (
                    <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <div className={detailStyles.twoCol}>
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Tipo</label>
                          <select className={styles.input} value={editAnotacaoForm.tipo}
                            onChange={(e) => setEditAnotacaoForm({ ...editAnotacaoForm, tipo: e.target.value as TipoAnotacao })}>
                            {TIPOS_ANOTACAO.map((t) => <option key={t} value={t}>{t}</option>)}
                          </select>
                        </div>
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Título</label>
                          <input className={styles.input} value={editAnotacaoForm.titulo}
                            onChange={(e) => setEditAnotacaoForm({ ...editAnotacaoForm, titulo: e.target.value })} />
                        </div>
                      </div>
                      <div className={styles.formRow}>
                        <label className={styles.formLabel}>Texto</label>
                        <textarea className={styles.input} rows={4} value={editAnotacaoForm.texto}
                          onChange={(e) => setEditAnotacaoForm({ ...editAnotacaoForm, texto: e.target.value })} />
                      </div>
                      <button className={styles.btnPrimary} style={{ alignSelf: 'flex-start' }}
                        disabled={atualizarAnotacao.isPending}
                        onClick={() => atualizarAnotacao.mutate({ aid: a.id, data: editAnotacaoForm })}>
                        {atualizarAnotacao.isPending ? 'Salvando...' : 'Salvar'}
                      </button>
                    </div>
                  ) : (
                    <>
                      <p className={detailStyles.anotacaoTexto}>{a.texto}</p>
                      {a.tipo === 'anamnese' && (
                        propostaAberta === a.id ? (
                          <PropostaForm
                            clienteId={id!}
                            clienteNome={cliente.nome}
                            anamneseTexto={a.texto}
                            onClose={() => setPropostaAberta(null)}
                          />
                        ) : (
                          <button
                            className={detailStyles.btnProposta}
                            onClick={() => setPropostaAberta(a.id)}
                          >
                            📄 Gerar Proposta
                          </button>
                        )
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Emails ── */}
      {aba === 'emails' && (
        <div>
          {!cliente.email ? (
            <div>
              <p className={styles.empty}>Cliente sem email cadastrado.</p>
              {!showEmailForm ? (
                <div style={{ textAlign: 'center', marginTop: '8px' }}>
                  <button className={styles.btnPrimary} onClick={() => setShowEmailForm(true)}>
                    + Cadastrar Email
                  </button>
                </div>
              ) : (
                <div className={detailStyles.emailFormInline}>
                  <input
                    className={styles.input}
                    type="email"
                    placeholder="email@exemplo.com"
                    value={emailInput}
                    onChange={(e) => setEmailInput(e.target.value)}
                    autoFocus
                  />
                  <button className={styles.btnPrimary}
                    disabled={!emailInput || atualizarCliente.isPending}
                    onClick={() => atualizarCliente.mutate({ email: emailInput })}>
                    Salvar
                  </button>
                  <button className={styles.btnTable} onClick={() => { setShowEmailForm(false); setEmailInput('') }}>
                    Cancelar
                  </button>
                </div>
              )}
            </div>
          ) : loadingTimeline ? (
            <p className={styles.empty}>Carregando emails...</p>
          ) : emailsTimeline.length === 0 ? (
            <p className={styles.empty}>Nenhum email encontrado para {cliente.email}.</p>
          ) : (
            <div className={detailStyles.emailsList}>
              {emailsTimeline.map((e, i) => (
                <div key={`email-${i}`} className={detailStyles.emailCard}
                  onClick={() => setExpandido(expandido === `email-${i}` ? null : `email-${i}`)}>
                  <div className={detailStyles.emailHeader}>
                    <div>
                      <strong>{e.titulo}</strong>
                      <div className={detailStyles.emailMeta}>
                        {e.subtitulo} → {String(e.meta.para ?? '')}
                      </div>
                    </div>
                    <div className={detailStyles.emailHeaderRight}>
                      <span className={detailStyles.anotacaoData}>{formatDate(e.data)}</span>
                      {e.referencia_id && (
                        <a
                          href={`https://mail.google.com/mail/u/0/#all/${e.referencia_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={detailStyles.btnGmail}
                          onClick={(ev) => ev.stopPropagation()}
                        >
                          Gmail ↗
                        </a>
                      )}
                    </div>
                  </div>
                  {expandido === `email-${i}` && !!e.meta.corpo && (
                    <pre className={detailStyles.emailCorpo}>{String(e.meta.corpo)}</pre>
                  )}
                  {expandido !== `email-${i}` && (
                    <p className={detailStyles.emailSnippet}>{e.texto}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Processos ── */}
      {aba === 'processos' && (
        <div>
          {/* Barra de ações em lote */}
          <div className={detailStyles.processosToolbar}>
            <a
              className={styles.btnTable}
              href={`/api/clientes/${id}/processos/template-xls`}
              download
            >
              ⬇ Template XLS
            </a>
            <label className={`${styles.btnTable} ${batchUploading ? '' : ''}`} style={{ cursor: 'pointer' }}>
              {batchUploading ? '⏳ Importando...' : '⬆ Importar XLS'}
              <input
                ref={batchFileRef}
                type="file"
                accept=".xlsx,.xls"
                style={{ display: 'none' }}
                disabled={batchUploading}
                onChange={handleBatchUpload}
              />
            </label>
            {batchResultado && (
              <span className={batchResultado.startsWith('Erro') ? detailStyles.batchErro : detailStyles.batchOk}>
                {batchResultado}
              </span>
            )}
          </div>

          {processos.length === 0 ? (
            <p className={styles.empty}>Nenhum processo vinculado.</p>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Nº CNJ</th>
                  <th>Polo</th>
                  <th>Tribunal</th>
                  <th>Matéria</th>
                  <th>Fase</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {processos.map((p) => (
                  <tr key={p.id}>
                    <td><code>{p.numero_cnj}</code></td>
                    <td>{p.polo || '—'}</td>
                    <td>{p.tribunal || p.estado}</td>
                    <td>{p.materia || '—'}</td>
                    <td>{p.fase || '—'}</td>
                    <td><span className={`${styles.badge} ${styles[`status_${p.status}`]}`}>{p.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Financeiro ── */}
      {aba === 'financeiro' && (
        <div>
          <div className={detailStyles.abaHeader}>
            <span className={detailStyles.abaHeaderTitle}>Honorários</span>
            <button className={styles.btnPrimary} onClick={() => setShowHonorarioForm(!showHonorarioForm)}>
              {showHonorarioForm ? 'Cancelar' : '+ Honorário'}
            </button>
          </div>

          {showHonorarioForm && (
            <form className={styles.form} onSubmit={(e) => {
              e.preventDefault()
              criarHonorario.mutate({ cliente_id: id!, ...honForm } as HonorarioCreate)
            }}>
              <div className={detailStyles.twoCol}>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>Descrição *</label>
                  <input className={styles.input} required value={honForm.descricao ?? ''}
                    onChange={(e) => setHonForm({ ...honForm, descricao: e.target.value })} />
                </div>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>Tipo</label>
                  <select className={styles.input} value={honForm.tipo}
                    onChange={(e) => setHonForm({ ...honForm, tipo: e.target.value as 'fixo' | 'percentual' | 'exito' })}>
                    <option value="fixo">Fixo</option>
                    <option value="percentual">Percentual</option>
                    <option value="exito">Êxito</option>
                  </select>
                </div>
              </div>
              <div className={detailStyles.twoCol}>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>Valor Total (R$) *</label>
                  <input type="number" className={styles.input} required min={0} step={0.01}
                    value={honForm.valor_total ?? ''}
                    onChange={(e) => setHonForm({ ...honForm, valor_total: parseFloat(e.target.value) || 0 })} />
                </div>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>Vencimento</label>
                  <input type="date" className={styles.input} value={honForm.data_vencimento ?? ''}
                    onChange={(e) => setHonForm({ ...honForm, data_vencimento: e.target.value })} />
                </div>
              </div>
              <button type="submit" className={styles.btnPrimary} disabled={criarHonorario.isPending}>
                {criarHonorario.isPending ? 'Salvando...' : 'Salvar Honorário'}
              </button>
            </form>
          )}

          {honorarios.length === 0 ? (
            <p className={styles.empty}>Nenhum honorário cadastrado para este cliente.</p>
          ) : (
            <div className={detailStyles.honList}>
              {honorarios.map((h) => {
                const pct = h.valor_total > 0 ? Math.min(100, (h.total_recebido / h.valor_total) * 100) : 0
                const isOpen = expandidoHon === h.id
                return (
                  <div key={h.id} className={detailStyles.honCard}>
                    <div className={detailStyles.honHeader} onClick={() => setExpandidoHon(isOpen ? null : h.id)}>
                      <div>
                        <div className={detailStyles.honDescricao}>{h.descricao}</div>
                        <div className={detailStyles.honMeta}>
                          {h.tipo} · R$ {h.valor_total.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                        </div>
                        <div className={detailStyles.honProgress}>
                          <div className={detailStyles.honProgressBar} style={{ width: `${pct}%` }} />
                        </div>
                        <div className={detailStyles.honProgressLabel}>
                          R$ {h.total_recebido.toLocaleString('pt-BR', { minimumFractionDigits: 2 })} recebido
                          · saldo R$ {h.saldo_pendente.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                        </div>
                      </div>
                      <span className={`${styles.badge} ${detailStyles[`status_hon_${h.status}`] || ''}`}>{h.status}</span>
                    </div>
                    {isOpen && (
                      <div className={detailStyles.honExpandido}>
                        {h.recebimentos.length > 0 && (
                          <table className={styles.table} style={{ marginBottom: '10px' }}>
                            <thead><tr><th>Data</th><th>Forma</th><th>Valor</th></tr></thead>
                            <tbody>
                              {h.recebimentos.map((r) => (
                                <tr key={r.id}>
                                  <td>{formatDate(r.data_recebimento)}</td>
                                  <td>{r.forma_pagamento}</td>
                                  <td>R$ {r.valor.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                        <div className={detailStyles.recForm}>
                          <input type="number" placeholder="Valor" min={0} step={0.01} className={styles.input}
                            style={{ flex: 1 }} value={recForm.valor || ''}
                            onChange={(e) => setRecForm({ ...recForm, valor: parseFloat(e.target.value) || 0 })} />
                          <input type="date" className={styles.input} value={recForm.data_recebimento}
                            onChange={(e) => setRecForm({ ...recForm, data_recebimento: e.target.value })} />
                          <select className={styles.input} value={recForm.forma_pagamento}
                            onChange={(e) => setRecForm({ ...recForm, forma_pagamento: e.target.value as 'pix' })}>
                            {['pix', 'ted', 'boleto', 'cheque', 'dinheiro', 'outro'].map((f) => (
                              <option key={f} value={f}>{f}</option>
                            ))}
                          </select>
                          <button className={styles.btnPrimary} onClick={() => {
                            if (!recForm.valor) return
                            adicionarRecebimento.mutate({ honId: h.id, data: recForm as RecebimentoCreate })
                          }}>+ Recebimento</button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Contratos ── */}
      {aba === 'contratos' && (
        <div>
          <div className={detailStyles.abaHeader}>
            <span className={detailStyles.abaHeaderTitle}>Contratos</span>
            <a href="/contratos" className={styles.btnTable} onClick={(e) => { e.preventDefault(); window.location.href='/contratos' }}>
              Ver todos →
            </a>
          </div>
          {contratos.length === 0 ? (
            <p className={styles.empty}>Nenhum contrato para este cliente.</p>
          ) : (
            <div className={detailStyles.contratoList}>
              {contratos.map((c) => {
                const STATUS_LABEL: Record<string, string> = {
                  rascunho: 'Rascunho',
                  aguardando_assinatura: 'Ag. Assinaturas',
                  parcialmente_assinado: 'Parcialmente Assinado',
                  assinado: 'Assinado',
                  cancelado: 'Cancelado',
                }
                return (
                  <div key={c.id} className={detailStyles.contratoCard}>
                    <div className={detailStyles.contratoHeader}>
                      <div>
                        <div className={detailStyles.contratoTitulo}>{c.titulo}</div>
                        <div className={detailStyles.contratoMeta}>
                          {c.arquivos?.length > 0
                            ? `${c.arquivos.length} arquivo(s)`
                            : c.arquivo_path ? '1 arquivo' : 'Sem arquivo'
                          }
                          {' · '}{c.signatarios.length} signatário(s)
                        </div>
                      </div>
                      <span className={`${styles.badge} ${detailStyles[`status_contrato_${c.status}`] || ''}`}>
                        {STATUS_LABEL[c.status] || c.status}
                      </span>
                    </div>
                    {c.signatarios.length > 0 && (
                      <div className={detailStyles.signatariosList}>
                        {c.signatarios.map((s) => (
                          <span key={s.id} className={`${detailStyles.signatarioBadge} ${s.status_assinatura === 'assinado' ? detailStyles.sigAssinado : ''}`}>
                            {s.nome} ({s.papel}) — {s.status_assinatura}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── IA & Docs ── */}
      {aba === 'ia' && (
        <ClienteIA clienteId={id!} />
      )}
    </div>
  )
}
