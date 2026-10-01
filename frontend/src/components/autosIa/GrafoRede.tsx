import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { autosIa, TIPOS_PECA } from '../../api/autosIa'
import type { GrafoAresta, GrafoNo, TipoPeca } from '../../api/autosIa'
import styles from './GrafoRede.module.css'

// Paleta categórica validada (8 matizes, ordem fixa, segura para
// daltonismo), mapeada 1:1 nos 8 tipos de peça — mesma paleta usada em
// outras visualizações do Autos IA (ex.: painel de peças).
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
const NOME_TIPO = Object.fromEntries(TIPOS_PECA.map((t) => [t.value, t.label])) as Record<TipoPeca, string>
// Ordem das faixas (de cima pra baixo): o que as partes pedem, depois o que o juízo decide.
const ORDEM_TIPOS: TipoPeca[] = ['peticao', 'decisao', 'despacho', 'certidao', 'oficio', 'recurso', 'documento', 'outro']

const DIA_MS = 86_400_000
const MARGEM_ESQ = 112 // gutter dos rótulos das faixas
const MARGEM_DIR = 28
const ALTURA_EIXO = 46
const ALTURA_FAIXA_MIN = 54
const PADDING_FAIXA = 10
const ZOOM_MAX = 90

const loc = d3.timeFormatLocale({
  dateTime: '%A, %e de %B de %Y', date: '%d/%m/%Y', time: '%H:%M:%S', periods: ['AM', 'PM'],
  days: ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'],
  shortDays: ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'],
  months: ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'],
  shortMonths: ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
})
const fDia = loc.format('%d')
const fSemana = loc.format('%d %b')
const fMes = loc.format('%b')
const fAno = loc.format('%Y')
const fCompleta = loc.format('%a, %d %b %Y')
const fCurta = loc.format('%d %b %Y')

type NivelTick = 'dia' | 'semana' | 'mes' | 'ano'
const ESPACO_MIN_ENTRE_RODULOS_PX = 52

/** Escolhe a granularidade da régua pelo espaço (px) por dia — sempre com rótulos
 * espaçados o bastante pra serem lidos —, em vez de deixar o D3 decidir (que, com
 * ~4 meses na tela, mostrava só 3 rótulos de mês). */
function gerarTicks(inicio: Date, fim: Date, larguraPx: number): { ticks: Date[]; nivel: NivelTick } {
  const dias = Math.max(1, (fim.getTime() - inicio.getTime()) / DIA_MS)
  const pxPorDia = larguraPx / dias
  const opcoes: { dias: number; nivel: NivelTick; intervalo: d3.TimeInterval }[] = [
    { dias: 1, nivel: 'dia', intervalo: d3.timeDay.every(1)! },
    { dias: 2, nivel: 'dia', intervalo: d3.timeDay.every(2)! },
    { dias: 7, nivel: 'semana', intervalo: d3.timeMonday.every(1)! },
    { dias: 14, nivel: 'semana', intervalo: d3.timeMonday.every(2)! },
    { dias: 30, nivel: 'mes', intervalo: d3.timeMonth.every(1)! },
    { dias: 61, nivel: 'mes', intervalo: d3.timeMonth.every(2)! },
    { dias: 91, nivel: 'mes', intervalo: d3.timeMonth.every(3)! },
    { dias: 365, nivel: 'ano', intervalo: d3.timeYear.every(1)! },
  ]
  const escolhida = opcoes.find((o) => o.dias * pxPorDia >= ESPACO_MIN_ENTRE_RODULOS_PX) ?? opcoes[opcoes.length - 1]
  return { ticks: escolhida.intervalo.range(inicio, fim), nivel: escolhida.nivel }
}

/** Rótulo por nível: dia → "13" (e o nome do mês no dia 1º); semana → "13 abr"; mês → "abr" (ano em janeiro). */
function rotuloTick(d: Date, nivel: NivelTick): string {
  if (nivel === 'dia') return d.getDate() === 1 ? fMes(d) : fDia(d)
  if (nivel === 'semana') return fSemana(d)
  if (nivel === 'mes') return d.getMonth() === 0 ? fAno(d) : fMes(d)
  return fAno(d)
}
function ehInicioDeMes(d: Date): boolean { return d3.timeMonth(d) >= d }

function formatarData(d?: string | null): string {
  if (!d) return 'sem data'
  // "AAAA-MM-DD" sem hora vira meia-noite UTC, que no fuso do Brasil (UTC-3)
  // exibe o dia anterior — mesmo cuidado do resto do Autos IA.
  const [ano, mes, dia] = d.split('T')[0].split('-').map(Number)
  return new Date(ano, mes - 1, dia).toLocaleDateString('pt-BR')
}

function parseDataLocal(d?: string | null): Date | null {
  if (!d) return null
  const [ano, mes, dia] = d.split('T')[0].split('-').map(Number)
  return new Date(ano, mes - 1, dia)
}

function escapeHtml(s: string): string {
  const div = document.createElement('div')
  div.textContent = s
  return div.innerHTML
}

interface NoInterno extends GrafoNo {
  citacoes: number
  /** Dia da peça (meia-noite local); null = sem data. */
  dt: Date | null
  /** Instante usado no eixo X: o dia + uma fração dele pela ordem das páginas, pra
   * peças do mesmo dia não se sobreporem nem trocarem de ordem. */
  dtx: Date | null
  /** Posição vertical final (centro da faixa + deslocamento do empilhamento). */
  y: number
  visivel: boolean
}
interface LinkInterno {
  id: string
  source: NoInterno
  target: NoInterno
}

interface Props {
  nos: GrafoNo[]
  arestas: GrafoAresta[]
  /** Chamado depois de disparar uma releitura — o pai invalida as queries
   * (grafo/documentos) pra os dados atualizados aparecerem. Guardado em ref
   * (não é dependência do efeito): identidade nova a cada render do pai não
   * pode derrubar e reconstruir o grafo inteiro à toa. */
  onRelido?: () => void
}

/** Linha do tempo de peças: cada peça-mãe é um ponto, na posição horizontal EXATA
 * da sua data (régua fixa no topo, com mês/ano), em uma faixa por tipo (petição,
 * decisão, despacho...). Dimensionado por quantas vezes é citada; as linhas mostram
 * quem menciona quem. Clique isola a vizinhança e abre o painel de detalhe; "Fixar"
 * trava a vizinhança atual. Filtros: tipo, busca, advogado responsável e período
 * (De–Até, que também ajusta o zoom). Tudo é construído imperativamente com D3
 * dentro de `rootRef` — zoom/pan não convivem bem com o ciclo de re-render do React. */
export default function GrafoRede({ nos, arestas, onRelido }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const onRelidoRef = useRef(onRelido)
  useEffect(() => { onRelidoRef.current = onRelido }, [onRelido])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return

    const nosRaiz: NoInterno[] = nos
      .filter((n) => !n.peca_pai_id)
      .map((n) => ({ ...n, citacoes: 0, dt: parseDataLocal(n.data_peca), dtx: null, y: 0, visivel: true }))
    if (nosRaiz.length === 0) return

    // Dentro do mesmo dia, a ordem das páginas (≈ ordem de juntada) distribui as
    // peças ao longo do dia no eixo X — a hora de protocolo não entra aqui de
    // propósito (ela depende de fuso e nem toda peça tem), então a ordem exibida
    // é a mesma da listagem de Documentos.
    const porDia = new Map<string, NoInterno[]>()
    nosRaiz.forEach((n) => {
      if (!n.dt) return
      const chave = n.dt.getTime().toString()
      porDia.set(chave, [...(porDia.get(chave) ?? []), n])
    })
    porDia.forEach((lista) => {
      lista.sort((a, b) => a.pagina_inicio - b.pagina_inicio)
      lista.forEach((n, i) => {
        n.dtx = new Date(n.dt!.getTime() + (0.05 + 0.9 * ((i + 0.5) / lista.length)) * DIA_MS)
      })
    })

    const byId = new Map<string, NoInterno>()
    nosRaiz.forEach((n) => byId.set(n.id, n))

    // Anexos (peca_pai_id preenchido) não viram ponto próprio no grafo — ficam
    // "dentro" da peça-mãe. Mas uma referência pode mirar direto no ID de um
    // anexo (ex.: uma decisão citando o "Id. 104282427" de um documento
    // anexado a uma peça), e o backend já resolveu isso certinho em
    // peca_destino_id. Sem este passo, `byId.has(destino)` dava falso pra
    // qualquer anexo e a menção caía como "não localizado" mesmo já
    // resolvida — foi o que o Lucas flagrou com a ID 104282427. Resolve
    // sempre pro nó-raiz visível (a própria peça-mãe) antes de checar/contar.
    const paiPorId = new Map<string, string | null | undefined>()
    nos.forEach((n) => paiPorId.set(n.id, n.peca_pai_id))
    function resolverRaiz(id: string): string {
      let atual = id
      const visitados = new Set<string>()
      while (paiPorId.get(atual) && !visitados.has(atual)) {
        visitados.add(atual)
        atual = paiPorId.get(atual)!
      }
      return atual
    }

    const mencoesPorOrigem = new Map<string, GrafoAresta[]>()
    arestas.forEach((a) => {
      const origem = resolverRaiz(a.peca_origem_id)
      if (!byId.has(origem)) return
      const lista = mencoesPorOrigem.get(origem) ?? []
      lista.push(a)
      mencoesPorOrigem.set(origem, lista)
    })

    const links: LinkInterno[] = arestas
      .filter((a) => a.peca_destino_id)
      .map((a) => ({ id: a.id, source: byId.get(resolverRaiz(a.peca_origem_id)), target: byId.get(resolverRaiz(a.peca_destino_id!)) }))
      .filter((l): l is LinkInterno => !!l.source && !!l.target && l.source !== l.target)
    links.forEach((l) => { l.target.citacoes += 1 })

    const citadaPorDestino = new Map<string, GrafoAresta[]>()
    arestas.forEach((a) => {
      if (!a.peca_destino_id) return
      const destino = resolverRaiz(a.peca_destino_id)
      const origem = resolverRaiz(a.peca_origem_id)
      if (!byId.has(destino) || !byId.has(origem) || destino === origem) return
      const lista = citadaPorDestino.get(destino) ?? []
      lista.push(a)
      citadaPorDestino.set(destino, lista)
    })

    const tiposPresentes = ORDEM_TIPOS.filter((t) => nosRaiz.some((n) => n.tipo === t))
    let tiposAtivos = new Set(tiposPresentes)
    const advogados = Array.from(new Set(nosRaiz.map((n) => n.advogado_responsavel).filter((a): a is string => !!a)))
      .sort((a, b) => a.localeCompare(b, 'pt-BR'))
    const comDatas = nosRaiz.filter((n) => n.dtx)
    const minData = comDatas.length ? d3.min(comDatas, (n) => n.dt as Date)! : null
    const maxData = comDatas.length ? d3.max(comDatas, (n) => n.dt as Date)! : null
    const iso = (d: Date | null) => d
      ? `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      : ''

    // ---- monta a casca de DOM (sidebar, régua, canvas, painel, tooltip) ----
    root.innerHTML = `
      <div class="${styles.wrap}">
        <aside class="${styles.aside}">
          <div>
            <span class="${styles.fieldLabel}">Busca</span>
            <input type="search" class="${styles.searchInput}" placeholder="Título, ID, autor, advogado..." autocomplete="off" />
          </div>
          <div class="${styles.statsGrid}">
            <div class="${styles.stat}"><div class="${styles.statN}" data-role="nPecas">${nosRaiz.length}</div><div class="${styles.statL}">peças</div></div>
            <div class="${styles.stat}"><div class="${styles.statN}" data-role="nCitacoes">${links.length}</div><div class="${styles.statL}">citações</div></div>
          </div>
          <div>
            <span class="${styles.fieldLabel}">Período (de – até)</span>
            <div class="${styles.periodoCol}">
              <label class="${styles.periodoLinha}"><span>De</span>
                <input type="date" class="${styles.dateInput}" data-role="de" aria-label="Data inicial" min="${iso(minData)}" max="${iso(maxData)}" /></label>
              <label class="${styles.periodoLinha}"><span>Até</span>
                <input type="date" class="${styles.dateInput}" data-role="ate" aria-label="Data final" min="${iso(minData)}" max="${iso(maxData)}" /></label>
            </div>
            <button type="button" class="${styles.limparBtn}" data-role="limparPeriodo" style="display:none">✕ Limpar período</button>
          </div>
          ${advogados.length > 0 ? `
          <div>
            <span class="${styles.fieldLabel}">Advogado responsável</span>
            <select class="${styles.selectInput}" data-role="advogado">
              <option value="">Todos</option>
              <option value="__sem__">(sem advogado)</option>
              ${advogados.map((a) => `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`).join('')}
            </select>
          </div>` : ''}
          <div>
            <span class="${styles.fieldLabel}">Tipos (clique filtra · "só" isola)</span>
            <div class="${styles.legend}" data-role="legend"></div>
          </div>
          <details class="${styles.idxWrap}">
            <summary>Índice de IDs</summary>
            <div class="${styles.idIndex}" data-role="idindex"></div>
          </details>
          <div class="${styles.hint}">
            <strong>Como ler:</strong> cada faixa é um tipo de peça e a posição horizontal é a data exata
            (régua no topo; mais antiga à esquerda). Peças do mesmo dia ficam lado a lado, na ordem das
            páginas. O tamanho do ponto cresce com quantas vezes a peça é citada; as linhas mostram quem
            menciona quem. Passe o mouse num ponto pra ver a data na régua; clique pra ver o resumo e
            isolar suas conexões. Role pra dar zoom na linha do tempo, arraste pra andar nela — ou use o
            filtro de período.
          </div>
        </aside>
        <main class="${styles.canvasWrap}">
          <svg class="${styles.axisSvg}" data-role="axisSvg" height="${ALTURA_EIXO}"></svg>
          <div class="${styles.scrollArea}" data-role="scrollArea">
            <svg class="${styles.graphSvg}" data-role="graphSvg"></svg>
          </div>
          <div class="${styles.zoomControls}">
            <button type="button" class="${styles.zoomBtn}" data-role="zoomIn" aria-label="Mais zoom">+</button>
            <button type="button" class="${styles.zoomBtn}" data-role="zoomOut" aria-label="Menos zoom">−</button>
            <button type="button" class="${styles.zoomBtn}" data-role="zoomReset" aria-label="Ver tudo" title="Ver tudo (limpa o período)">⤢</button>
          </div>
          <div class="${styles.panel}" data-role="panel">
            <button type="button" class="${styles.panelClose}" data-role="panelClose" aria-label="Fechar">✕</button>
            <span class="${styles.tipoPill}" data-role="pTipo"></span>
            <a class="${styles.driveLink}" data-role="pDrive" href="#" target="_blank" rel="noreferrer" title="Abrir no Drive" aria-label="Abrir no Drive">↗</a>
            <h2 class="${styles.panelTitulo}" data-role="pTitulo"></h2>
            <div class="${styles.panelMeta}" data-role="pMeta"></div>
            <div class="${styles.avisoLeitura}" data-role="pAviso"></div>
            <button type="button" class="${styles.relerBtn}" data-role="pReler">↻ Reler documento</button>
            <button type="button" class="${styles.fixBtn}" data-role="pFixar">📌 Fixar estas conexões</button>
            <div class="${styles.relLabel}">IDs mencionados neste texto</div>
            <div data-role="pIds"></div>
            <div class="${styles.resumo}" data-role="pResumo"></div>
            <div data-role="pMenciona"></div>
            <div data-role="pCitada"></div>
          </div>
        </main>
        <div class="${styles.tooltip}" data-role="tooltip"></div>
      </div>
    `

    const q = <T extends Element>(sel: string) => root.querySelector<T>(sel)!
    const legendEl = q<HTMLDivElement>('[data-role="legend"]')
    const idIndexEl = q<HTMLDivElement>('[data-role="idindex"]')
    const canvasWrap = q<HTMLDivElement>(`.${styles.canvasWrap}`)
    const scrollArea = q<HTMLDivElement>('[data-role="scrollArea"]')
    const panel = q<HTMLDivElement>('[data-role="panel"]')
    const tooltip = q<HTMLDivElement>('[data-role="tooltip"]')
    const buscaInput = q<HTMLInputElement>(`.${styles.searchInput}`)
    const deInput = q<HTMLInputElement>('[data-role="de"]')
    const ateInput = q<HTMLInputElement>('[data-role="ate"]')
    const limparPeriodoBtn = q<HTMLButtonElement>('[data-role="limparPeriodo"]')
    const advSelect = root.querySelector<HTMLSelectElement>('[data-role="advogado"]')

    // ---- legenda + índice de IDs ----
    tiposPresentes.forEach((tipo) => {
      const count = nosRaiz.filter((n) => n.tipo === tipo).length
      const row = document.createElement('div')
      row.className = styles.legendRow
      row.setAttribute('data-tipo', tipo)
      row.innerHTML = `<span class="${styles.swatch}" style="background:${COR_POR_TIPO[tipo]}"></span>` +
        `<span class="${styles.legendName}">${NOME_TIPO[tipo]}</span>` +
        `<span class="${styles.legendRight}"><button type="button" class="${styles.onlyBtn}">só</button>` +
        `<span class="${styles.legendCount}">${count}</span></span>`
      row.addEventListener('click', () => {
        if (tiposAtivos.has(tipo)) { tiposAtivos.delete(tipo); row.classList.add(styles.legendOff) }
        else { tiposAtivos.add(tipo); row.classList.remove(styles.legendOff) }
        if (fixado) { fixado = false; fixadoIds = null; atualizarBotaoFixar() }
        aplicarFiltro()
      })
      row.querySelector('button')!.addEventListener('click', (ev) => {
        ev.stopPropagation()
        tiposAtivos = new Set([tipo])
        legendEl.querySelectorAll<HTMLDivElement>(`.${styles.legendRow}`).forEach((r) => {
          r.classList.toggle(styles.legendOff, r.getAttribute('data-tipo') !== tipo)
        })
        if (fixado) { fixado = false; fixadoIds = null; atualizarBotaoFixar() }
        aplicarFiltro()
      })
      legendEl.appendChild(row)
    })

    let idxHtml = ''
    tiposPresentes.forEach((tipo) => {
      const itens = nosRaiz.filter((n) => n.tipo === tipo && n.id_processual)
      if (itens.length === 0) return
      idxHtml += `<div class="${styles.idxGroup}"><div class="${styles.idxGroupTitle}">` +
        `<span class="${styles.swatch}" style="background:${COR_POR_TIPO[tipo]}"></span>${NOME_TIPO[tipo]} · ${itens.length}</div>`
      itens.forEach((n) => {
        idxHtml += `<div class="${styles.idxItem}" data-id="${n.id}">` +
          `<span class="${styles.idxIid}">${escapeHtml(n.id_processual!)}</span>` +
          `<span class="${styles.idxTitle}">${escapeHtml(n.titulo)}</span></div>`
      })
      idxHtml += '</div>'
    })
    // Anexos (documentos dentro de uma peça-mãe) não têm ponto próprio no
    // grafo, mas podem ser citados pelo ID deles — sem entrar aqui também no
    // índice, o ID simplesmente "sumia" da busca mesmo já tendo leitura.
    // Clique navega pra peça-mãe, que é quem aparece visualmente.
    const anexosComId = nos.filter((n) => n.peca_pai_id && n.id_processual)
    if (anexosComId.length > 0) {
      idxHtml += `<div class="${styles.idxGroup}"><div class="${styles.idxGroupTitle}">` +
        `<span class="${styles.swatch}" style="background:${COR_POR_TIPO.documento}"></span>Anexos · ${anexosComId.length}</div>`
      anexosComId.forEach((n) => {
        const raizId = resolverRaiz(n.id)
        const pai = byId.get(raizId)
        idxHtml += `<div class="${styles.idxItem}" data-id="${raizId}">` +
          `<span class="${styles.idxIid}">${escapeHtml(n.id_processual!)}</span>` +
          `<span class="${styles.idxTitle}">${escapeHtml(n.titulo)}${pai ? ' · anexo de ' + escapeHtml(pai.titulo) : ''}</span></div>`
      })
      idxHtml += '</div>'
    }
    idIndexEl.innerHTML = idxHtml || `<p class="${styles.relEmpty}">Nenhuma peça com ID processual neste caso.</p>`
    idIndexEl.querySelectorAll<HTMLDivElement>(`.${styles.idxItem}`).forEach((el) => {
      const n = byId.get(el.getAttribute('data-id')!)
      if (!n) return
      el.addEventListener('mousemove', (ev) => mostrarTooltip(ev, n))
      el.addEventListener('mouseleave', esconderTooltip)
      el.addEventListener('click', () => irPara(n.id))
    })

    // ---- SVGs: régua fixa (topo) + faixas/pontos/linhas ----
    const axisSvg = d3.select(q<SVGSVGElement>('[data-role="axisSvg"]'))
    const svg = d3.select(q<SVGSVGElement>('[data-role="graphSvg"]'))
    const defs = svg.append('defs')
    tiposPresentes.forEach((tipo) => {
      defs.append('marker')
        .attr('id', `arrow-${tipo}`)
        .attr('viewBox', '0 -4 8 8')
        .attr('refX', 7).attr('refY', 0)
        .attr('markerWidth', 6).attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-4L8,0L0,4')
        .attr('fill', 'var(--gray-mid)')
        .attr('opacity', 0.5)
    })

    // Pontos/linhas/grade ficam recortados à área do tempo — ao andar a linha do tempo,
    // nada passa por cima dos nomes das faixas (gutter da esquerda).
    const clipId = `clip-grafo-${Math.random().toString(36).slice(2, 9)}`
    const clipRect = defs.append('clipPath').attr('id', clipId).append('rect').attr('y', 0)
    const laneLayer = svg.append('g')
    const gridLayer = svg.append('g').attr('clip-path', `url(#${clipId})`)
    const guideLine = svg.append('line').attr('class', styles.guideLine).style('display', 'none')
    const edgeLayer = svg.append('g').attr('clip-path', `url(#${clipId})`)
    const nodeLayer = svg.append('g').attr('clip-path', `url(#${clipId})`)

    const axisTicks = axisSvg.append('g')
    const axisPeriodo = axisSvg.append('text').attr('class', styles.axisPeriodo).attr('x', 10).attr('y', 14)
    const guideLabel = axisSvg.append('g').style('display', 'none')
    const guideRect = guideLabel.append('rect').attr('class', styles.guideRect).attr('y', 2).attr('height', 18).attr('rx', 5)
    const guideText = guideLabel.append('text').attr('class', styles.guideText).attr('y', 15).attr('text-anchor', 'middle')

    const radius = d3.scaleSqrt()
      .domain([0, d3.max(nosRaiz, (n) => n.citacoes) || 1])
      .range([4.5, 12])

    let W = 600
    let H = 400
    let xBase = d3.scaleTime()
    let dominio: [Date, Date] = [new Date(), new Date()]
    let transformAtual = d3.zoomIdentity
    let lanesInfo: { tipo: TipoPeca; top: number; h: number }[] = []

    const xz = () => transformAtual.rescaleX(xBase)
    const semDataX = () => W - MARGEM_DIR + 2
    const posX = (n: NoInterno, escala: d3.ScaleTime<number, number>) => (n.dtx ? escala(n.dtx) : semDataX())

    /** Calcula domínio X, empilhamento (beeswarm) por faixa e alturas. Roda no início
     * e a cada resize (a largura muda as colisões). */
    function calcularLayout() {
      W = Math.max(320, scrollArea.clientWidth || 600)
      const alturaDisponivel = Math.max(220, scrollArea.clientHeight || 420)

      if (comDatas.length > 0) {
        const t0 = d3.min(comDatas, (n) => n.dtx as Date)!.getTime()
        const t1 = d3.max(comDatas, (n) => n.dtx as Date)!.getTime()
        const pad = Math.max(1.5 * DIA_MS, (t1 - t0) * 0.025)
        dominio = [new Date(t0 - pad), new Date(t1 + pad)]
      } else {
        const hoje = Date.now()
        dominio = [new Date(hoje - 15 * DIA_MS), new Date(hoje + 15 * DIA_MS)]
      }
      xBase = d3.scaleTime().domain(dominio).range([MARGEM_ESQ, W - MARGEM_DIR - (comDatas.length < nosRaiz.length ? 26 : 0)])

      const montar = (passo: number) => {
        const info: { tipo: TipoPeca; top: number; h: number; meio: number }[] = []
        let acumulado = 0
        tiposPresentes.forEach((tipo) => {
          const itens = nosRaiz.filter((n) => n.tipo === tipo).sort((a, b) => {
            const xa = a.dtx ? a.dtx.getTime() : Infinity
            const xb = b.dtx ? b.dtx.getTime() : Infinity
            return xa - xb || a.pagina_inicio - b.pagina_inicio
          })
          const colocados: { x: number; y: number; r: number }[] = []
          let maxK = 0
          const candidatos = [0]
          for (let k = 1; k <= 60; k++) candidatos.push(k, -k)
          itens.forEach((n) => {
            const x = posX(n, xBase)
            const r = radius(n.citacoes)
            let escolhido = 0
            let kEscolhido = 0
            for (const k of candidatos) {
              const y = k * passo
              let livre = true
              for (let i = colocados.length - 1; i >= 0; i--) {
                const p = colocados[i]
                if (x - p.x > 40) break
                const dx = x - p.x, dy = y - p.y
                const min = r + p.r + 2.5
                if (dx * dx + dy * dy < min * min) { livre = false; break }
              }
              if (livre) { escolhido = y; kEscolhido = k; break }
            }
            n.y = escolhido
            colocados.push({ x, y: escolhido, r })
            maxK = Math.max(maxK, Math.abs(kEscolhido))
          })
          const h = Math.max(ALTURA_FAIXA_MIN, 2 * (maxK * passo + 12 + PADDING_FAIXA))
          info.push({ tipo, top: acumulado, h, meio: acumulado + h / 2 })
          acumulado += h
        })
        return { info, total: acumulado }
      }

      let resultado = montar(13)
      for (const passo of [10, 8, 7]) {
        if (resultado.total <= alturaDisponivel) break
        resultado = montar(passo)
      }
      // Sobrou altura: distribui entre as faixas pra ocupar o quadro todo.
      const extra = Math.max(0, alturaDisponivel - resultado.total) / Math.max(1, resultado.info.length)
      let topo = 0
      lanesInfo = resultado.info.map((l) => {
        const h = l.h + extra
        const item = { tipo: l.tipo, top: topo, h }
        topo += h
        return item
      })
      H = Math.max(alturaDisponivel, resultado.total)
      // Reposiciona o Y absoluto (o beeswarm guardou só o deslocamento em relação ao centro da faixa).
      lanesInfo.forEach((l) => {
        nosRaiz.filter((n) => n.tipo === l.tipo).forEach((n) => { n.y = l.top + l.h / 2 + n.y })
      })
      svg.attr('width', W).attr('height', H)
      axisSvg.attr('width', W)
      clipRect.attr('x', MARGEM_ESQ - 8).attr('width', Math.max(0, W - MARGEM_ESQ + 8)).attr('height', H)
    }

    // ---- elementos que dependem do layout (faixas) ----
    function desenharFaixas() {
      laneLayer.selectAll('*').remove()
      lanesInfo.forEach((l, i) => {
        laneLayer.append('rect')
          .attr('class', i % 2 === 0 ? styles.laneBand : `${styles.laneBand} ${styles.laneBandAlt}`)
          .attr('x', 0).attr('y', l.top).attr('width', W).attr('height', l.h)
        const rotulo = laneLayer.append('g').attr('transform', `translate(10,${l.top + l.h / 2})`)
        rotulo.append('rect').attr('width', 8).attr('height', 8).attr('rx', 2).attr('y', -4).attr('fill', COR_POR_TIPO[l.tipo])
        rotulo.append('text').attr('class', styles.laneLabel).attr('x', 14).attr('y', -1).text(NOME_TIPO[l.tipo])
        rotulo.append('text').attr('class', styles.laneCount).attr('x', 14).attr('y', 11)
          .text(`${nosRaiz.filter((n) => n.tipo === l.tipo).length} peça(s)`)
      })
      if (comDatas.length < nosRaiz.length) {
        laneLayer.append('text').attr('class', styles.laneCount).attr('x', semDataX()).attr('y', 12).attr('text-anchor', 'end').text('sem data →')
      }
    }

    const edgeSel = edgeLayer.selectAll<SVGPathElement, LinkInterno>('path').data(links).enter().append('path')
      .attr('class', styles.edge)
      .attr('marker-end', (d) => `url(#arrow-${d.target.tipo})`)

    const nodeSel = nodeLayer.selectAll<SVGGElement, NoInterno>('g').data(nosRaiz).enter().append('g')
      .attr('class', styles.node)
    nodeSel.append('circle')
      .attr('r', (d) => radius(d.citacoes))
      .attr('fill', (d) => COR_POR_TIPO[d.tipo])
    nodeSel.append('text')
      .attr('class', styles.nodeText)
      .attr('dy', (d) => radius(d.citacoes) + 11)
      .attr('text-anchor', 'middle')
      .text((d) => (d.titulo.length > 26 ? d.titulo.slice(0, 26) + '…' : d.titulo))

    function caminho(s: NoInterno, t: NoInterno, escala: d3.ScaleTime<number, number>): string {
      const x1 = posX(s, escala), y1 = s.y, x2 = posX(t, escala), y2 = t.y
      const alt = Math.min(80, 14 + Math.hypot(x2 - x1, y2 - y1) * 0.16)
      return `M${x1},${y1}Q${(x1 + x2) / 2},${(y1 + y2) / 2 - alt} ${x2},${y2}`
    }

    /** Reposiciona tudo conforme o zoom/pan atual: pontos, linhas, régua e grade. */
    function renderizar() {
      const escala = xz()
      nodeSel.attr('transform', (d) => `translate(${posX(d, escala)},${d.y})`)
      edgeSel.attr('d', (d) => caminho(d.source, d.target, escala))
      nodeSel.select<SVGTextElement>('text').style('display', (d) => (transformAtual.k >= 2.4 || d.id === selecionadoId ? null : 'none'))

      const ini = escala.invert(MARGEM_ESQ), fim = escala.invert(W - MARGEM_DIR)
      const { ticks, nivel } = gerarTicks(ini, fim, W - MARGEM_ESQ - MARGEM_DIR)
      // Grade: um traço por rótulo + um mais forte em cada início de mês (referência de
      // mês mesmo quando a régua está em dias/semanas).
      const gradeDatas = Array.from(new Map([...ticks, ...d3.timeMonth.range(ini, fim)].map((t) => [t.getTime(), t])).values())
      gridLayer.selectAll<SVGLineElement, Date>('line').data(gradeDatas, (t) => String(t.getTime()))
        .join('line')
        .attr('class', (t) => (ehInicioDeMes(t) ? `${styles.gridLine} ${styles.gridLineForte}` : styles.gridLine))
        .attr('x1', (t) => escala(t)).attr('x2', (t) => escala(t)).attr('y1', 0).attr('y2', H)
      axisTicks.selectAll<SVGGElement, Date>('g').data(ticks, (t) => String(t.getTime()))
        .join((enter) => {
          const g = enter.append('g')
          g.append('line').attr('y1', ALTURA_EIXO - 7).attr('y2', ALTURA_EIXO)
          g.append('text').attr('y', ALTURA_EIXO - 12).attr('text-anchor', 'middle')
          return g
        })
        .attr('class', (t) => (ehInicioDeMes(t) ? `${styles.tick} ${styles.tickForte}` : styles.tick))
        .attr('transform', (t) => `translate(${escala(t)},0)`)
        .each(function (t) { d3.select(this).select('text').text(rotuloTick(t, nivel)) })
      axisPeriodo.text(comDatas.length ? `${fCurta(ini)} → ${fCurta(fim)}` : 'sem datas nas peças')
      // linha-guia acompanha a peça em foco
      if (guiaId) mostrarGuia(byId.get(guiaId)!)
    }

    // ---- guia de data (liga o ponto à régua) ----
    let guiaId: string | null = null
    function mostrarGuia(d: NoInterno) {
      if (!d.dtx) return
      guiaId = d.id
      const x = posX(d, xz())
      guideLine.style('display', null).attr('x1', x).attr('x2', x).attr('y1', 0).attr('y2', H)
      const texto = fCompleta(d.dt as Date)
      guideText.text(texto).attr('x', 0)
      const largura = texto.length * 6.2 + 14
      guideRect.attr('x', -largura / 2).attr('width', largura)
      guideLabel.style('display', null).attr('transform', `translate(${Math.min(W - largura / 2 - 4, Math.max(largura / 2 + 4, x))},0)`)
    }
    function esconderGuia() {
      guiaId = null
      guideLine.style('display', 'none')
      guideLabel.style('display', 'none')
      if (selecionadoId) { const sel = byId.get(selecionadoId); if (sel) mostrarGuia(sel) }
    }

    const TOOLTIP_LARGURA = 260
    function mostrarTooltip(event: MouseEvent, d: NoInterno) {
      // Não sobrepõe o painel de detalhe (aberto ou não): a régua da direita
      // é o painel quando aberto, senão a própria janela — sem isso o
      // tooltip ficava por cima do painel, com fundo escuro, tapando o
      // resumo real que o clique já tinha aberto ali.
      const panelAberto = panel.classList.contains(styles.panelOpen)
      const limiteDireita = (panelAberto ? panel.getBoundingClientRect().left : window.innerWidth) - 12
      const esquerda = Math.min(event.clientX + 14, limiteDireita - TOOLTIP_LARGURA)
      tooltip.style.left = `${Math.max(8, esquerda)}px`
      tooltip.style.top = `${Math.min(event.clientY + 10, window.innerHeight - 130)}px`
      tooltip.style.opacity = '1'
      const resumoTrecho = d.resumo ? `<div class="${styles.ttKw}">${escapeHtml(d.resumo.slice(0, 120))}${d.resumo.length > 120 ? '…' : ''}</div>` : ''
      const kwTrecho = d.keywords && d.keywords.length ? `<div class="${styles.ttKw}">${d.keywords.map(escapeHtml).join(' · ')}</div>` : ''
      const advTrecho = d.advogado_responsavel ? `<div class="${styles.ttKw}">⚖ ${escapeHtml(d.advogado_responsavel)}</div>` : ''
      tooltip.innerHTML = `<div class="${styles.ttTipo}" style="color:${COR_POR_TIPO[d.tipo]}">${NOME_TIPO[d.tipo]}${d.id_processual ? ' · ID ' + escapeHtml(d.id_processual) : ''}</div>` +
        `<strong>${escapeHtml(d.titulo)}</strong><br>${formatarData(d.data_peca)}${d.autor ? ' · ' + escapeHtml(d.autor) : ''}` +
        (d.citacoes ? `<br>citada ${d.citacoes}x` : '') + advTrecho + resumoTrecho + kwTrecho
    }
    function esconderTooltip() { tooltip.style.opacity = '0' }

    nodeSel
      .on('mousemove', (event, d) => { mostrarTooltip(event, d); mostrarGuia(d) })
      .on('mouseleave', () => { esconderTooltip(); esconderGuia() })
      .on('click', (_event, d) => { esconderTooltip(); irPara(d.id) })

    // ---- zoom/pan só no eixo do tempo (os pontos mantêm o tamanho) ----
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([1, ZOOM_MAX])
      .on('zoom', (event) => {
        transformAtual = event.transform
        renderizar()
      })
    function configurarZoom() {
      zoom.extent([[0, 0], [W, H]]).translateExtent([[0, 0], [W, H]])
    }
    svg.call(zoom).on('dblclick.zoom', null)
    q<HTMLButtonElement>('[data-role="zoomIn"]').addEventListener('click', () => svg.transition().call(zoom.scaleBy, 1.4))
    q<HTMLButtonElement>('[data-role="zoomOut"]').addEventListener('click', () => svg.transition().call(zoom.scaleBy, 1 / 1.4))
    q<HTMLButtonElement>('[data-role="zoomReset"]').addEventListener('click', () => {
      deInput.value = ''
      ateInput.value = ''
      aplicarPeriodo()
    })

    // ---- período (De–Até): filtra E enquadra o zoom ----
    let periodoDe: Date | null = null
    let periodoAteExclusivo: Date | null = null

    function enquadrarPeriodo() {
      if (comDatas.length === 0) return
      const a = periodoDe ?? dominio[0]
      const b = periodoAteExclusivo ?? dominio[1]
      const x0 = xBase(a), x1 = xBase(b)
      const larguraUtil = W - MARGEM_DIR - MARGEM_ESQ
      const k = Math.min(ZOOM_MAX, Math.max(1, larguraUtil / Math.max(1, x1 - x0)))
      const tx = periodoDe || periodoAteExclusivo ? MARGEM_ESQ - k * x0 : 0
      svg.transition().duration(260).call(zoom.transform, d3.zoomIdentity.translate(tx, 0).scale(k))
    }
    function aplicarPeriodo() {
      const de = parseDataLocal(deInput.value)
      const ate = parseDataLocal(ateInput.value)
      periodoDe = de
      periodoAteExclusivo = ate ? new Date(ate.getTime() + DIA_MS) : null
      if (de && ate && de > ate) { // De > Até: troca, em vez de mostrar tela vazia
        periodoDe = ate
        periodoAteExclusivo = new Date(de.getTime() + DIA_MS)
        deInput.value = ateInput.value
        ateInput.value = iso(de)
      }
      limparPeriodoBtn.style.display = periodoDe || periodoAteExclusivo ? 'inline-flex' : 'none'
      if (fixado) { fixado = false; fixadoIds = null; atualizarBotaoFixar() }
      aplicarFiltro()
      enquadrarPeriodo()
    }
    deInput.addEventListener('change', aplicarPeriodo)
    ateInput.addEventListener('change', aplicarPeriodo)
    limparPeriodoBtn.addEventListener('click', () => { deInput.value = ''; ateInput.value = ''; aplicarPeriodo() })

    // ---- filtros (tipo/busca/advogado/período) + fixar ----
    let fixado = false
    let fixadoIds: Set<string> | null = null
    const nPecasEl = q<HTMLDivElement>('[data-role="nPecas"]')
    const nCitacoesEl = q<HTMLDivElement>('[data-role="nCitacoes"]')

    function passaFiltros(d: NoInterno, termo: string, adv: string): boolean {
      if (!tiposAtivos.has(d.tipo)) return false
      if (termo && !(
        d.titulo.toLowerCase().includes(termo) ||
        (d.autor ?? '').toLowerCase().includes(termo) ||
        (d.advogado_responsavel ?? '').toLowerCase().includes(termo) ||
        (d.id_processual ?? '').includes(termo)
      )) return false
      if (adv === '__sem__' ? !!d.advogado_responsavel : adv && d.advogado_responsavel !== adv) return false
      if (periodoDe || periodoAteExclusivo) {
        if (!d.dt) return false
        if (periodoDe && d.dt < periodoDe) return false
        if (periodoAteExclusivo && d.dt >= periodoAteExclusivo) return false
      }
      return true
    }

    function aplicarFiltro() {
      const termo = buscaInput.value.trim().toLowerCase()
      const adv = advSelect?.value ?? ''
      nosRaiz.forEach((d) => { d.visivel = fixadoIds ? fixadoIds.has(d.id) : passaFiltros(d, termo, adv) })
      nodeSel.style('display', (d) => (d.visivel ? null : 'none'))
      edgeSel.style('display', (d) => (d.source.visivel && d.target.visivel ? null : 'none'))
      nPecasEl.textContent = String(nosRaiz.filter((d) => d.visivel).length)
      nCitacoesEl.textContent = String(links.filter((l) => l.source.visivel && l.target.visivel).length)
    }
    buscaInput.addEventListener('input', aplicarFiltro)
    advSelect?.addEventListener('change', () => {
      if (fixado) { fixado = false; fixadoIds = null; atualizarBotaoFixar() }
      aplicarFiltro()
    })

    // ---- seleção / painel ----
    let selecionadoId: string | null = null

    function vizinhos(id: string): Set<string> {
      const ids = new Set([id])
      links.forEach((l) => {
        if (l.source.id === id) ids.add(l.target.id)
        if (l.target.id === id) ids.add(l.source.id)
      })
      return ids
    }

    function atualizarBotaoFixar() {
      const btn = q<HTMLButtonElement>('[data-role="pFixar"]')
      btn.textContent = fixado ? '📌 Desafixar (ver o grafo todo)' : '📌 Fixar estas conexões'
      btn.classList.toggle(styles.fixBtnActive, fixado)
    }
    q<HTMLButtonElement>('[data-role="pFixar"]').addEventListener('click', () => {
      if (!selecionadoId) return
      if (fixado) { fixado = false; fixadoIds = null }
      else { fixadoIds = vizinhos(selecionadoId); fixado = true }
      atualizarBotaoFixar()
      aplicarFiltro()
    })

    q<HTMLButtonElement>('[data-role="pReler"]').addEventListener('click', async (event) => {
      if (!selecionadoId) return
      const btn = event.currentTarget as HTMLButtonElement
      btn.disabled = true
      btn.textContent = 'Relendo...'
      try {
        await autosIa.relerPeca(selecionadoId)
        onRelidoRef.current?.()
      } catch (err: unknown) {
        const detalhe = (err as { response?: { data?: { detail?: string } }; message?: string })
        alert(`Erro ao reler: ${detalhe?.response?.data?.detail || detalhe?.message}`)
        btn.disabled = false
        btn.textContent = '↻ Reler documento'
      }
    })

    function irPara(id: string) {
      const alvo = byId.get(id)
      if (!alvo) return
      tiposAtivos.add(alvo.tipo)
      const row = legendEl.querySelector<HTMLDivElement>(`[data-tipo="${alvo.tipo}"]`)
      if (row) row.classList.remove(styles.legendOff)
      if (fixado && fixadoIds && !fixadoIds.has(id)) { fixado = false; fixadoIds = null; atualizarBotaoFixar() }
      aplicarFiltro()
      if (!alvo.visivel) {
        // Peça escondida por período/advogado/busca (ex.: clique num ID do índice):
        // limpa esses filtros em vez de abrir o painel de algo que não aparece.
        buscaInput.value = ''
        if (advSelect) advSelect.value = ''
        deInput.value = ''
        ateInput.value = ''
        aplicarPeriodo()
      }
      selecionar(id)
    }

    // Pequena setinha de Drive reaproveitada em qualquer lugar que referencia
    // outra peça (chip de ID mencionado, "Menciona"/"Citada por") — abre o
    // documento direto, sem precisar navegar até lá primeiro. `stopPropagation`
    // via classe própria (ver wiring abaixo) pra não disparar a navegação do
    // item inteiro junto.
    function driveIconHtml(no: NoInterno): string {
      if (!no.arquivo_drive_link) return ''
      return `<a class="${styles.miniDrive}" href="${escapeHtml(no.arquivo_drive_link)}" target="_blank" rel="noreferrer" title="Abrir no Drive" aria-label="Abrir no Drive">↗</a>`
    }

    function chipsDeMencoes(d: NoInterno): string {
      const mencoes = mencoesPorOrigem.get(d.id) ?? []
      if (mencoes.length === 0) return `<div class="${styles.relEmpty}">Nenhum ID mencionado no texto desta peça.</div>`
      return `<div class="${styles.chipWrap}">` + mencoes.map((a) => {
        const destino = a.peca_destino_id ? resolverRaiz(a.peca_destino_id) : null
        if (destino && byId.has(destino)) {
          const alvo = byId.get(destino)!
          return `<span class="${styles.chip} ${styles.chipResolved}" data-goto="${destino}" title="Clique para abrir">${escapeHtml(a.id_mencionado)}${driveIconHtml(alvo)}</span>`
        }
        return `<span class="${styles.chip} ${styles.chipUnresolved}" title="Citado no texto, mas não localizado no acervo">${escapeHtml(a.id_mencionado)} · não localizado</span>`
      }).join('') + '</div>'
    }

    function relItemHtml(m: NoInterno): string {
      return `<div class="${styles.relItem}" data-goto="${m.id}">` +
        `<span class="${styles.relTitle}">${escapeHtml(m.titulo)}</span>` +
        `<span class="${styles.relId}">${escapeHtml(m.id_processual ?? '')}</span>` +
        driveIconHtml(m) +
        '</div>'
    }

    function selecionar(id: string) {
      esconderTooltip()
      selecionadoId = id
      const d = byId.get(id)
      if (!d) return
      const viz = vizinhos(id)
      nodeSel.classed(styles.nodeDim, (n) => !viz.has(n.id))
      nodeSel.classed(styles.nodeHi, (n) => n.id === id)
      edgeSel.classed(styles.edgeDim, (l) => !(l.source.id === id || l.target.id === id))
      edgeSel.classed(styles.edgeHi, (l) => l.source.id === id || l.target.id === id)
      mostrarGuia(d)
      renderizar()

      q<HTMLSpanElement>('[data-role="pTipo"]').textContent = NOME_TIPO[d.tipo]
      q<HTMLSpanElement>('[data-role="pTipo"]').style.background = COR_POR_TIPO[d.tipo]
      const linkDrive = q<HTMLAnchorElement>('[data-role="pDrive"]')
      linkDrive.style.display = d.arquivo_drive_link ? 'inline-flex' : 'none'
      if (d.arquivo_drive_link) linkDrive.href = d.arquivo_drive_link
      q<HTMLHeadingElement>('[data-role="pTitulo"]').textContent = d.titulo
      const paginas = d.pagina_inicio === d.pagina_fim ? `p. ${d.pagina_inicio}` : `p. ${d.pagina_inicio}–${d.pagina_fim}`
      q<HTMLDivElement>('[data-role="pMeta"]').innerHTML =
        `${formatarData(d.data_peca)}${d.autor ? ' · ' + escapeHtml(d.autor) : ''} · ${paginas} · ${d.citacoes}x citada` +
        (d.id_processual ? ` <span class="${styles.ownId}">ID ${escapeHtml(d.id_processual)}</span>` : '') +
        (d.advogado_responsavel ? ` <span class="${styles.advChip}">⚖ ${escapeHtml(d.advogado_responsavel)}</span>` : '')
      q<HTMLDivElement>('[data-role="pIds"]').innerHTML = chipsDeMencoes(d)
      q<HTMLDivElement>('[data-role="pResumo"]').textContent = d.resumo || 'Ainda sem resumo gerado.'
      const naoLida = d.status !== 'resumida' || !!d.erro_mensagem
      const avisoEl = q<HTMLDivElement>('[data-role="pAviso"]')
      avisoEl.style.display = naoLida ? 'block' : 'none'
      avisoEl.textContent = d.erro_mensagem ? `⚠ ${d.erro_mensagem}` : (naoLida ? '⚠ Ainda não lida/resumida.' : '')
      const btnReler = q<HTMLButtonElement>('[data-role="pReler"]')
      btnReler.style.display = naoLida ? 'inline-flex' : 'none'
      btnReler.disabled = false
      btnReler.textContent = '↻ Reler documento'
      atualizarBotaoFixar()

      const mencionaResolvidos = (mencoesPorOrigem.get(id) ?? [])
        .map((a) => a.peca_destino_id ? byId.get(resolverRaiz(a.peca_destino_id)) : undefined)
        .filter((n): n is NoInterno => !!n)
      const mencionaHtml = `<div class="${styles.relLabel}">Menciona (resolvidos)</div>` + (
        mencionaResolvidos.length
          ? mencionaResolvidos.map(relItemHtml).join('')
          : `<div class="${styles.relEmpty}">Nenhuma menção identificada.</div>`
      )
      q<HTMLDivElement>('[data-role="pMenciona"]').innerHTML = mencionaHtml

      const citadaPor = (citadaPorDestino.get(id) ?? []).map((a) => byId.get(a.peca_origem_id)).filter((n): n is NoInterno => !!n)
      const citadaHtml = `<div class="${styles.relLabel}">Citada por</div>` + (
        citadaPor.length
          ? citadaPor.map(relItemHtml).join('')
          : `<div class="${styles.relEmpty}">Ainda não citada por outra peça.</div>`
      )
      q<HTMLDivElement>('[data-role="pCitada"]').innerHTML = citadaHtml

      panel.querySelectorAll<HTMLAnchorElement>(`.${styles.miniDrive}`).forEach((a) => {
        a.addEventListener('click', (ev) => ev.stopPropagation())
      })

      panel.querySelectorAll<HTMLElement>('[data-goto]').forEach((btn) => {
        btn.addEventListener('click', () => irPara(btn.getAttribute('data-goto')!))
        // Passar o mouse já mostra o resumo do documento referenciado — pra
        // conferir do que se trata sem perder o contexto de onde se estava.
        const alvo = byId.get(btn.getAttribute('data-goto')!)
        if (alvo) {
          btn.addEventListener('mousemove', (ev) => mostrarTooltip(ev as MouseEvent, alvo))
          btn.addEventListener('mouseleave', esconderTooltip)
        }
      })

      panel.classList.add(styles.panelOpen)
    }

    q<HTMLButtonElement>('[data-role="panelClose"]').addEventListener('click', () => {
      panel.classList.remove(styles.panelOpen)
      selecionadoId = null
      fixado = false; fixadoIds = null
      nodeSel.classed(styles.nodeDim, false).classed(styles.nodeHi, false)
      edgeSel.classed(styles.edgeDim, false).classed(styles.edgeHi, false)
      aplicarFiltro()
      esconderGuia()
      renderizar()
    })

    // ---- primeira montagem + resize ----
    function montarTudo() {
      calcularLayout()
      configurarZoom()
      desenharFaixas()
      renderizar()
    }
    montarTudo()
    aplicarFiltro()

    let larguraAnterior = scrollArea.clientWidth
    let alturaAnterior = scrollArea.clientHeight
    const resizeObserver = new ResizeObserver(() => {
      const w = scrollArea.clientWidth, h = scrollArea.clientHeight
      if (w <= 0 || h <= 0 || (w === larguraAnterior && h === alturaAnterior)) return
      larguraAnterior = w; alturaAnterior = h
      // O enquadramento é guardado em proporção do domínio, então um resize não "pula" o zoom.
      const antes = xz()
      const [a, b] = [antes.invert(MARGEM_ESQ), antes.invert(W - MARGEM_DIR)]
      montarTudo()
      const x0 = xBase(a), x1 = xBase(b)
      const k = Math.min(ZOOM_MAX, Math.max(1, (W - MARGEM_DIR - MARGEM_ESQ) / Math.max(1, x1 - x0)))
      transformAtual = d3.zoomIdentity.translate(MARGEM_ESQ - k * x0, 0).scale(k)
      svg.call(zoom.transform, transformAtual)
    })
    resizeObserver.observe(canvasWrap)

    return () => {
      resizeObserver.disconnect()
      root.innerHTML = ''
    }
  }, [nos, arestas])

  const temPecaRaiz = nos.some((n) => !n.peca_pai_id)
  if (!temPecaRaiz) {
    return <p className={styles.vazio}>Nenhuma peça indexada ainda.</p>
  }

  return <div ref={rootRef} />
}
