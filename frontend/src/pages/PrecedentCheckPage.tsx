import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronDown,
  ExternalLink,
  FileUp,
  History,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react'
import { precedentCheckApi, CitacaoVerificada, AnaliseResumida } from '../api/precedentcheck'
import styles from './Page.module.css'
import cs from './PrecedentCheckPage.module.css'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadgeClass(status: CitacaoVerificada['status_geral']) {
  if (status === 'verificado') return cs.badgeOk
  if (status === 'divergencia') return cs.badgeDiv
  if (status === 'nao_encontrado') return cs.badgeNao
  return cs.badgePend
}

function statusChipClass(status: CitacaoVerificada['status_geral']) {
  if (status === 'verificado') return cs.chipOk
  if (status === 'divergencia') return cs.chipDiv
  if (status === 'nao_encontrado') return cs.chipNao
  return cs.chipPend
}

function resultadoClass(r?: string) {
  if (r === 'ok') return cs.resOk
  if (r === 'divergencia') return cs.resDiv
  if (r === 'nao_encontrado') return cs.resNao
  return cs.resInc
}

function resultadoIcon(r?: string) {
  if (r === 'ok') return '✓'
  if (r === 'divergencia') return '⚠'
  if (r === 'nao_encontrado') return '✗'
  return '?'
}

const DIMENSOES: { key: keyof CitacaoVerificada; label: string }[] = [
  { key: 'numero_existe', label: 'Número existe' },
  { key: 'relator_correto', label: 'Relator correto' },
  { key: 'data_procede', label: 'Data procede' },
  { key: 'trecho_literal', label: 'Trecho literal' },
  { key: 'voto_vencedor', label: 'Voto vencedor' },
  { key: 'contexto_compativel', label: 'Contexto compatível' },
  { key: 'ratio_fit', label: 'Ratio decidendi fit' },
]

function formatData(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

// ---------------------------------------------------------------------------
// Componente de card de citação
// ---------------------------------------------------------------------------

function CitacaoCard({
  citacao,
  idx,
  verificando,
}: {
  citacao: CitacaoVerificada
  idx: number
  verificando: boolean
}) {
  const [aberto, setAberto] = useState(false)
  const [decisoesMesmoAberto, setDecisoesMesmoAberto] = useState(false)
  const [decisoesContrarioAberto, setDecisoesContrarioAberto] = useState(false)

  const referencia = `${citacao.tribunal} — ${citacao.numero}`

  return (
    <div className={cs.card}>
      <div className={cs.cardHeader} onClick={() => setAberto((v) => !v)}>
        {verificando ? (
          <div className={cs.loadingDot} />
        ) : (
          <div className={`${cs.cardBadge} ${statusBadgeClass(citacao.status_geral)}`} />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className={cs.cardReferencia}>{referencia}</div>
          {citacao.trecho_citado && (
            <div className={cs.cardTrecho}>"{citacao.trecho_citado}"</div>
          )}
        </div>
        {!verificando && (
          <span className={`${cs.chip} ${statusChipClass(citacao.status_geral)}`}>
            {citacao.status_geral === 'verificado' && 'Verificado'}
            {citacao.status_geral === 'divergencia' && 'Divergência'}
            {citacao.status_geral === 'nao_encontrado' && 'Não encontrado'}
            {citacao.status_geral === 'parcial' && 'Parcial'}
            {citacao.status_geral === 'pendente' && 'Pendente'}
          </span>
        )}
        <ChevronDown
          size={16}
          className={`${cs.cardChevron} ${aberto ? cs.cardChevronOpen : ''}`}
        />
      </div>

      {aberto && (
        <div className={cs.cardBody}>
          {/* 7 dimensões */}
          {citacao.verificado && (
            <div className={cs.dimensoesGrid}>
              {DIMENSOES.map(({ key, label }) => {
                const dim = citacao[key] as { resultado: string; detalhe: string } | undefined
                if (!dim) return null
                return (
                  <div key={key} className={cs.dimensao}>
                    <div className={cs.dimensaoLabel}>{label}</div>
                    <div className={`${cs.dimensaoResultado} ${resultadoClass(dim.resultado)}`}>
                      <span>{resultadoIcon(dim.resultado)}</span>
                      <span style={{ textTransform: 'capitalize' }}>{dim.resultado?.replace('_', ' ')}</span>
                    </div>
                    {dim.detalhe && <div className={cs.dimensaoDetalhe}>{dim.detalhe}</div>}
                  </div>
                )
              })}
            </div>
          )}

          {/* Ementa real */}
          {citacao.ementa_real && (
            <div>
              <div className={cs.ementaLabel}>Ementa real</div>
              <div className={cs.ementa}>{citacao.ementa_real}</div>
            </div>
          )}

          {/* Link inteiro teor */}
          {citacao.link_inteiro_teor && (
            <a
              className={cs.linkTeor}
              href={citacao.link_inteiro_teor}
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink size={13} />
              Inteiro teor
            </a>
          )}

          {/* Collapsível: decisões no mesmo sentido */}
          {citacao.decisoes_mesmo_sentido && citacao.decisoes_mesmo_sentido.length > 0 && (
            <>
              <button
                className={cs.decisoesToggle}
                onClick={() => setDecisoesMesmoAberto((v) => !v)}
              >
                <span>Decisões no mesmo sentido ({citacao.decisoes_mesmo_sentido.length})</span>
                <ChevronDown size={14} style={{ transform: decisoesMesmoAberto ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
              </button>
              {decisoesMesmoAberto && (
                <div className={cs.decisoesLista}>
                  {citacao.decisoes_mesmo_sentido.map((d, i) => (
                    <div key={i} className={cs.decisaoItem}>
                      <div className={cs.decisaoItemRef}>
                        {d.link ? (
                          <a href={d.link} target="_blank" rel="noopener noreferrer" className={cs.linkTeor}>
                            {d.referencia} <ExternalLink size={11} />
                          </a>
                        ) : d.referencia}
                      </div>
                      <div className={cs.decisaoItemEmenta}>{d.ementa}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Collapsível: decisões em sentido contrário */}
          {citacao.decisoes_sentido_contrario && citacao.decisoes_sentido_contrario.length > 0 && (
            <>
              <button
                className={cs.decisoesToggle}
                onClick={() => setDecisoesContrarioAberto((v) => !v)}
              >
                <span>Decisões em sentido contrário ({citacao.decisoes_sentido_contrario.length})</span>
                <ChevronDown size={14} style={{ transform: decisoesContrarioAberto ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
              </button>
              {decisoesContrarioAberto && (
                <div className={cs.decisoesLista}>
                  {citacao.decisoes_sentido_contrario.map((d, i) => (
                    <div key={i} className={cs.decisaoItem}>
                      <div className={cs.decisaoItemRef}>
                        {d.link ? (
                          <a href={d.link} target="_blank" rel="noopener noreferrer" className={cs.linkTeor}>
                            {d.referencia} <ExternalLink size={11} />
                          </a>
                        ) : d.referencia}
                      </div>
                      <div className={cs.decisaoItemEmenta}>{d.ementa}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Contexto de uso na peça */}
          {citacao.contexto_na_peca && (
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border)', paddingTop: '0.5rem' }}>
              <strong>Uso na peça:</strong> {citacao.contexto_na_peca}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Componente de histórico
// ---------------------------------------------------------------------------

function HistoricoPanel({
  onCarregar,
}: {
  onCarregar: (id: string) => void
}) {
  const qc = useQueryClient()
  const { data: historico = [], isLoading } = useQuery({
    queryKey: ['precedentcheck-historico'],
    queryFn: () => precedentCheckApi.listarHistorico(),
  })

  const deletar = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await precedentCheckApi.deletar(id)
    qc.invalidateQueries({ queryKey: ['precedentcheck-historico'] })
  }

  if (isLoading) return null
  if (historico.length === 0) return null

  return (
    <div className={cs.historico}>
      <div className={cs.historicoHeader}>
        <History size={14} />
        Histórico
      </div>
      {historico.map((a: AnaliseResumida) => (
        <div key={a.id} className={cs.historicoRow} onClick={() => onCarregar(a.id)}>
          <div className={cs.historicoTitulo}>{a.titulo || 'Sem título'}</div>
          <span className={`${cs.chip} ${cs.chipOk}`}>{a.total_ok}✓</span>
          {a.total_divergencia > 0 && (
            <span className={`${cs.chip} ${cs.chipDiv}`}>{a.total_divergencia}⚠</span>
          )}
          {a.total_nao_encontrado > 0 && (
            <span className={`${cs.chip} ${cs.chipNao}`}>{a.total_nao_encontrado}✗</span>
          )}
          <span className={cs.historicoData}>{formatData(a.created_at)}</span>
          <button
            className={styles.btnDanger}
            style={{ padding: '0.2rem 0.4rem', fontSize: '0.7rem' }}
            onClick={(e) => deletar(a.id, e)}
          >
            <Trash2 size={11} />
          </button>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------

export default function PrecedentCheckPage() {
  const fileRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const [texto, setTexto] = useState('')
  const [titulo, setTitulo] = useState('')
  const [uploading, setUploading] = useState(false)
  const [analisando, setAnalisando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  // Estado da análise em andamento
  const [analiseId, setAnaliseId] = useState<string | null>(null)
  const [citacoes, setCitacoes] = useState<CitacaoVerificada[]>([])
  const [verificandoIdx, setVerificandoIdx] = useState<number | null>(null)
  const [totalVerificadas, setTotalVerificadas] = useState(0)

  const uploadPdf = async (file: File) => {
    setUploading(true)
    setErro(null)
    try {
      const { texto: t } = await precedentCheckApi.extrairPdf(file)
      setTexto(t)
      if (!titulo) setTitulo(file.name.replace('.pdf', ''))
    } catch {
      setErro('Erro ao extrair o PDF.')
    } finally {
      setUploading(false)
    }
  }

  const iniciarAnalise = async () => {
    if (!texto.trim()) return
    setAnalisando(true)
    setErro(null)
    setCitacoes([])
    setAnaliseId(null)
    setTotalVerificadas(0)

    try {
      const res = await precedentCheckApi.analisar({ texto, titulo: titulo || undefined })
      setAnaliseId(res.analise_id)
      setCitacoes(res.citacoes)

      // Verifica citação a citação
      for (let i = 0; i < res.citacoes.length; i++) {
        setVerificandoIdx(i)
        try {
          const verificada = await precedentCheckApi.verificarCitacao(res.analise_id, i)
          setCitacoes((prev) => {
            const next = [...prev]
            next[i] = verificada
            return next
          })
        } catch {
          // Continua para a próxima mesmo se falhar
        }
        setTotalVerificadas(i + 1)
      }
      setVerificandoIdx(null)
      qc.invalidateQueries({ queryKey: ['precedentcheck-historico'] })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Erro ao analisar'
      setErro(msg)
    } finally {
      setAnalisando(false)
      setVerificandoIdx(null)
    }
  }

  const carregarDoHistorico = async (id: string) => {
    try {
      const analise = await precedentCheckApi.obterAnalise(id)
      setTexto(analise.texto_peca)
      setTitulo(analise.titulo || '')
      setCitacoes(analise.citacoes)
      setAnaliseId(analise.id)
      setTotalVerificadas(analise.citacoes.filter((c) => c.verificado).length)
    } catch {
      setErro('Erro ao carregar análise.')
    }
  }

  const limpar = () => {
    setTexto('')
    setTitulo('')
    setCitacoes([])
    setAnaliseId(null)
    setErro(null)
    setTotalVerificadas(0)
  }

  const totalOk = citacoes.filter((c) => c.status_geral === 'verificado').length
  const totalDiv = citacoes.filter((c) => c.status_geral === 'divergencia').length
  const totalNao = citacoes.filter((c) => c.status_geral === 'nao_encontrado').length

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          <ShieldCheck size={20} style={{ marginRight: 8, verticalAlign: 'middle' }} />
          PrecedentCheck
        </h1>
        {(citacoes.length > 0 || texto) && (
          <button className={styles.btnSmall} onClick={limpar}>
            <X size={13} /> Nova análise
          </button>
        )}
      </div>

      <div className={cs.layout}>
        {/* Painel esquerdo — entrada */}
        <div className={cs.painel}>
          <div className={cs.painelTitle}>Peça ou decisão</div>

          <input
            className={cs.tituloInput}
            placeholder="Título (opcional)"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
          />

          <textarea
            className={cs.textarea}
            placeholder="Cole aqui o texto da peça, decisão, sentença ou acórdão..."
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />

          <div className={cs.uploadRow}>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              style={{ display: 'none' }}
              onChange={(e) => e.target.files?.[0] && uploadPdf(e.target.files[0])}
            />
            <button
              className={styles.btnSmall}
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
            >
              <FileUp size={13} />
              {uploading ? 'Carregando PDF...' : 'Carregar PDF'}
            </button>
            {texto && (
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                {texto.length.toLocaleString('pt-BR')} caracteres
              </span>
            )}
          </div>

          <button
            className={styles.btnPrimary}
            onClick={iniciarAnalise}
            disabled={analisando || !texto.trim()}
          >
            {analisando
              ? `Verificando... (${totalVerificadas}/${citacoes.length || '?'})`
              : 'Verificar precedentes'}
          </button>

          {erro && (
            <div style={{ fontSize: '0.8rem', color: 'var(--danger)', padding: '0.5rem', background: '#fee2e2', borderRadius: 6 }}>
              {erro}
            </div>
          )}
        </div>

        {/* Painel direito — resultados */}
        <div className={cs.resultados}>
          {citacoes.length > 0 && (
            <div className={cs.summaryBar}>
              <span className={cs.summaryLabel}>
                {citacoes.length} citaç{citacoes.length === 1 ? 'ão' : 'ões'} encontrada{citacoes.length === 1 ? '' : 's'}
                {analiseId && verificandoIdx !== null && ` — verificando ${totalVerificadas + 1} de ${citacoes.length}...`}
              </span>
              {totalOk > 0 && <span className={`${cs.chip} ${cs.chipOk}`}>{totalOk} ok</span>}
              {totalDiv > 0 && <span className={`${cs.chip} ${cs.chipDiv}`}>{totalDiv} divergência</span>}
              {totalNao > 0 && <span className={`${cs.chip} ${cs.chipNao}`}>{totalNao} não encontrado</span>}
            </div>
          )}

          {citacoes.map((c, i) => (
            <CitacaoCard
              key={i}
              citacao={c}
              idx={i}
              verificando={verificandoIdx === i}
            />
          ))}

          {citacoes.length === 0 && !analisando && (
            <HistoricoPanel onCarregar={carregarDoHistorico} />
          )}
        </div>
      </div>
    </div>
  )
}
