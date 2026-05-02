import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Sparkles, CheckCircle, XCircle, Clock, FileText, ClipboardList, BookOpen, Link, Lock, LockOpen, UserCheck } from 'lucide-react'
import { reunioesApi } from '../api/reunioes'
import type { Reuniao, AcaoSugerida, TipoAcao } from '../api/reunioes'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import ClienteCombobox from './ClienteCombobox'
import { useAuth } from '../contexts/AuthContext'
import styles from './RevisaoReuniaoModal.module.css'
import p from '../pages/Page.module.css'

const TIPO_LABEL: Record<TipoAcao, string> = {
  tarefa: 'Tarefa',
  contrato: 'Contrato',
  anotacao: 'Anotação',
}

const TIPO_ICON: Record<TipoAcao, React.ReactNode> = {
  tarefa: <ClipboardList size={14} />,
  contrato: <FileText size={14} />,
  anotacao: <BookOpen size={14} />,
}

const TIPO_COLOR: Record<TipoAcao, string> = {
  tarefa: '#0369a1',
  contrato: '#7c3aed',
  anotacao: '#0f766e',
}

const TIPO_BG: Record<TipoAcao, string> = {
  tarefa: '#e0f2fe',
  contrato: '#ede9fe',
  anotacao: '#ccfbf1',
}

function formatDateTime(d: string | null) {
  if (!d) return ''
  return new Date(d).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

interface Props {
  reuniao: Reuniao
  onClose: () => void
}

export default function RevisaoReuniaoModal({ reuniao: initialReuniao, onClose }: Props) {
  const qc = useQueryClient()
  const { usuario, isSuperAdmin } = useAuth()

  const { data: reuniao = initialReuniao } = useQuery({
    queryKey: ['reuniao', initialReuniao.id],
    queryFn: () => reunioesApi.obter(initialReuniao.id),
    initialData: initialReuniao,
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
    enabled: !!reuniao.cliente_id,
  })

  const [clienteId, setClienteId] = useState(reuniao.cliente_id ?? '')
  const [processoId, setProcessoId] = useState(reuniao.processo_id ?? '')
  const [resumo, setResumo] = useState(reuniao.resumo_ia ?? '')
  const [acoes, setAcoes] = useState<AcaoSugerida[]>(reuniao.acoes_sugeridas ?? [])
  const [tab, setTab] = useState<'transcricao' | 'acoes'>('acoes')

  const isCreator = usuario && reuniao.criado_por_id === usuario.id
  const canManageAccess = isCreator || isSuperAdmin
  const acessoRestrito = reuniao.acesso_restrito

  useEffect(() => {
    setAcoes(reuniao.acoes_sugeridas ?? [])
    setResumo(reuniao.resumo_ia ?? '')
    setClienteId(reuniao.cliente_id ?? '')
    setProcessoId(reuniao.processo_id ?? '')
  }, [reuniao])

  const processarMut = useMutation({
    mutationFn: async () => {
      // Salva cliente/processo antes de processar
      await reunioesApi.atualizar(reuniao.id, {
        cliente_id: clienteId || null,
        processo_id: processoId || null,
      })
      return reunioesApi.processar(reuniao.id)
    },
    onSuccess: (r) => {
      setAcoes(r.acoes_sugeridas ?? [])
      setResumo(r.resumo_ia ?? '')
      qc.invalidateQueries({ queryKey: ['reuniao', reuniao.id] })
      setTab('acoes')
    },
    onError: () => alert('Erro ao processar transcrição com IA.'),
  })

  const salvarMut = useMutation({
    mutationFn: () => reunioesApi.atualizar(reuniao.id, {
      cliente_id: clienteId || null,
      processo_id: processoId || null,
      resumo_ia: resumo,
      acoes_sugeridas: acoes,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reuniao', reuniao.id] }),
  })

  const confirmarMut = useMutation({
    mutationFn: async () => {
      await salvarMut.mutateAsync()
      return reunioesApi.confirmarAcoes(reuniao.id, acoes)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reunioes'] })
      alert('Ações criadas com sucesso!')
      onClose()
    },
    onError: (e: Error) => alert(`Erro ao confirmar ações: ${e.message}`),
  })

  const toggleConfidencialMut = useMutation({
    mutationFn: () => reunioesApi.atualizar(reuniao.id, { confidencial: !reuniao.confidencial }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reuniao', reuniao.id] }),
  })

  const solicitarAcessoMut = useMutation({
    mutationFn: () => reunioesApi.solicitarAcesso(reuniao.id),
    onSuccess: (r) => alert(r.mensagem),
    onError: () => alert('Erro ao solicitar acesso.'),
  })

  const concederAcessoMut = useMutation({
    mutationFn: (usuarioId: string) => reunioesApi.concederAcesso(reuniao.id, usuarioId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reuniao', reuniao.id] }),
    onError: () => alert('Erro ao conceder acesso.'),
  })

  const revogarAcessoMut = useMutation({
    mutationFn: (usuarioId: string) => reunioesApi.revogarAcesso(reuniao.id, usuarioId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reuniao', reuniao.id] }),
    onError: () => alert('Erro ao rejeitar solicitação.'),
  })

  const pedidos = reuniao.pedidos_acesso ?? []

  function toggleAcao(idx: number, aprovada: boolean | null) {
    setAcoes((prev) => prev.map((a, i) => i === idx ? { ...a, aprovada } : a))
  }

  function updateAcao(idx: number, field: string, value: string | number | null | boolean) {
    setAcoes((prev) => prev.map((a, i) => i === idx ? { ...a, [field]: value } : a))
  }

  function toggleAcaoConfidencial(idx: number) {
    setAcoes((prev) => prev.map((a, i) => i === idx ? { ...a, confidencial: !a.confidencial } : a))
  }

  const processosFiltrados = processos.filter((p: { cliente_id: string | null }) => !clienteId || p.cliente_id === clienteId)
  // Only count non-already-created actions
  const aprovadas = acoes.filter((a) => a.aprovada === true && !a.criada).length
  const semResposta = acoes.filter((a) => a.aprovada === null && !a.criada).length

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.icon}><Sparkles size={16} /></div>
            <div>
              <div className={styles.title}>{reuniao.titulo}</div>
              <div className={styles.subtitle}>
                {formatDateTime(reuniao.data_reuniao) || 'Sem data'} · {reuniao.fonte === 'drive_auto' ? 'Drive' : 'Manual'}
              </div>
            </div>
          </div>
          <button className={styles.closeBtn} onClick={onClose}><X size={18} /></button>
        </div>

        {/* Meta: cliente + processo */}
        <div className={styles.meta}>
          <div className={styles.metaRow} style={{ alignItems: 'flex-start', flexDirection: 'column', gap: 4 }}>
            <label className={styles.metaLabel}>Cliente</label>
            <div style={{ minWidth: 260 }}>
              <ClienteCombobox
                value={clienteId}
                onChange={(id) => { setClienteId(id); setProcessoId('') }}
                clientes={clientes}
                onCreateCliente={async () => ''}
              />
            </div>
          </div>
          {clienteId && processosFiltrados.length > 0 && (
            <div className={styles.metaRow}>
              <label className={styles.metaLabel}>Processo</label>
              <select
                className={styles.metaSelect}
                value={processoId}
                onChange={(e) => setProcessoId(e.target.value)}
              >
                <option value="">Nenhum</option>
                {processosFiltrados.map((pr: { id: string; numero_cnj: string }) => (
                  <option key={pr.id} value={pr.id}>{pr.numero_cnj}</option>
                ))}
              </select>
            </div>
          )}
          {reuniao.drive_tldr_file_id && (
            <a href={reuniao.drive_tldr_file_id} target="_blank" rel="noreferrer" className={styles.driveLink}>
              <Link size={12} /> TLDR salvo no Drive
            </a>
          )}
          {reuniao.criado_por_nome && (
            <div className={styles.driveLink} style={{ color: '#6b7280' }}>
              <UserCheck size={12} /> Criado por {reuniao.criado_por_nome}{isCreator ? ' (você)' : ''}
            </div>
          )}
          {canManageAccess && (
            <button
              className={styles.driveLink}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: reuniao.confidencial ? '#9333ea' : '#6b7280' }}
              onClick={() => toggleConfidencialMut.mutate()}
              title={reuniao.confidencial ? 'Tornar pública' : 'Tornar confidencial'}
            >
              {reuniao.confidencial ? <><Lock size={12} /> Confidencial</> : <><LockOpen size={12} /> Pública</>}
            </button>
          )}
          {!canManageAccess && reuniao.confidencial && !acessoRestrito && (
            <div className={styles.driveLink} style={{ color: '#9333ea' }}>
              <Lock size={12} /> Reunião confidencial
            </div>
          )}
        </div>

        {/* Pending access requests — visible only to creator / super_admin */}
        {canManageAccess && pedidos.length > 0 && (
          <div style={{ padding: '10px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#92400e' }}>
              🔔 {pedidos.length} solicitação(ões) de acesso pendente(s)
            </div>
            {pedidos.map((req) => (
              <div key={req.usuario_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: '#374151' }}>{req.nome}</span>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    className={p.btnPrimary}
                    style={{ fontSize: 11, padding: '2px 10px', background: '#059669' }}
                    onClick={() => concederAcessoMut.mutate(req.usuario_id)}
                    disabled={concederAcessoMut.isPending}
                  >
                    Conceder
                  </button>
                  <button
                    className={p.btnTable}
                    style={{ fontSize: 11, padding: '2px 10px', color: '#dc2626' }}
                    onClick={() => revogarAcessoMut.mutate(req.usuario_id)}
                    disabled={revogarAcessoMut.isPending}
                  >
                    Recusar
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Restricted access banner */}
        {acessoRestrito && (
          <div style={{ padding: '16px 20px', background: '#faf5ff', borderBottom: '1px solid #e9d5ff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#7c3aed', fontSize: 13 }}>
              <Lock size={14} />
              <span>Esta reunião é confidencial. Você não tem acesso ao conteúdo.</span>
            </div>
            <button
              className={p.btnPrimary}
              style={{ background: '#7c3aed', fontSize: 12, padding: '4px 12px' }}
              onClick={() => solicitarAcessoMut.mutate()}
              disabled={solicitarAcessoMut.isPending}
            >
              {solicitarAcessoMut.isPending ? 'Solicitando...' : 'Solicitar acesso'}
            </button>
          </div>
        )}

        {/* Tabs */}
        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${tab === 'acoes' ? styles.tabActive : ''}`}
            onClick={() => setTab('acoes')}
          >
            Ações {acoes.length > 0 && <span className={styles.tabCount}>{acoes.length}</span>}
          </button>
          <button
            className={`${styles.tab} ${tab === 'transcricao' ? styles.tabActive : ''}`}
            onClick={() => setTab('transcricao')}
          >
            Transcrição
          </button>
        </div>

        {/* Body */}
        <div className={styles.body} style={acessoRestrito ? { pointerEvents: 'none', opacity: 0.35 } : {}}>
          {tab === 'acoes' ? (
            <>
              {/* TLDR */}
              {(resumo || reuniao.status === 'em_revisao' || reuniao.status === 'processada') && (
                <div className={styles.resumoBlock}>
                  <label className={styles.sectionLabel}>Resumo (TLDR)</label>
                  <textarea
                    className={styles.resumoArea}
                    value={resumo}
                    onChange={(e) => setResumo(e.target.value)}
                    rows={4}
                    placeholder="Resumo gerado pela IA..."
                  />
                </div>
              )}

              {/* Processar button */}
              {reuniao.status === 'pendente' && (
                <div className={styles.processarHint}>
                  <p>Clique em <strong>Processar com IA</strong> para gerar o resumo e as ações sugeridas.</p>
                  <button
                    className={p.btnPrimary}
                    onClick={() => {
                      if (!reuniao.transcricao_texto) {
                        alert('Esta reunião não tem texto de transcrição. Adicione o texto na aba Transcrição.')
                        return
                      }
                      processarMut.mutate()
                    }}
                    disabled={processarMut.isPending}
                  >
                    <Sparkles size={13} />
                    {processarMut.isPending ? 'Processando...' : 'Processar com IA'}
                  </button>
                </div>
              )}

              {/* Ações list */}
              {acoes.length > 0 && (
                <div className={styles.acoesList}>
                  <div className={styles.sectionLabel}>
                    Ações sugeridas — {aprovadas} aprovada(s){semResposta > 0 ? `, ${semResposta} sem resposta` : ''}
                  </div>
                  {acoes.map((acao, idx) => (
                    <div
                      key={idx}
                      className={`${styles.acaoCard} ${acao.criada ? styles.acaoCriada : acao.aprovada === true ? styles.acaoAprovada : acao.aprovada === false ? styles.acaoRecusada : ''}`}
                    >
                      <div className={styles.acaoHeader}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                          <span
                            className={styles.acaoTipo}
                            style={{ background: TIPO_BG[acao.tipo], color: TIPO_COLOR[acao.tipo] }}
                          >
                            {TIPO_ICON[acao.tipo]} {TIPO_LABEL[acao.tipo]}
                          </span>
                          {acao.criada && (
                            <span style={{ fontSize: 11, color: '#16a34a', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 3 }}>
                              <CheckCircle size={11} /> Criada
                            </span>
                          )}
                          {acao.confidencial && !acao.criada && (
                            <span style={{ fontSize: 11, color: '#9333ea', display: 'flex', alignItems: 'center', gap: 3 }}>
                              <Lock size={11} /> confidencial
                            </span>
                          )}
                        </div>
                        <div className={styles.acaoControls}>
                          {/* Per-action confidential toggle */}
                          {!acao.criada && (
                            <button
                              className={styles.acaoBtn}
                              onClick={() => toggleAcaoConfidencial(idx)}
                              title={acao.confidencial ? 'Tornar pública' : 'Tornar confidencial'}
                              style={{ color: acao.confidencial ? '#9333ea' : '#9ca3af' }}
                            >
                              {acao.confidencial ? <Lock size={14} /> : <LockOpen size={14} />}
                            </button>
                          )}
                          <button
                            className={`${styles.acaoBtn} ${acao.aprovada === true ? styles.acaoBtnAtivo : ''}`}
                            onClick={() => !acao.criada && toggleAcao(idx, acao.aprovada === true ? null : true)}
                            title={acao.criada ? 'Já criada' : 'Aprovar'}
                            disabled={!!acao.criada}
                          >
                            <CheckCircle size={16} />
                          </button>
                          <button
                            className={`${styles.acaoBtn} ${styles.acaoBtnRejeitar} ${acao.aprovada === false ? styles.acaoBtnAtivoRed : ''}`}
                            onClick={() => !acao.criada && toggleAcao(idx, acao.aprovada === false ? null : false)}
                            title={acao.criada ? 'Já criada' : 'Rejeitar'}
                            disabled={!!acao.criada}
                          >
                            <XCircle size={16} />
                          </button>
                        </div>
                      </div>

                      <div className={styles.acaoFields} style={acao.criada ? { opacity: 0.45, pointerEvents: 'none' } : {}}>
                        <input
                          className={styles.acaoInput}
                          value={acao.titulo}
                          onChange={(e) => updateAcao(idx, 'titulo', e.target.value)}
                          placeholder="Título"
                        />

                        {(acao.tipo === 'tarefa' || acao.tipo === 'contrato') && (
                          <textarea
                            className={styles.acaoInput}
                            value={acao.descricao ?? ''}
                            onChange={(e) => updateAcao(idx, 'descricao', e.target.value)}
                            placeholder="Descrição"
                            rows={2}
                            style={{ resize: 'vertical' }}
                          />
                        )}

                        {acao.tipo === 'anotacao' && (
                          <textarea
                            className={styles.acaoInput}
                            value={acao.conteudo ?? ''}
                            onChange={(e) => updateAcao(idx, 'conteudo', e.target.value)}
                            placeholder="Conteúdo da anotação"
                            rows={3}
                            style={{ resize: 'vertical' }}
                          />
                        )}

                        {acao.tipo === 'tarefa' && (
                          <div className={styles.acaoInputRow}>
                            <div>
                              <label className={styles.acaoInputLabel}><Clock size={11} /> Prazo</label>
                              <input
                                type="date"
                                className={styles.acaoInput}
                                value={acao.data_limite ?? ''}
                                onChange={(e) => updateAcao(idx, 'data_limite', e.target.value || null)}
                              />
                            </div>
                            <div>
                              <label className={styles.acaoInputLabel}>Responsável</label>
                              <input
                                className={styles.acaoInput}
                                value={acao.responsavel ?? ''}
                                onChange={(e) => updateAcao(idx, 'responsavel', e.target.value || null)}
                                placeholder="Opcional"
                              />
                            </div>
                          </div>
                        )}

                        {acao.tipo === 'contrato' && acao.valor_mencionado != null && (
                          <div>
                            <label className={styles.acaoInputLabel}>Valor mencionado (R$)</label>
                            <input
                              type="number"
                              className={styles.acaoInput}
                              value={acao.valor_mencionado ?? ''}
                              onChange={(e) => updateAcao(idx, 'valor_mencionado', e.target.value ? parseFloat(e.target.value) : null)}
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Re-processar se já processada */}
              {(reuniao.status === 'em_revisao' || reuniao.status === 'processada') && (
                <button
                  className={styles.reprocessBtn}
                  onClick={() => processarMut.mutate()}
                  disabled={processarMut.isPending}
                >
                  <Sparkles size={12} />
                  {processarMut.isPending ? 'Processando...' : 'Re-processar com IA'}
                </button>
              )}
            </>
          ) : (
            /* Transcricao tab */
            <div className={styles.transcricaoTab}>
              <textarea
                className={styles.transcricaoArea}
                value={reuniao.transcricao_texto ?? ''}
                readOnly
                rows={20}
                placeholder="Nenhum texto de transcrição disponível."
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={styles.footer} style={acessoRestrito ? { pointerEvents: 'none', opacity: 0.35 } : {}}>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className={p.btnTable} onClick={salvarMut.mutate as () => void} disabled={salvarMut.isPending}>
              {salvarMut.isPending ? 'Salvando...' : 'Salvar rascunho'}
            </button>
            <button className={p.btnTable} onClick={onClose}>Fechar</button>
          </div>
          <button
            className={p.btnPrimary}
            onClick={() => {
              if (!clienteId) {
                alert('Vincule a reunião a um cliente antes de confirmar ações.')
                return
              }
              const temAprovadas = acoes.some((a) => a.aprovada === true)
              if (!temAprovadas) {
                alert('Aprove pelo menos uma ação antes de confirmar.')
                return
              }
              confirmarMut.mutate()
            }}
            disabled={confirmarMut.isPending || acessoRestrito}
          >
            {confirmarMut.isPending
              ? 'Criando...'
              : reuniao.status === 'processada'
              ? `Criar ${aprovadas} ação(ões) adicionais`
              : `Criar ${aprovadas} ação(ões) aprovada(s)`}
          </button>
        </div>
      </div>
    </div>
  )
}
