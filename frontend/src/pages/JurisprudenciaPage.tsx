import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../api/client'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import ComboBox from '../components/ComboBox'
import styles from './Page.module.css'
import cs from './JurisprudenciaPage.module.css'

type Modelo = 'gemini' | 'claude' | 'gpt'

const MODELOS: { key: Modelo; label: string }[] = [
  { key: 'gemini', label: 'Gemini' },
  { key: 'claude', label: 'Claude' },
  { key: 'gpt', label: 'GPT-4o' },
]

export default function JurisprudenciaPage() {
  const [texto, setTexto] = useState('')
  const [modelo, setModelo] = useState<Modelo>('gemini')
  const [analise, setAnalise] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [titulo, setTitulo] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  // Para salvar na pasta
  const [clienteId, setClienteId] = useState('')
  const [processoId, setProcessoId] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [salvoMsg, setSalvoMsg] = useState<string | null>(null)

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })
  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })

  const processosFiltrados = clienteId
    ? processos.filter((p) => p.cliente_id === clienteId)
    : processos

  const analisar = async () => {
    if (!texto.trim()) return
    setLoading(true)
    setErro(null)
    setAnalise(null)
    setSalvoMsg(null)
    try {
      const r = await api.post<{ analise: string }>('/jurisprudencia/analisar', {
        texto,
        modelo,
      })
      setAnalise(r.data.analise)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detail || 'Erro ao analisar. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setErro(null)
    try {
      const form = new FormData()
      form.append('arquivo', file)
      const r = await api.post<{ texto: string }>('/jurisprudencia/extrair-pdf', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setTexto(r.data.texto)
      if (!titulo) setTitulo(file.name.replace(/\.pdf$/i, ''))
    } catch {
      setErro('Erro ao extrair texto do PDF.')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const salvarNaPasta = async () => {
    if (!clienteId || !analise) return
    setSalvando(true)
    setSalvoMsg(null)
    try {
      await api.post('/jurisprudencia/salvar', {
        cliente_id: clienteId,
        processo_id: processoId || null,
        titulo: titulo || null,
        analise,
        texto_original: texto,
      })
      setSalvoMsg('Salvo na pasta do cliente com sucesso!')
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setSalvoMsg(`Erro: ${detail || 'Falha ao salvar'}`)
    } finally {
      setSalvando(false)
    }
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Análise de Jurisprudência</h1>
      </div>

      {/* Seleção de cliente/processo para salvar */}
      <div className={cs.clienteBar}>
        <div className={cs.clienteBarField}>
          <label className={cs.clienteLabel}>Cliente</label>
          <ComboBox
            options={clientes.map((c) => ({ value: c.id, label: c.nome }))}
            value={clienteId}
            onChange={(v) => { setClienteId(v); setProcessoId('') }}
            placeholder="Selecionar cliente (para salvar)..."
          />
        </div>
        {clienteId && processosFiltrados.length > 0 && (
          <div className={cs.clienteBarField}>
            <label className={cs.clienteLabel}>Processo</label>
            <ComboBox
              options={processosFiltrados.map((p) => ({ value: p.id, label: p.numero_cnj }))}
              value={processoId}
              onChange={setProcessoId}
              placeholder="Processo (opcional)..."
            />
          </div>
        )}
        <div className={cs.clienteBarField} style={{ flex: 2 }}>
          <label className={cs.clienteLabel}>Título / referência</label>
          <input
            className={styles.input}
            placeholder="ex: STJ — HC 123456 — prisão cautelar"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
          />
        </div>
      </div>

      <div className={cs.layout}>
        {/* Painel de entrada */}
        <div className={cs.inputPanel}>
          <div className={cs.panelHeader}>
            <span className={cs.panelTitle}>Texto do Julgado</span>
            <div className={cs.headerActions}>
              <label className={cs.btnUpload}>
                {uploading ? 'Extraindo...' : '↑ PDF'}
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf"
                  style={{ display: 'none' }}
                  onChange={handleUpload}
                  disabled={uploading}
                />
              </label>
              <button className={cs.btnLimpar} onClick={() => { setTexto(''); setAnalise(null); setErro(null); setSalvoMsg(null) }}>
                Limpar
              </button>
            </div>
          </div>
          <textarea
            className={cs.textarea}
            placeholder="Cole aqui o texto de uma decisão, acórdão ou ementa para análise..."
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={18}
          />
          <div className={cs.inputFooter}>
            <div className={cs.modeloRow}>
              {MODELOS.map((m) => (
                <button
                  key={m.key}
                  className={`${cs.btnModelo} ${modelo === m.key ? cs.btnModeloAtivo : ''}`}
                  onClick={() => setModelo(m.key)}
                  disabled={loading}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <button
              className={cs.btnAnalisar}
              onClick={analisar}
              disabled={loading || !texto.trim()}
            >
              {loading ? '⏳ Analisando...' : '⚖ Analisar'}
            </button>
          </div>
        </div>

        {/* Painel de resultado */}
        <div className={cs.resultPanel}>
          <div className={cs.panelHeader}>
            <span className={cs.panelTitle}>Análise</span>
            {analise && clienteId && (
              <button
                className={cs.btnSalvar}
                onClick={salvarNaPasta}
                disabled={salvando}
              >
                {salvando ? 'Salvando...' : '💾 Salvar na pasta'}
              </button>
            )}
          </div>
          {salvoMsg && (
            <div className={salvoMsg.startsWith('Erro') ? cs.erro : cs.salvoOk}>
              {salvoMsg}
            </div>
          )}
          {erro && (
            <div className={cs.erro}>{erro}</div>
          )}
          {!analise && !erro && !loading && (
            <div className={cs.vazio}>
              A análise aparecerá aqui após o envio do texto.
            </div>
          )}
          {loading && (
            <div className={cs.vazio}>⏳ Processando com {MODELOS.find(m => m.key === modelo)?.label}...</div>
          )}
          {analise && (
            <div className={cs.analiseContent}>
              {analise.split('\n').map((linha, i) => {
                if (linha.startsWith('**') && linha.endsWith('**')) {
                  return <h3 key={i} className={cs.secao}>{linha.replace(/\*\*/g, '')}</h3>
                }
                if (linha.startsWith('**')) {
                  return <p key={i} className={cs.boldLine}>{linha.replace(/\*\*/g, '')}</p>
                }
                if (linha.startsWith('- ') || linha.startsWith('• ')) {
                  return <li key={i} className={cs.item}>{linha.slice(2)}</li>
                }
                if (!linha.trim()) return <br key={i} />
                return <p key={i} className={cs.linha}>{linha}</p>
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
