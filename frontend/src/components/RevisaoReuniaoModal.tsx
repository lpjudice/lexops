import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Sparkles, CheckCircle, XCircle, Clock, FileText, ClipboardList, BookOpen, Link } from 'lucide-react'
import { reunioesApi } from '../api/reunioes'
import type { Reuniao, AcaoSugerida, TipoAcao } from '../api/reunioes'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import ClienteCombobox from './ClienteCombobox'
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

  function toggleAcao(idx: number, aprovada: boolean | null) {
    setAcoes((prev) => prev.map((a, i) => i === idx ? { ...a, aprovada } : a))
  }

  function updateAcao(idx: number, field: string, value: string | number | null) {
    setAcoes((prev) => prev.map((a, i) => i === idx ? { ...a, [field]: value } : a))
  }

  const processosFiltrados = processos.filter((p: { cliente_id: string | null }) => !clienteId || p.cliente_id === clienteId)
  const aprovadas = acoes.filter((a) => a.aprovada === true).length
  const semResposta = acoes.filter((a) => a.aprovada === null).length

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
        </div>

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
        <div className={styles.body}>
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
                      className={`${styles.acaoCard} ${acao.aprovada === true ? styles.acaoAprovada : acao.aprovada === false ? styles.acaoRecusada : ''}`}
                    >
                      <div className={styles.acaoHeader}>
                        <span
                          className={styles.acaoTipo}
                          style={{ background: TIPO_BG[acao.tipo], color: TIPO_COLOR[acao.tipo] }}
                        >
                          {TIPO_ICON[acao.tipo]} {TIPO_LABEL[acao.tipo]}
                        </span>
                        <div className={styles.acaoControls}>
                          <button
                            className={`${styles.acaoBtn} ${acao.aprovada === true ? styles.acaoBtnAtivo : ''}`}
                            onClick={() => toggleAcao(idx, acao.aprovada === true ? null : true)}
                            title="Aprovar"
                          >
                            <CheckCircle size={16} />
                          </button>
                          <button
                            className={`${styles.acaoBtn} ${styles.acaoBtnRejeitar} ${acao.aprovada === false ? styles.acaoBtnAtivoRed : ''}`}
                            onClick={() => toggleAcao(idx, acao.aprovada === false ? null : false)}
                            title="Rejeitar"
                          >
                            <XCircle size={16} />
                          </button>
                        </div>
                      </div>

                      <div className={styles.acaoFields}>
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
        <div className={styles.footer}>
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
            disabled={confirmarMut.isPending || reuniao.status === 'processada'}
          >
            {confirmarMut.isPending
              ? 'Criando...'
              : reuniao.status === 'processada'
              ? 'Ações já criadas'
              : `Criar ${aprovadas} ação(ões) aprovada(s)`}
          </button>
        </div>
      </div>
    </div>
  )
}
