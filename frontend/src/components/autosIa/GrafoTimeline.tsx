import { useMemo, useState } from 'react'
import type { GrafoAresta, GrafoNo, TipoPeca } from '../../api/autosIa'
import styles from './GrafoTimeline.module.css'

const ALTURA_LINHA = 52
const EIXO_X = 22

// Paleta categórica validada (8 matizes, ordem fixa, segura para daltonismo) —
// mapeada 1:1 nos 8 tipos de peça. A ordem não é escolhida por "combinar com
// o sentido" de cada tipo — é a ordem que passa nos testes de distinção.
const COR_POR_TIPO: Record<TipoPeca, string> = {
  peticao: '#2a78d6',
  decisao: '#eb6834',
  despacho: '#1baf7a',
  certidao: '#eda100',
  oficio: '#e87ba4',
  recurso: '#008300',
  documento: '#4a3aa7',
  outro: '#e34948',
}

function formatarData(d?: string | null): string {
  if (!d) return 'sem data'
  return new Date(d).toLocaleDateString('pt-BR')
}

/** Primeiras 1-2 frases do resumo — o popup é pra identificar do que se trata
 * num relance, não pra ler o resumo inteiro (esse já está na aba Peças). */
function resumoCurto(resumo?: string | null): string {
  if (!resumo) return 'Ainda sem resumo gerado.'
  const frases = resumo.split(/(?<=[.!?])\s+/).filter(Boolean)
  return frases.slice(0, 2).join(' ')
}

interface Props {
  nos: GrafoNo[]
  arestas: GrafoAresta[]
}

/** Linha do tempo visual: uma peça por linha (mais recente no topo), curvas à
 * esquerda ligando quem menciona quem, clique abre um resumo curto. Só peças
 * "mãe" viram nó — anexos (procurações, comprovantes...) ficam de fora, do
 * jeito que já são tratados no resto do Autos IA. */
export default function GrafoTimeline({ nos, arestas }: Props) {
  const [selecionado, setSelecionado] = useState<string | null>(null)

  const nosOrdenados = useMemo(() => {
    return nos
      .filter((n) => !n.peca_pai_id)
      .slice()
      .sort((a, b) => {
        if (!a.data_peca && !b.data_peca) return 0
        if (!a.data_peca) return 1
        if (!b.data_peca) return -1
        return a.data_peca > b.data_peca ? -1 : 1
      })
  }, [nos])

  const indicePorId = useMemo(() => {
    const mapa = new Map<string, number>()
    nosOrdenados.forEach((n, i) => mapa.set(n.id, i))
    return mapa
  }, [nosOrdenados])

  const incomingCount = useMemo(() => {
    const mapa = new Map<string, number>()
    arestas.forEach((a) => {
      if (a.peca_destino_id) mapa.set(a.peca_destino_id, (mapa.get(a.peca_destino_id) ?? 0) + 1)
    })
    return mapa
  }, [arestas])

  const arestasVisiveis = useMemo(() => {
    return arestas
      .filter((a) => a.peca_destino_id && indicePorId.has(a.peca_origem_id) && indicePorId.has(a.peca_destino_id))
      .map((a) => ({
        chave: a.id,
        origem: indicePorId.get(a.peca_origem_id)!,
        destino: indicePorId.get(a.peca_destino_id!)!,
      }))
  }, [arestas, indicePorId])

  const altura = nosOrdenados.length * ALTURA_LINHA

  if (nosOrdenados.length === 0) {
    return <p className={styles.vazio}>Nenhuma peça indexada ainda.</p>
  }

  return (
    <div className={styles.wrap}>
      <p className={styles.legendaTexto}>
        Cada ponto é uma peça — a mais recente no topo. As curvas à esquerda ligam uma peça a
        outra que ela menciona no texto. Clique num ponto (ou no título) pra ver o resumo.
      </p>

      <div className={styles.chart}>
        <svg
          className={styles.svgArestas}
          width={EIXO_X + 60}
          height={altura}
          style={{ overflow: 'visible' }}
          aria-hidden="true"
        >
          {arestasVisiveis.map((a) => {
            const y1 = a.origem * ALTURA_LINHA + ALTURA_LINHA / 2
            const y2 = a.destino * ALTURA_LINHA + ALTURA_LINHA / 2
            const distancia = Math.abs(a.destino - a.origem)
            const curva = Math.min(56, 14 + distancia * 5)
            const cx = EIXO_X - curva
            const emFoco =
              selecionado != null &&
              (nosOrdenados[a.origem]?.id === selecionado || nosOrdenados[a.destino]?.id === selecionado)
            return (
              <path
                key={a.chave}
                d={`M ${EIXO_X} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${EIXO_X} ${y2}`}
                className={`${styles.arestaPath} ${emFoco ? styles.arestaEmFoco : ''}`}
              />
            )
          })}
        </svg>

        <ul className={styles.linhas} style={{ minHeight: altura }}>
          {nosOrdenados.map((n) => {
            const cor = COR_POR_TIPO[n.tipo] ?? COR_POR_TIPO.outro
            const aberta = selecionado === n.id
            const entradas = incomingCount.get(n.id) ?? 0
            return (
              <li key={n.id} className={styles.linha} style={{ height: ALTURA_LINHA }}>
                <button
                  type="button"
                  className={styles.no}
                  style={{ background: cor, borderColor: cor }}
                  onClick={() => setSelecionado(aberta ? null : n.id)}
                  aria-expanded={aberta}
                  aria-label={`${n.tipo}: ${n.titulo}`}
                />
                <button
                  type="button"
                  className={styles.linhaConteudo}
                  onClick={() => setSelecionado(aberta ? null : n.id)}
                  aria-expanded={aberta}
                >
                  <span className={styles.dataTxt}>{formatarData(n.data_peca)}</span>
                  <span className={styles.tipoTxt} style={{ color: cor }}>{n.tipo}</span>
                  <span className={styles.tituloTxt}>{n.titulo}</span>
                  {entradas > 0 && <span className={styles.entradasBadge}>{entradas}×citada</span>}
                </button>

                {aberta && (
                  <div className={styles.popup} role="dialog">
                    <div className={styles.popupTopo}>
                      <span className={styles.popupTipo} style={{ color: cor }}>{n.tipo}</span>
                      {n.autor && <span className={styles.popupAutor}>{n.autor}</span>}
                    </div>
                    <div className={styles.popupResumo}>{resumoCurto(n.resumo)}</div>
                    {n.keywords && n.keywords.length > 0 && (
                      <div className={styles.popupKeywords}>
                        {n.keywords.map((k) => <span key={k}>{k}</span>)}
                      </div>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </div>

      <div className={styles.legendaTipos}>
        {(Object.keys(COR_POR_TIPO) as TipoPeca[]).map((t) => (
          <span key={t} className={styles.legendaItem}>
            <span className={styles.legendaDot} style={{ background: COR_POR_TIPO[t] }} />
            {t}
          </span>
        ))}
      </div>
    </div>
  )
}
