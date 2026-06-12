import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  ArchiveRestore,
  ChevronDown,
  ExternalLink,
  FileUp,
  History,
  Pencil,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react'
import { precedentCheckApi } from '../api/precedentcheck'
import type { CitacaoVerificada, AnaliseResumida } from '../api/precedentcheck'
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

function jusbrasil(referencia: string) {
  return `https://www.jusbrasil.com.br/jurisprudencia/busca?q=${encodeURIComponent(referencia)}`
}

const DIMENSOES: { key: keyof CitacaoVerificada; label: string }[] = [
  { key: 'numero_existe',       label: 'Número existe' },
  { key: 'relator_correto',     label: 'Relator correto' },
  { key: 'data_procede',        label: 'Data procede' },
  { key: 'trecho_literal',      label: 'Trecho literal' },
  { key: 'voto_vencedor',       label: 'Voto vencedor' },
  { key: 'contexto_compativel', label: 'Contexto compatível' },
  { key: 'ratio_fit',           label: 'Ratio decidendi fit' },
]

function formatData(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

// ---------------------------------------------------------------------------
// Card de citação
// ---------------------------------------------------------------------------

// Custo real vem do backend (usage.input_tokens/output_tokens + web_search).
const USD_BRL = 5.7

function formatCusto(usd: number) {
  const brl = usd * USD_BRL
  const prefixo = brl >= 0.01 ? 'R$' : 'R$<'
  const valor = brl >= 0.01 ? brl.toFixed(2) : '0,01'
  return `${prefixo}${valor}`.replace('.', ',')
}

function CitacaoCard({ citacao, verificando }: { citacao: CitacaoVerificada; idx: number; verificando: boolean }) {
  const [aberto, setAberto] = useState(false)
  const [mesmoAberto, setMesmoAberto] = useState(false)
  const [contrarioAberto, setContrarioAberto] = useState(false)

  const referencia = `${citacao.tribunal} — ${citacao.numero}`

  return (
    <div className={cs.card}>
      <div className={cs.cardHeader} onClick={() => setAberto((v) => !v)}>
        {verificando ? (
          <div className={cs.loadingDot} />
        ) : (
          <div className={`${cs.cardBadge} ${statusBadgeClass(citacao.status_geral)}`} />
        )}
        <div className={cs.cardInfo}>
          <div className={cs.cardReferencia}>{referencia}</div>
          {citacao.trecho_citado && (
            <div className={cs.cardTrecho}>"{citacao.trecho_citado}"</div>
          )}
        </div>
        {!verificando && (
          <span className={`${cs.chip} ${statusChipClass(citacao.status_geral)}`}>
            {citacao.status_geral === 'verificado'     && 'Verificado'}
            {citacao.status_geral === 'divergencia'    && 'Divergência'}
            {citacao.status_geral === 'nao_encontrado' && 'Não encontrado'}
            {citacao.status_geral === 'parcial'        && 'Parcial'}
            {citacao.status_geral === 'pendente'       && 'Pendente'}
          </span>
        )}
        {citacao.verificado && typeof citacao.custo_usd === 'number' && citacao.custo_usd > 0 && (
          <span className={cs.custoBadge}>{formatCusto(citacao.custo_usd)}</span>
        )}
        <ChevronDown size={15} className={`${cs.cardChevron} ${aberto ? cs.cardChevronOpen : ''}`} />
      </div>

      {aberto && (verificando || !citacao.verificado) && (
        <div className={cs.verificandoMsg}>
          <div className={cs.loadingDot} />
          Verificando nas fontes…
        </div>
      )}

      {aberto && citacao.verificado && (
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
                      {resultadoIcon(dim.resultado)}{' '}
                      {dim.resultado?.replace(/_/g, ' ')}
                    </div>
                    {dim.detalhe && <div className={cs.dimensaoDetalhe}>{dim.detalhe}</div>}
                  </div>
                )
              })}
            </div>
          )}

          {/* Ementa real */}
          {citacao.ementa_real && (
            <div className={cs.ementaBlock}>
              <div className={cs.ementaLabel}>Ementa real</div>
              <div className={cs.ementaTexto}>{citacao.ementa_real}</div>
            </div>
          )}

          {/* Links */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {citacao.link_inteiro_teor && (
              <a className={cs.linkTeor} href={citacao.link_inteiro_teor} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={12} /> Inteiro teor
              </a>
            )}
            <a className={cs.linkTeor} href={jusbrasil(citacao.numero)} target="_blank" rel="noopener noreferrer">
              <ExternalLink size={12} /> Buscar no Jusbrasil
            </a>
          </div>

          {/* Collapsível: mesmo sentido */}
          {citacao.decisoes_mesmo_sentido && citacao.decisoes_mesmo_sentido.length > 0 && (
            <>
              <button className={cs.decisoesToggle} onClick={() => setMesmoAberto((v) => !v)}>
                <span>Decisões no mesmo sentido ({citacao.decisoes_mesmo_sentido.length})</span>
                <ChevronDown size={13} style={{ transform: mesmoAberto ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
              </button>
              {mesmoAberto && (
                <div className={cs.decisoesLista}>
                  {citacao.decisoes_mesmo_sentido.map((d, i) => (
                    <div key={i} className={cs.decisaoItem}>
                      <div className={cs.decisaoItemRef}>
                        {d.referencia}
                        <a
                          className={cs.decisaoBuscarLink}
                          href={d.link || jusbrasil(d.referencia)}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink size={11} /> {d.link ? 'Abrir' : 'Jusbrasil'}
                        </a>
                      </div>
                      <div className={cs.decisaoItemEmenta}>{d.ementa}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Collapsível: sentido contrário */}
          {citacao.decisoes_sentido_contrario && citacao.decisoes_sentido_contrario.length > 0 && (
            <>
              <button className={cs.decisoesToggle} onClick={() => setContrarioAberto((v) => !v)}>
                <span>Decisões em sentido contrário ({citacao.decisoes_sentido_contrario.length})</span>
                <ChevronDown size={13} style={{ transform: contrarioAberto ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
              </button>
              {contrarioAberto && (
                <div className={cs.decisoesLista}>
                  {citacao.decisoes_sentido_contrario.map((d, i) => (
                    <div key={i} className={cs.decisaoItem}>
                      <div className={cs.decisaoItemRef}>
                        {d.referencia}
                        <a
                          className={cs.decisaoBuscarLink}
                          href={d.link || jusbrasil(d.referencia)}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink size={11} /> {d.link ? 'Abrir' : 'Jusbrasil'}
                        </a>
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
            <div className={cs.contextoUso}>
              <strong>Uso na peça:</strong> {citacao.contexto_na_peca}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Histórico
// ---------------------------------------------------------------------------

function HistoricoPanel({ onCarregar }: { onCarregar: (id: string) => void }) {
  const qc = useQueryClient()
  const [verArquivados, setVerArquivados] = useState(false)
  const [editandoId, setEditandoId] = useState<string | null>(null)
  const [editTitulo, setEditTitulo] = useState('')

  const { data: historico = [], isLoading } = useQuery({
    queryKey: ['precedentcheck-historico', verArquivados],
    queryFn: () => precedentCheckApi.listarHistorico(verArquivados),
  })

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ['precedentcheck-historico'] })
  }

  const arquivar = async (id: string, arquivar: boolean, e: React.MouseEvent) => {
    e.stopPropagation()
    await precedentCheckApi.patch(id, { arquivado: arquivar })
    invalidar()
  }

  const deletar = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await precedentCheckApi.deletar(id)
    invalidar()
  }

  const iniciarEdicao = (a: AnaliseResumida, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditandoId(a.id)
    setEditTitulo(a.titulo || '')
  }

  const salvarEdicao = async (id: string) => {
    await precedentCheckApi.patch(id, { titulo: editTitulo })
    setEditandoId(null)
    invalidar()
  }

  if (isLoading) return null

  return (
    <div className={cs.historico}>
      <div className={cs.historicoHeader}>
        <History size={13} />
        <span>{verArquivados ? 'Arquivados' : 'Histórico'}</span>
        <button
          type="button"
          className={cs.historicoTabBtn}
          onClick={() => setVerArquivados((v) => !v)}
        >
          {verArquivados ? <><ArchiveRestore size={12} /> Ativos</> : <><Archive size={12} /> Arquivados</>}
        </button>
      </div>

      {historico.length === 0 && (
        <div className={cs.historicoVazio}>{verArquivados ? 'Nenhum item arquivado.' : 'Sem histórico.'}</div>
      )}

      {historico.map((a: AnaliseResumida) => (
        <div key={a.id} className={cs.historicoRow} onClick={() => onCarregar(a.id)}>
          {editandoId === a.id ? (
            <input
              className={cs.editTituloInput}
              value={editTitulo}
              autoFocus
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setEditTitulo(e.target.value)}
              onBlur={() => salvarEdicao(a.id)}
              onKeyDown={(e) => { if (e.key === 'Enter') salvarEdicao(a.id); if (e.key === 'Escape') setEditandoId(null) }}
            />
          ) : (
            <div className={cs.historicoTitulo}>{a.titulo || 'Sem título'}</div>
          )}
          {a.total_ok > 0 && <span className={`${cs.chip} ${cs.chipOk}`}>{a.total_ok}</span>}
          {a.total_divergencia > 0 && <span className={`${cs.chip} ${cs.chipDiv}`}>{a.total_divergencia}</span>}
          {a.total_nao_encontrado > 0 && <span className={`${cs.chip} ${cs.chipNao}`}>{a.total_nao_encontrado}</span>}
          <span className={cs.historicoData}>{formatData(a.created_at)}</span>
          <button type="button" className={cs.historicoIconBtn} title="Renomear" onClick={(e) => iniciarEdicao(a, e)}>
            <Pencil size={11} />
          </button>
          <button
            type="button"
            className={cs.historicoIconBtn}
            title={a.arquivado ? 'Restaurar' : 'Arquivar'}
            onClick={(e) => arquivar(a.id, !a.arquivado, e)}
          >
            {a.arquivado ? <ArchiveRestore size={11} /> : <Archive size={11} />}
          </button>
          <button type="button" className={`${cs.historicoIconBtn} ${cs.historicoIconBtnDanger}`} title="Excluir" onClick={(e) => deletar(a.id, e)}>
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

  const [, setAnaliseId] = useState<string | null>(null)
  const [citacoes, setCitacoes] = useState<CitacaoVerificada[]>([])
  const [verificandoSet, setVerificandoSet] = useState<Set<number>>(new Set())
  const [totalVerificadas, setTotalVerificadas] = useState(0)

  const uploadPdf = async (file: File) => {
    setUploading(true)
    setErro(null)
    try {
      const { texto: t } = await precedentCheckApi.extrairPdf(file)
      setTexto(t)
      if (!titulo) setTitulo(file.name.replace('.pdf', ''))
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detail || 'Erro ao extrair o PDF.')
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
    setVerificandoSet(new Set())

    try {
      const res = await precedentCheckApi.analisar({ texto, titulo: titulo || undefined })
      setAnaliseId(res.analise_id)
      setCitacoes(res.citacoes)
      // Aparece no histórico imediatamente (sem aguardar todas as verificações)
      qc.invalidateQueries({ queryKey: ['precedentcheck-historico'] })

      // Verifica em paralelo com pool de concorrência limitada — muito mais
      // rápido que sequencial (40 citações × 20s = 13min vira ~2min).
      const CONCORRENCIA = 6
      let proximo = 0
      const total = res.citacoes.length

      const worker = async () => {
        while (proximo < total) {
          const i = proximo++
          setVerificandoSet((prev) => new Set(prev).add(i))
          try {
            const verificada = await precedentCheckApi.verificarCitacao(res.analise_id, i)
            setCitacoes((prev) => { const next = [...prev]; next[i] = verificada; return next })
          } catch { /* continua */ }
          setVerificandoSet((prev) => { const next = new Set(prev); next.delete(i); return next })
          setTotalVerificadas((n) => n + 1)
        }
      }

      await Promise.all(
        Array.from({ length: Math.min(CONCORRENCIA, total) }, () => worker())
      )

      setVerificandoSet(new Set())
      qc.invalidateQueries({ queryKey: ['precedentcheck-historico'] })
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detail || 'Erro ao analisar.')
    } finally {
      setAnalisando(false)
      setVerificandoSet(new Set())
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
    setTexto(''); setTitulo(''); setCitacoes([])
    setAnaliseId(null); setErro(null); setTotalVerificadas(0)
  }

  const totalOk  = citacoes.filter((c) => c.status_geral === 'verificado').length
  const totalDiv = citacoes.filter((c) => c.status_geral === 'divergencia').length
  const totalNao = citacoes.filter((c) => c.status_geral === 'nao_encontrado').length

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          <ShieldCheck size={18} style={{ marginRight: 7, verticalAlign: 'middle' }} />
          PrecedentCheck
        </h1>
        {(citacoes.length > 0 || texto) && (
          <button className={styles.btnSmall} onClick={limpar}>
            <X size={13} /> {citacoes.length > 0 ? 'Fechar' : 'Limpar'}
          </button>
        )}
      </div>

      <div className={cs.layout}>
        {/* Painel esquerdo */}
        <div className={cs.painel}>
          <div className={cs.painelHeader}>
            <span className={cs.painelTitle}>Peça ou decisão</span>
          </div>
          {/* barra de progresso: indeterminada no upload, determinada na verificação */}
          {(uploading || analisando) && (
            <div className={cs.progressWrap}>
              {uploading && <div className={cs.progressFillIndeterminate} />}
              {analisando && citacoes.length > 0 && (
                <div
                  className={cs.progressFill}
                  style={{ width: `${Math.round((totalVerificadas / citacoes.length) * 100)}%` }}
                />
              )}
              {analisando && citacoes.length === 0 && <div className={cs.progressFillIndeterminate} />}
            </div>
          )}
          {erro && <div className={cs.erroBanner}>{erro}</div>}
          <div className={cs.painelBody}>
            <input
              className={cs.tituloInput}
              placeholder="Título (opcional)"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
            />
            {uploading ? (
              <div className={cs.uploadingState}>
                <div className={cs.loadingDot} />
                Extraindo texto do PDF…
              </div>
            ) : (
              <textarea
                className={cs.textarea}
                placeholder="Cole aqui o texto da peça, decisão, sentença ou acórdão — ou carregue um PDF abaixo."
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
              />
            )}
          </div>
          <div className={cs.painelFooter}>
            <div className={cs.uploadRow}>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                style={{ display: 'none' }}
                onChange={(e) => { if (e.target.files?.[0]) uploadPdf(e.target.files[0]) }}
              />
              <button type="button" className={styles.btnSmall} onClick={() => fileRef.current?.click()} disabled={uploading}>
                <FileUp size={13} /> {uploading ? 'Lendo…' : 'PDF'}
              </button>
              {texto && !uploading && (
                <span className={cs.charCount}>{texto.length.toLocaleString('pt-BR')} chars</span>
              )}
            </div>
            <button
              type="button"
              className={styles.btnPrimary}
              onClick={iniciarAnalise}
              disabled={analisando || uploading || !texto.trim()}
            >
              {analisando
                ? `Verificando ${totalVerificadas}/${citacoes.length || '?'}...`
                : 'Verificar precedentes'}
            </button>
          </div>
        </div>

        {/* Painel direito */}
        <div className={cs.resultados}>
          {citacoes.length > 0 && titulo && (
            <div className={cs.resultadosTitulo}>{titulo}</div>
          )}
          {citacoes.length > 0 && (
            <div className={cs.summaryBar}>
              <span className={cs.summaryLabel}>
                {citacoes.length} citaç{citacoes.length === 1 ? 'ão' : 'ões'} encontrada{citacoes.length === 1 ? '' : 's'}
                {analisando && ` — verificadas ${totalVerificadas}/${citacoes.length}`}
              </span>
              {totalOk > 0  && <span className={`${cs.chip} ${cs.chipOk}`}>{totalOk} ok</span>}
              {totalDiv > 0 && <span className={`${cs.chip} ${cs.chipDiv}`}>{totalDiv} div.</span>}
              {totalNao > 0 && <span className={`${cs.chip} ${cs.chipNao}`}>{totalNao} n/e</span>}
              {citacoes.length > 0 && (() => {
                const total = citacoes.reduce((acc, c) => acc + (c.custo_usd || 0), 0)
                if (total <= 0) return null
                return (
                  <span className={cs.custoBadge}>
                    {formatCusto(total)} {analisando ? 'parcial' : 'real'}
                  </span>
                )
              })()}
            </div>
          )}

          {citacoes.map((c, i) => (
            <CitacaoCard
              key={i}
              idx={i}
              citacao={c}
              verificando={verificandoSet.has(i)}
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
