import { useRef, useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { clientesApi } from '../api/clientes'
import type { ChatMessage } from '../api/clientes'
import { conversasIaApi } from '../api/conversas_ia'
import type { ConversaIA } from '../api/conversas_ia'
import styles from './ClienteIA.module.css'

type Modelo = 'claude' | 'gpt' | 'gemini'

const MODELOS: { key: Modelo; label: string }[] = [
  { key: 'claude', label: 'Claude' },
  { key: 'gpt', label: 'GPT-4o' },
  { key: 'gemini', label: 'Gemini' },
]

interface Props {
  clienteId: string
}

export default function ClienteIA({ clienteId }: Props) {
  const qc = useQueryClient()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [modelo, setModelo] = useState<Modelo>('claude')
  const [conversaAtualId, setConversaAtualId] = useState<string | null>(null)
  const [compactando, setCompactando] = useState(false)
  const [renomeandoId, setRenomeandoId] = useState<string | null>(null)
  const [novoTitulo, setNovoTitulo] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: docs = [] } = useQuery({
    queryKey: ['cliente-docs', clienteId],
    queryFn: () => clientesApi.listarDocumentos(clienteId),
  })

  const { data: conversas = [] } = useQuery({
    queryKey: ['conversas-ia', clienteId],
    queryFn: () => conversasIaApi.listar({ cliente_id: clienteId }),
  })

  const carregarConversa = (c: ConversaIA) => {
    setConversaAtualId(c.id)
    setMessages(c.historico)
    setModelo((c.modelo as Modelo) || 'claude')
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }

  const novaConversa = () => {
    setConversaAtualId(null)
    setMessages([])
    setInput('')
  }

  const deletarConversa = useMutation({
    mutationFn: (id: string) => conversasIaApi.deletar(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversas-ia', clienteId] })
      if (conversaAtualId) novaConversa()
    },
  })

  const enviar = async () => {
    const pergunta = input.trim()
    if (!pergunta || loading) return

    const novoHistorico: ChatMessage[] = [...messages, { role: 'user', content: pergunta }]
    setMessages(novoHistorico)
    setInput('')
    setLoading(true)

    try {
      const historico = novoHistorico.slice(0, -1)
      const { resposta } = await clientesApi.chat(clienteId, pergunta, historico, modelo)
      const historicoFinal: ChatMessage[] = [...novoHistorico, { role: 'model', content: resposta }]
      setMessages(historicoFinal)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)

      // Persiste no banco
      const tituloAuto = pergunta.slice(0, 60) + (pergunta.length > 60 ? '...' : '')
      if (conversaAtualId) {
        await conversasIaApi.atualizar(conversaAtualId, { historico: historicoFinal, modelo })
      } else {
        const nova = await conversasIaApi.criar(clienteId, modelo, historicoFinal, tituloAuto)
        setConversaAtualId(nova.id)
        qc.invalidateQueries({ queryKey: ['conversas-ia', clienteId] })
      }
      qc.invalidateQueries({ queryKey: ['conversas-ia', clienteId] })
    } catch {
      setMessages([...novoHistorico, { role: 'model', content: '❌ Erro ao conectar com a IA.' }])
    } finally {
      setLoading(false)
    }
  }

  const compactar = async () => {
    if (!conversaAtualId) return
    setCompactando(true)
    try {
      await conversasIaApi.compactar(conversaAtualId)
      qc.invalidateQueries({ queryKey: ['conversas-ia', clienteId] })
    } finally {
      setCompactando(false)
    }
  }

  const salvarRenome = async (id: string) => {
    if (!novoTitulo.trim()) { setRenomeandoId(null); return }
    await conversasIaApi.atualizar(id, { titulo: novoTitulo.trim() })
    qc.invalidateQueries({ queryKey: ['conversas-ia', clienteId] })
    setRenomeandoId(null)
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (!files.length) return
    setUploading(true)
    try {
      for (const file of files) {
        await clientesApi.uploadPdf(clienteId, file)
      }
      qc.invalidateQueries({ queryKey: ['cliente-docs', clienteId] })
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const remover = async (filename: string) => {
    if (!confirm(`Remover ${filename}?`)) return
    await clientesApi.removerDocumento(clienteId, filename)
    qc.invalidateQueries({ queryKey: ['cliente-docs', clienteId] })
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  return (
    <div className={styles.root}>
      {/* Documentos */}
      <div className={styles.docsSection}>
        <div className={styles.docsHeader}>
          <span className={styles.docsTitle}>Documentos do Cliente</span>
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
            Nenhum PDF adicionado. Suba documentos para a IA usar como contexto.
          </p>
        ) : (
          <ul className={styles.docsList}>
            {docs.map((d) => (
              <li key={d.filename} className={styles.docItem}>
                {d.drive_link ? (
                  <a className={styles.docNome} href={d.drive_link} target="_blank" rel="noreferrer">
                    {d.filename}
                  </a>
                ) : (
                  <span className={styles.docNome}>{d.filename}</span>
                )}
                <span className={styles.docTamanho}>{formatSize(d.size)}</span>
                {d.source === 'drive' && <span className={styles.docTamanho}>Drive</span>}
                {d.source !== 'drive' && (
                  <button className={styles.btnRemoverDoc} onClick={() => remover(d.filename)}>×</button>
                )}
              </li>
            ))}
          </ul>
        )}

        {/* Conversas salvas */}
        {conversas.length > 0 && (
          <div className={styles.conversasSection}>
            <div className={styles.conversasHeader}>
              <span className={styles.docsTitle}>Conversas salvas</span>
              <button className={styles.btnNovaConversa} onClick={novaConversa}>+ Nova</button>
            </div>
            <ul className={styles.conversasList}>
              {/* Mostra conversas raiz (sem parent) e seus filhos (resumos) abaixo */}
              {conversas
                .filter((c) => !c.parent_conversa_id)
                .map((c) => {
                  const filhos = conversas.filter((f) => f.parent_conversa_id === c.id)
                  return (
                    <li key={c.id} className={styles.conversaGrupo}>
                      {/* Conversa principal */}
                      <div
                        className={`${styles.conversaItem} ${c.id === conversaAtualId ? styles.conversaAtiva : ''}`}
                        onClick={() => { if (renomeandoId !== c.id) carregarConversa(c) }}
                      >
                        {renomeandoId === c.id ? (
                          <input
                            className={styles.renomeInput}
                            value={novoTitulo}
                            autoFocus
                            onChange={(e) => setNovoTitulo(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') salvarRenome(c.id)
                              if (e.key === 'Escape') setRenomeandoId(null)
                            }}
                            onBlur={() => salvarRenome(c.id)}
                            onClick={(e) => e.stopPropagation()}
                          />
                        ) : (
                          <>
                            <div className={styles.conversaInfo}>
                              <span className={styles.conversaTitulo}>{c.titulo || '(sem título)'}</span>
                            </div>
                            <div className={styles.conversaAcoes} onClick={(e) => e.stopPropagation()}>
                              <button
                                className={styles.btnRenomear}
                                title="Renomear"
                                onClick={() => { setRenomeandoId(c.id); setNovoTitulo(c.titulo || '') }}
                              >✎</button>
                              <button
                                className={styles.btnRemoverDoc}
                                onClick={() => { if (confirm('Apagar conversa?')) deletarConversa.mutate(c.id) }}
                              >×</button>
                            </div>
                          </>
                        )}
                      </div>

                      {/* Resumos/filhos desta conversa */}
                      {filhos.map((f) => (
                        <div
                          key={f.id}
                          className={`${styles.conversaFilho} ${f.id === conversaAtualId ? styles.conversaAtiva : ''}`}
                          onClick={() => carregarConversa(f)}
                        >
                          <div className={styles.conversaInfo}>
                            <span className={styles.conversaResumoTitulo}>
                              ⚡ {f.titulo?.replace('[Resumo] ', '') || 'Resumo'}
                            </span>
                            {f.resumo && (
                              <span className={styles.conversaResumo}>
                                {f.resumo.slice(0, 70)}{f.resumo.length > 70 ? '...' : ''}
                              </span>
                            )}
                          </div>
                          <button
                            className={styles.btnRemoverDoc}
                            onClick={(e) => { e.stopPropagation(); if (confirm('Apagar resumo?')) deletarConversa.mutate(f.id) }}
                          >×</button>
                        </div>
                      ))}
                    </li>
                  )
                })}
            </ul>
          </div>
        )}
      </div>

      {/* Chat */}
      <div className={styles.chatSection}>
        <div className={styles.chatHeader}>
          <span className={styles.chatTitle}>
            Chat IA
            {docs.length > 0 && (
              <span className={styles.chatContexto}>{docs.length} doc(s)</span>
            )}
          </span>
          <div className={styles.modeloRow}>
            {MODELOS.map((m) => (
              <button
                key={m.key}
                className={`${styles.btnModelo} ${modelo === m.key ? styles.btnModeloAtivo : ''}`}
                onClick={() => setModelo(m.key)}
                disabled={loading}
              >
                {m.label}
              </button>
            ))}
            {conversaAtualId && (
              <button
                className={styles.btnCompactar}
                onClick={compactar}
                disabled={compactando || loading}
                title="Pede à IA um resumo executivo e salva"
              >
                {compactando ? '...' : '⚡ Compactar'}
              </button>
            )}
          </div>
        </div>

        <div className={styles.mensagens}>
          {messages.length === 0 && (
            <div className={styles.mensagemVazia}>
              {conversas.length > 0
                ? 'Selecione uma conversa à esquerda ou escreva para iniciar uma nova.'
                : 'Faça uma pergunta sobre o cliente ou seus documentos...'}
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`${styles.mensagem} ${m.role === 'user' ? styles.mensagemUser : styles.mensagemModel}`}
            >
              <div className={styles.mensagemBubble}>{m.content}</div>
            </div>
          ))}
          {loading && (
            <div className={`${styles.mensagem} ${styles.mensagemModel}`}>
              <div className={`${styles.mensagemBubble} ${styles.loading}`}>
                ⏳ {MODELOS.find(m => m.key === modelo)?.label} está processando...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className={styles.inputRow}>
          <textarea
            className={styles.chatInput}
            placeholder="Pergunta sobre o cliente..."
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
          <button
            className={styles.btnEnviar}
            onClick={enviar}
            disabled={!input.trim() || loading}
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  )
}
