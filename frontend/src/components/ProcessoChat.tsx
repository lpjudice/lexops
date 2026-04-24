import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { processosApi } from '../api/processos'
import { conversasIaApi } from '../api/conversas_ia'
import type { ConversaIA } from '../api/conversas_ia'
import type { ChatMessage } from '../api/processos'
import styles from './ProcessoChat.module.css'

interface Props {
  processoId: string
  clienteId: string
  processoNome?: string
}

function baixarBlob(blob: Blob, nome: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nome
  a.click()
  URL.revokeObjectURL(url)
}

export default function ProcessoChat({ processoId, clienteId, processoNome }: Props) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Conversa ativa
  const [conversaId, setConversaId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [vistaHistorico, setVistaHistorico] = useState(false)

  // Documentos do processo
  const { data: docs = [] } = useQuery({
    queryKey: ['processo-docs', processoId],
    queryFn: () => processosApi.listarDocumentos(processoId),
  })

  // Conversas salvas deste processo
  const { data: conversas = [] } = useQuery({
    queryKey: ['conversas-ia-processo', processoId],
    queryFn: () => conversasIaApi.listar({ processo_id: processoId }),
    staleTime: 30_000,
  })

  // ── Mutações ──────────────────────────────────────────────────────────

  const criarConversa = useMutation({
    mutationFn: (historico: ChatMessage[]) =>
      conversasIaApi.criar(clienteId, 'gemini', historico, undefined, processoId),
    onSuccess: (nova) => {
      setConversaId(nova.id)
      qc.invalidateQueries({ queryKey: ['conversas-ia-processo', processoId] })
    },
  })

  const atualizarConversa = useMutation({
    mutationFn: ({ id, historico }: { id: string; historico: ChatMessage[] }) =>
      conversasIaApi.atualizar(id, { historico }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversas-ia-processo', processoId] })
    },
  })

  const deletarConversa = useMutation({
    mutationFn: (id: string) => conversasIaApi.deletar(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversas-ia-processo', processoId] })
    },
  })

  const compactarConversa = useMutation({
    mutationFn: (id: string) => conversasIaApi.compactar(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversas-ia-processo', processoId] })
    },
  })

  // ── Helpers ───────────────────────────────────────────────────────────

  const iniciarNovaConversa = () => {
    setConversaId(null)
    setMessages([])
    setInput('')
    setVistaHistorico(false)
  }

  const abrirConversa = (c: ConversaIA) => {
    setConversaId(c.id)
    setMessages(c.historico as ChatMessage[])
    setVistaHistorico(false)
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
  }

  const handleDeletar = async (id: string) => {
    if (!confirm('Deletar esta conversa?')) return
    if (id === conversaId) iniciarNovaConversa()
    await deletarConversa.mutateAsync(id)
  }

  const handleCompactar = async (id: string) => {
    await compactarConversa.mutateAsync(id)
    alert('Resumo gerado e salvo.')
  }

  const handleDownloadPdf = async (id: string, titulo: string | null) => {
    const blob = await conversasIaApi.downloadPdf(id)
    baixarBlob(blob, `${titulo || 'conversa'}.pdf`)
  }

  // ── Envio de mensagem ─────────────────────────────────────────────────

  const enviar = async () => {
    const pergunta = input.trim()
    if (!pergunta || loading) return

    const novoHistorico: ChatMessage[] = [...messages, { role: 'user', content: pergunta }]
    setMessages(novoHistorico)
    setInput('')
    setLoading(true)

    try {
      const historico = novoHistorico.slice(0, -1)
      const { resposta } = await processosApi.chat(processoId, pergunta, historico)
      const historicoFinal: ChatMessage[] = [...novoHistorico, { role: 'model', content: resposta }]
      setMessages(historicoFinal)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)

      // Persiste no banco
      if (!conversaId) {
        criarConversa.mutate(historicoFinal)
      } else {
        atualizarConversa.mutate({ id: conversaId, historico: historicoFinal })
      }
    } catch {
      setMessages([...novoHistorico, { role: 'model', content: '❌ Erro ao conectar com Gemini.' }])
    } finally {
      setLoading(false)
    }
  }

  // ── Upload de documento ───────────────────────────────────────────────

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (!files.length) return
    setUploading(true)
    try {
      for (const file of files) {
        await processosApi.uploadPdf(processoId, file)
      }
      qc.invalidateQueries({ queryKey: ['processo-docs', processoId] })
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const remover = async (filename: string) => {
    if (!confirm(`Remover ${filename}?`)) return
    await processosApi.removerDocumento(processoId, filename)
    qc.invalidateQueries({ queryKey: ['processo-docs', processoId] })
  }

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className={styles.root}>
      {/* Documentos */}
      <div className={styles.docsSection}>
        <div className={styles.docsHeader}>
          <span className={styles.docsTitle}>Documentos do Processo</span>
          <label className={styles.btnUpload}>
            {uploading ? 'Enviando...' : '+ PDF'}
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              multiple
              style={{ display: 'none' }}
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>
        {docs.length === 0 ? (
          <p className={styles.docsVazio}>
            Nenhum PDF adicionado. Suba os documentos do processo para o Gemini ler.
          </p>
        ) : (
          <ul className={styles.docsList}>
            {docs.map((d) => (
              <li key={d.filename} className={styles.docItem}>
                <span className={styles.docNome}>{d.filename}</span>
                <span className={styles.docTamanho}>{(d.size / 1024).toFixed(0)} KB</span>
                <button className={styles.btnRemoverDoc} onClick={() => remover(d.filename)}>×</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Chat */}
      <div className={styles.chatSection}>
        {/* Cabeçalho do chat */}
        <div className={styles.chatHeader}>
          <div className={styles.chatTitle}>
            Chat Gemini {processoNome ? `· ${processoNome}` : ''}
            {docs.length > 0 && (
              <span className={styles.chatContexto}>{docs.length} doc(s) no contexto</span>
            )}
          </div>
          <div className={styles.chatActions}>
            {conversaId && (
              <>
                <button
                  className={styles.btnAcao}
                  title="Baixar conversa em PDF"
                  onClick={() => handleDownloadPdf(conversaId, conversas.find(c => c.id === conversaId)?.titulo ?? null)}
                >
                  ↓ PDF
                </button>
                <button
                  className={styles.btnAcao}
                  title="Gerar resumo compacto"
                  onClick={() => handleCompactar(conversaId)}
                  disabled={compactarConversa.isPending}
                >
                  ⊙ Compactar
                </button>
              </>
            )}
            <button
              className={`${styles.btnAcao} ${vistaHistorico ? styles.btnAcaoAtivo : ''}`}
              onClick={() => setVistaHistorico(!vistaHistorico)}
              title="Ver conversas anteriores"
            >
              ☰ Histórico {conversas.length > 0 ? `(${conversas.length})` : ''}
            </button>
            <button className={styles.btnNova} onClick={iniciarNovaConversa}>
              + Nova
            </button>
          </div>
        </div>

        {/* Painel histórico */}
        {vistaHistorico && (
          <div className={styles.historicoPanel}>
            {conversas.length === 0 ? (
              <p className={styles.historicoVazio}>Nenhuma conversa salva.</p>
            ) : (
              conversas.map((c) => (
                <div
                  key={c.id}
                  className={`${styles.historicoItem} ${c.id === conversaId ? styles.historicoItemAtivo : ''}`}
                  onClick={() => abrirConversa(c)}
                >
                  <div className={styles.historicoNome}>
                    {c.parent_conversa_id ? '⊙ ' : ''}{c.titulo || `Conversa ${c.id.slice(0, 6)}`}
                  </div>
                  <div className={styles.historicoMeta}>
                    {c.historico.length} msg · {new Date(c.updated_at).toLocaleDateString('pt-BR')}
                  </div>
                  <div className={styles.historicoAcoes} onClick={(e) => e.stopPropagation()}>
                    <button
                      className={styles.btnHistAcao}
                      title="Baixar PDF"
                      onClick={() => handleDownloadPdf(c.id, c.titulo)}
                    >↓</button>
                    <button
                      className={styles.btnHistAcao}
                      title="Compactar"
                      onClick={() => handleCompactar(c.id)}
                    >⊙</button>
                    <button
                      className={`${styles.btnHistAcao} ${styles.btnHistDeletar}`}
                      title="Deletar"
                      onClick={() => handleDeletar(c.id)}
                    >×</button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {docs.length === 0 && !vistaHistorico && (
          <div className={styles.chatAviso}>
            Adicione PDFs do processo para o Gemini poder responder com contexto real.
            Sem documentos, o chat funcionará como um assistente jurídico genérico.
          </div>
        )}

        {!vistaHistorico && (
          <>
            <div className={styles.mensagens}>
              {messages.length === 0 && (
                <div className={styles.mensagemVazia}>
                  Faça uma pergunta sobre o processo...
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`${styles.mensagem} ${m.role === 'user' ? styles.mensagemUser : styles.mensagemModel}`}>
                  <div className={styles.mensagemBubble}>{m.content}</div>
                </div>
              ))}
              {loading && (
                <div className={`${styles.mensagem} ${styles.mensagemModel}`}>
                  <div className={`${styles.mensagemBubble} ${styles.loading}`}>⏳ Gemini está lendo os documentos...</div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <div className={styles.inputRow}>
              <textarea
                className={styles.chatInput}
                placeholder="Pergunta sobre o processo..."
                value={input}
                rows={2}
                disabled={loading}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    enviar()
                  }
                }}
              />
              <button className={styles.btnEnviar} onClick={enviar} disabled={!input.trim() || loading}>
                ↑
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
