/**
 * Folder Organizer
 * 1. Seleciona cliente e subpasta (Dropbox)
 * 2. Faz upload da peça principal + anexos
 * 3. IA analisa e sugere renomeações com ordenação
 * 4. Usuário revisa/edita
 * 5. "Aplicar" → salva na pasta Dropbox selecionada + baixa ZIP
 */

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../api/client'
import { clientesApi } from '../api/clientes'
import styles from './Page.module.css'
import org from './OrganizadorPage.module.css'

interface Sugestao {
  original: string
  sugerido: string
  motivo: string
  ordem: number
  pagina?: number | null
  contexto?: string | null
  cenario?: string | null
}

interface AnaliseResult {
  sessao_id: string
  sugestoes: Sugestao[]
  faltando: string[]
  observacoes: string
  cenario_detectado?: string | null
}

function cenarioLabel(c: string): string {
  return ({
    A: 'Cenário A — placeholders (doc. XX) sem numeração',
    B: 'Cenário B — numeração já definida (doc. 1, doc. 2...)',
    C: 'Cenário C — placeholders + Rol de Documentos',
    D: 'Cenário D — sem marcadores explícitos',
  } as Record<string, string>)[c] ?? `Cenário ${c}`
}

interface SubpastaInfo {
  nome: string
  caminho_host: string
  num_arquivos: number
}

interface PastasClienteResult {
  cliente_nome: string
  pasta_raiz: string
  disponivel: boolean
  subpastas: SubpastaInfo[]
}

export default function OrganizadorPage() {
  const pecaRef = useRef<HTMLInputElement>(null)
  const anexosRef = useRef<HTMLInputElement>(null)

  const [clienteId, setClienteId] = useState('')
  const [subfolder, setSubfolder] = useState('')
  const [analisando, setAnalisando] = useState(false)
  const [analise, setAnalise] = useState<AnaliseResult | null>(null)
  const [sugestoes, setSugestoes] = useState<Sugestao[]>([])
  const [erro, setErro] = useState<string | null>(null)
  const [baixando, setBaixando] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [salvouNaPasta, setSalvouNaPasta] = useState(false)
  const [copiado, setCopiado] = useState(false)

  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })

  const { data: pastasInfo } = useQuery<PastasClienteResult>({
    queryKey: ['pastas-cliente', clienteId],
    queryFn: () => api.get(`/organizador/pastas-cliente/${clienteId}`).then((r) => r.data),
    enabled: !!clienteId,
  })

  // Reset subfolder when client changes
  useEffect(() => { setSubfolder('') }, [clienteId])

  const analisar = async () => {
    const peca = pecaRef.current?.files?.[0]
    if (!peca) { setErro('Selecione a peça processual principal.'); return }
    setErro(null)
    setAnalisando(true)
    setAnalise(null)
    setSalvouNaPasta(false)

    const form = new FormData()
    form.append('peca', peca)
    const anexos = Array.from(anexosRef.current?.files ?? [])
    for (const a of anexos) form.append('anexos', a)

    try {
      const { data } = await api.post<AnaliseResult>('/organizador/analisar', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setAnalise(data)
      setSugestoes(data.sugestoes.slice().sort((a, b) => a.ordem - b.ordem))
    } catch (e: any) {
      setErro(e?.response?.data?.detail || 'Erro ao analisar arquivos.')
    } finally {
      setAnalisando(false)
    }
  }

  const resetar = () => {
    setAnalise(null)
    setSugestoes([])
    setErro(null)
    setSalvouNaPasta(false)
    if (pecaRef.current) pecaRef.current.value = ''
    if (anexosRef.current) anexosRef.current.value = ''
  }

  const aplicar = async (salvarNaPasta: boolean) => {
    if (!analise) return
    if (salvarNaPasta) setSalvando(true)
    else setBaixando(true)

    const renomeacoes = sugestoes.map((s) => ({ original: s.original, novo: s.sugerido }))

    try {
      // Salva na pasta Dropbox se selecionado
      if (salvarNaPasta && clienteId && subfolder) {
        await api.post('/organizador/salvar-na-pasta', {
          sessao_id: analise.sessao_id,
          cliente_id: clienteId,
          subfolder,
          renomeacoes,
        })
        setSalvouNaPasta(true)
      }

      // Baixa ZIP sempre
      const resp = await api.post(
        '/organizador/aplicar',
        { sessao_id: analise.sessao_id, renomeacoes },
        { responseType: 'blob' }
      )
      const url = URL.createObjectURL(new Blob([resp.data], { type: 'application/zip' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `protocolo_${analise.sessao_id.slice(0, 8)}.zip`
      a.click()
      URL.revokeObjectURL(url)

      await api.delete(`/organizador/sessao/${analise.sessao_id}`).catch(() => {})
      resetar()
    } catch {
      setErro('Erro ao aplicar. Tente novamente.')
    } finally {
      setBaixando(false)
      setSalvando(false)
    }
  }

  const editarNome = (idx: number, novoNome: string) => {
    setSugestoes((prev) => prev.map((s, i) => i === idx ? { ...s, sugerido: novoNome } : s))
  }

  const moverItem = (idx: number, dir: -1 | 1) => {
    const next = idx + dir
    if (next < 0 || next >= sugestoes.length) return
    setSugestoes((prev) => {
      const arr = [...prev]
      ;[arr[idx], arr[next]] = [arr[next], arr[idx]]
      return arr.map((s, i) => ({ ...s, ordem: i + 1 }))
    })
  }

  const copiarCaminho = (path: string) => {
    navigator.clipboard.writeText(path).then(() => {
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    })
  }

  const pastaRaiz = pastasInfo?.pasta_raiz ?? ''
  const subpastas = pastasInfo?.subpastas ?? []

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Folder Organizer</h1>
        {analise && (
          <button className={styles.btnTable} onClick={resetar}>↺ Nova análise</button>
        )}
      </div>

      {!analise && (
        <div className={org.uploadCard}>
          {/* Seletor de cliente + pasta */}
          <div className={org.pastaSelector}>
            <div className={org.pastaSelectorRow}>
              <div className={org.pastaSelectorField}>
                <label className={org.uploadLabel}>Cliente</label>
                <select
                  className={styles.input}
                  value={clienteId}
                  onChange={(e) => setClienteId(e.target.value)}
                >
                  <option value="">Selecione o cliente...</option>
                  {clientes.map((c) => (
                    <option key={c.id} value={c.id}>{c.nome}</option>
                  ))}
                </select>
              </div>

              {clienteId && (
                <div className={org.pastaSelectorField}>
                  <label className={org.uploadLabel}>Salvar em</label>
                  <select
                    className={styles.input}
                    value={subfolder}
                    onChange={(e) => setSubfolder(e.target.value)}
                  >
                    <option value="">Pasta raiz do cliente</option>
                    {subpastas.map((s) => (
                      <option key={s.nome} value={s.nome}>
                        {s.nome} ({s.num_arquivos} arq.)
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {pastaRaiz && (
              <div className={org.pastaPath}>
                <span className={org.pastaPathLabel}>Pasta:</span>
                <code className={org.pastaPathCode}>
                  {subfolder ? `${pastaRaiz}/${subfolder}` : pastaRaiz}
                </code>
                <button
                  className={org.btnCopiarPath}
                  onClick={() => copiarCaminho(subfolder ? `${pastaRaiz}/${subfolder}` : pastaRaiz)}
                  title="Copiar caminho — cole no Finder com Cmd+Shift+G"
                >
                  {copiado ? '✓ Copiado' : '⎘ Copiar'}
                </button>
                {!pastasInfo?.disponivel && (
                  <span className={org.pastaIndisponivel}>⚠ Dropbox não montado</span>
                )}
              </div>
            )}
          </div>

          <div className={org.uploadSection}>
            <label className={org.uploadLabel}>
              Peça processual principal <span className={org.req}>*</span>
            </label>
            <input ref={pecaRef} type="file" accept=".pdf" className={org.fileInput} />
            <p className={org.uploadHint}>PDF da petição/contestação/recurso principal</p>
          </div>

          <div className={org.uploadSection}>
            <label className={org.uploadLabel}>
              Anexos / documentos complementares
            </label>
            <input ref={anexosRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.doc" multiple className={org.fileInput} />
            <p className={org.uploadHint}>Procurações, documentos, comprovantes... (múltiplos)</p>
          </div>

          {erro && <div className={org.erro}>{erro}</div>}

          <button
            className={styles.btnPrimary}
            onClick={analisar}
            disabled={analisando}
          >
            {analisando ? '⏳ Analisando com IA...' : 'Analisar e Organizar'}
          </button>

          <div className={org.comoFunciona}>
            <strong>Como funciona:</strong> a IA lê a peça principal, identifica os documentos
            mencionados como anexos e sugere nomes padronizados com numeração de protocolo.
            Você revisa, ajusta a ordem e salva na pasta do cliente ou baixa o ZIP.
          </div>
        </div>
      )}

      {analise && (
        <div className={org.resultadoCard}>
          {analise.cenario_detectado && (
            <div className={org.cenarioBadgeWrap}>
              <span className={org.cenarioBadge}>{cenarioLabel(analise.cenario_detectado)}</span>
            </div>
          )}
          {analise.observacoes && (
            <div className={org.observacoes}>
              <strong>IA:</strong> {analise.observacoes}
            </div>
          )}

          {analise.faltando.length > 0 && (
            <div className={org.faltando}>
              <div className={org.faltandoTitulo}>Documentos mencionados na peça que estão faltando:</div>
              <ul className={org.faltandoLista}>
                {analise.faltando.map((f, i) => <li key={i}>{f}</li>)}
              </ul>
            </div>
          )}

          <div className={org.tabelaTitulo}>
            Sugestões de renomeação — edite os nomes e reordene se necessário
          </div>
          <div className={org.tabela}>
            <div className={org.tabelaHeader}>
              <span className={org.colOrdem}>#</span>
              <span className={org.colOriginal}>Nome original</span>
              <span className={org.colSugerido}>Nome sugerido (editável)</span>
              <span className={org.colMotivo}>Motivo</span>
              <span className={org.colPag}>Pág.</span>
              <span className={org.colContexto}>Contexto</span>
              <span className={org.colAcoes}></span>
            </div>
            {sugestoes.map((s, idx) => (
              <div key={s.original} className={org.tabelaRow}>
                <span className={org.colOrdem}>{idx + 1}</span>
                <span className={org.colOriginal} title={s.original}>{s.original}</span>
                <input
                  className={org.inputNome}
                  value={s.sugerido}
                  onChange={(e) => editarNome(idx, e.target.value)}
                />
                <span className={org.colMotivo} title={s.motivo}>{s.motivo}</span>
                <span className={org.colPag}>{s.pagina ?? '—'}</span>
                <span className={org.colContexto} title={s.contexto ?? ''}>{s.contexto ?? '—'}</span>
                <div className={org.colAcoes}>
                  <button className={org.btnMover} onClick={() => moverItem(idx, -1)} disabled={idx === 0}>↑</button>
                  <button className={org.btnMover} onClick={() => moverItem(idx, 1)} disabled={idx === sugestoes.length - 1}>↓</button>
                </div>
              </div>
            ))}
          </div>

          {erro && <div className={org.erro}>{erro}</div>}
          {salvouNaPasta && (
            <div className={org.sucessoMsg}>
              ✓ Arquivos salvos em {subfolder ? `${pastaRaiz}/${subfolder}` : pastaRaiz}
            </div>
          )}

          <div className={org.acoes}>
            {clienteId && subfolder && pastasInfo?.disponivel && (
              <button
                className={styles.btnPrimary}
                onClick={() => aplicar(true)}
                disabled={salvando || baixando}
                title={`Salvar em ${pastaRaiz}/${subfolder} e baixar ZIP`}
              >
                {salvando ? '⏳ Salvando...' : `Salvar na pasta + ZIP`}
              </button>
            )}
            <button
              className={styles.btnTable}
              onClick={() => aplicar(false)}
              disabled={salvando || baixando}
            >
              {baixando ? '⏳ Gerando ZIP...' : 'Baixar ZIP'}
            </button>
            <button className={styles.btnTable} onClick={resetar}>Cancelar</button>
          </div>
        </div>
      )}
    </div>
  )
}
