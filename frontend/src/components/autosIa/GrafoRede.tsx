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

interface NoInterno extends GrafoNo, d3.SimulationNodeDatum {
  citacoes: number
  dt: Date | null
}
interface LinkInterno extends d3.SimulationLinkDatum<NoInterno> {
  id: string
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

/** Grafo de nós conectados: cada peça-mãe é um ponto, dimensionado por quantas
 * vezes é citada, colorido por tipo. Clique isola a vizinhança e abre o painel
 * de detalhe com os IDs mencionados (resolvidos e "não localizados"); "Fixar"
 * trava a vizinhança atual pra navegar só entre aqueles documentos. Tudo é
 * construído imperativamente com D3 dentro de `rootRef` — o layout de força e
 * o zoom/pan não convivem bem com o ciclo de re-render do React. */
export default function GrafoRede({ nos, arestas, onRelido }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const onRelidoRef = useRef(onRelido)
  useEffect(() => { onRelidoRef.current = onRelido }, [onRelido])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return

    const nosRaiz: NoInterno[] = nos
      .filter((n) => !n.peca_pai_id)
      .map((n) => ({ ...n, citacoes: 0, dt: parseDataLocal(n.data_peca) }))
    if (nosRaiz.length === 0) return

    const byId = new Map<string, NoInterno>()
    nosRaiz.forEach((n) => byId.set(n.id, n))

    const idpIndex = new Map<string, string>()
    nosRaiz.forEach((n) => { if (n.id_processual) idpIndex.set(n.id_processual, n.id) })

    const mencoesPorOrigem = new Map<string, GrafoAresta[]>()
    arestas.forEach((a) => {
      if (!byId.has(a.peca_origem_id)) return
      const lista = mencoesPorOrigem.get(a.peca_origem_id) ?? []
      lista.push(a)
      mencoesPorOrigem.set(a.peca_origem_id, lista)
    })

    const links: LinkInterno[] = arestas
      .filter((a) => a.peca_destino_id && byId.has(a.peca_origem_id) && byId.has(a.peca_destino_id))
      .map((a) => ({ id: a.id, source: a.peca_origem_id, target: a.peca_destino_id! }))
    links.forEach((l) => {
      const alvo = byId.get(l.target as string)
      if (alvo) alvo.citacoes += 1
    })

    const citadaPorDestino = new Map<string, GrafoAresta[]>()
    arestas.forEach((a) => {
      if (!a.peca_destino_id || !byId.has(a.peca_destino_id) || !byId.has(a.peca_origem_id)) return
      const lista = citadaPorDestino.get(a.peca_destino_id) ?? []
      lista.push(a)
      citadaPorDestino.set(a.peca_destino_id, lista)
    })

    const tiposPresentes = Array.from(new Set(nosRaiz.map((n) => n.tipo)))
    let tiposAtivos = new Set(tiposPresentes)

    // ---- monta a casca de DOM (sidebar, canvas, painel, tooltip) ----
    root.innerHTML = `
      <div class="${styles.wrap}">
        <aside class="${styles.aside}">
          <div>
            <span class="${styles.fieldLabel}">Busca</span>
            <input type="search" class="${styles.searchInput}" placeholder="Título, ID, autor..." autocomplete="off" />
          </div>
          <div class="${styles.statsGrid}">
            <div class="${styles.stat}"><div class="${styles.statN}">${nosRaiz.length}</div><div class="${styles.statL}">peças</div></div>
            <div class="${styles.stat}"><div class="${styles.statN}">${links.length}</div><div class="${styles.statL}">citações</div></div>
          </div>
          <div>
            <span class="${styles.fieldLabel}">Tipos (clique filtra · "só" isola)</span>
            <div class="${styles.legend}" data-role="legend"></div>
          </div>
          <details class="${styles.idxWrap}">
            <summary>Índice de IDs</summary>
            <div class="${styles.idIndex}" data-role="idindex"></div>
          </details>
          <div class="${styles.hint}">
            <strong>Como ler:</strong> a posição horizontal segue a data (mais antiga à esquerda, eixo no
            rodapé) — mesmo sem citação identificada, a ordem cronológica já mostra o que veio antes. O
            tamanho do ponto cresce com quantas vezes a peça é citada; as linhas mostram quem menciona quem.
            Clique num ponto pra ver o resumo e isolar suas conexões; arraste o fundo pra mover, role pra
            dar zoom.
          </div>
        </aside>
        <main class="${styles.canvasWrap}">
          <svg class="${styles.graphSvg}"></svg>
          <div class="${styles.zoomControls}">
            <button type="button" class="${styles.zoomBtn}" data-role="zoomIn" aria-label="Mais zoom">+</button>
            <button type="button" class="${styles.zoomBtn}" data-role="zoomOut" aria-label="Menos zoom">−</button>
            <button type="button" class="${styles.zoomBtn}" data-role="zoomReset" aria-label="Resetar zoom">⤢</button>
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
    const panel = q<HTMLDivElement>('[data-role="panel"]')
    const tooltip = q<HTMLDivElement>('[data-role="tooltip"]')
    const buscaInput = q<HTMLInputElement>(`.${styles.searchInput}`)

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
    idIndexEl.innerHTML = idxHtml || `<p class="${styles.relEmpty}">Nenhuma peça com ID processual neste caso.</p>`
    idIndexEl.querySelectorAll<HTMLDivElement>(`.${styles.idxItem}`).forEach((el) => {
      const n = byId.get(el.getAttribute('data-id')!)
      if (!n) return
      el.addEventListener('mousemove', (ev) => mostrarTooltip(ev, n))
      el.addEventListener('mouseleave', esconderTooltip)
      el.addEventListener('click', () => irPara(n.id))
    })

    // ---- SVG + força ----
    const width = canvasWrap.clientWidth || 600
    const height = canvasWrap.clientHeight || 460
    const svg = d3.select(q<SVGSVGElement>('svg'))
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

    const zoomLayer = svg.append('g')
    const axisLayer = zoomLayer.append('g')
    const edgeLayer = zoomLayer.append('g')
    const nodeLayer = zoomLayer.append('g')

    const radius = d3.scaleSqrt()
      .domain([0, d3.max(nosRaiz, (n) => n.citacoes) || 1])
      .range([5, 15])

    // Eixo cronológico: puxa cada nó horizontalmente pra posição proporcional à
    // data da peça (mais antiga à esquerda), respondendo ao pedido de dar uma
    // sequência temporal legível ao grafo — sem isso ele é só nuvem de pontos
    // sem noção de "o que veio antes de quê". Força moderada (não trava): o
    // link/charge/collide ainda podem organizar verticalmente por citação.
    const comData = nosRaiz.filter((n) => n.dt)
    const temEixoTempo = comData.length >= 2
    const AXIS_Y = height - 34
    const xScale = temEixoTempo
      ? d3.scaleTime()
        .domain(d3.extent(comData, (n) => n.dt as Date) as [Date, Date])
        .range([64, Math.max(64 + 40, width - 24)])
        .nice()
      : null

    const sim = d3.forceSimulation<NoInterno>(nosRaiz)
      .force('link', d3.forceLink<NoInterno, LinkInterno>(links).id((d) => d.id).distance(70).strength(0.35))
      .force('charge', d3.forceManyBody().strength(-140))
      .force('collide', d3.forceCollide<NoInterno>().radius((d) => radius(d.citacoes) + 14))
    if (xScale) {
      sim
        .force('x', d3.forceX<NoInterno>((d) => (d.dt ? xScale(d.dt) : width / 2)).strength(0.22))
        .force('y', d3.forceY<NoInterno>(height / 2 - 14).strength(0.05))
    } else {
      sim.force('center', d3.forceCenter(width / 2, height / 2))
    }

    if (xScale) {
      axisLayer.attr('class', styles.axisEixo).attr('transform', `translate(0,${AXIS_Y})`)
      axisLayer.call(
        d3.axisBottom(xScale)
          .ticks(Math.min(8, comData.length))
          .tickFormat((d) => (d as Date).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })) as unknown as (sel: typeof axisLayer) => void,
      )
    }

    const edgeSel = edgeLayer.selectAll('path').data(links).enter().append('path')
      .attr('class', styles.edge)
      .attr('marker-end', (d) => {
        const alvo = typeof d.target === 'object' ? d.target : byId.get(d.target as string)
        return `url(#arrow-${alvo?.tipo ?? 'outro'})`
      })

    const nodeSel = nodeLayer.selectAll('g').data(nosRaiz).enter().append('g')
      .attr('class', styles.node)
      .call(d3.drag<SVGGElement, NoInterno>()
        .on('start', (event, d) => { if (!event.active) sim.alphaTarget(0.25).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null }))

    nodeSel.append('circle')
      .attr('r', (d) => radius(d.citacoes))
      .attr('fill', (d) => COR_POR_TIPO[d.tipo])

    nodeSel.append('text')
      .attr('class', styles.nodeText)
      .attr('dy', (d) => radius(d.citacoes) + 11)
      .attr('text-anchor', 'middle')
      .text((d) => (d.titulo.length > 26 ? d.titulo.slice(0, 26) + '…' : d.titulo))

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
      tooltip.innerHTML = `<div class="${styles.ttTipo}" style="color:${COR_POR_TIPO[d.tipo]}">${NOME_TIPO[d.tipo]}${d.id_processual ? ' · ID ' + escapeHtml(d.id_processual) : ''}</div>` +
        `<strong>${escapeHtml(d.titulo)}</strong><br>${formatarData(d.data_peca)}${d.autor ? ' · ' + escapeHtml(d.autor) : ''}` +
        (d.citacoes ? `<br>citada ${d.citacoes}x` : '') + resumoTrecho + kwTrecho
    }
    function esconderTooltip() { tooltip.style.opacity = '0' }

    nodeSel
      .on('mousemove', (event, d) => mostrarTooltip(event, d))
      .on('mouseleave', esconderTooltip)
      .on('click', (_event, d) => { esconderTooltip(); irPara(d.id) })

    sim.on('tick', () => {
      edgeSel.attr('d', (d) => {
        const s = d.source as NoInterno, t = d.target as NoInterno
        const dx = (t.x ?? 0) - (s.x ?? 0), dy = (t.y ?? 0) - (s.y ?? 0)
        const dr = Math.sqrt(dx * dx + dy * dy) * 1.4
        return `M${s.x},${s.y}A${dr},${dr} 0 0,1 ${t.x},${t.y}`
      })
      nodeSel.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

    const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.3, 4]).on('zoom', (event) => {
      zoomLayer.attr('transform', event.transform)
    })
    svg.call(zoom)
    q<HTMLButtonElement>('[data-role="zoomIn"]').addEventListener('click', () => svg.transition().call(zoom.scaleBy, 1.3))
    q<HTMLButtonElement>('[data-role="zoomOut"]').addEventListener('click', () => svg.transition().call(zoom.scaleBy, 1 / 1.3))
    q<HTMLButtonElement>('[data-role="zoomReset"]').addEventListener('click', () => svg.transition().call(zoom.transform, d3.zoomIdentity))

    // ---- filtro (tipo/busca) + fixar ----
    let fixado = false
    let fixadoIds: Set<string> | null = null

    function aplicarFiltro() {
      const termo = buscaInput.value.trim().toLowerCase()
      nodeSel.style('display', (d) => {
        if (fixadoIds) return fixadoIds.has(d.id) ? null : 'none'
        const passaTipo = tiposAtivos.has(d.tipo)
        const passaBusca = !termo ||
          d.titulo.toLowerCase().includes(termo) ||
          (d.autor ?? '').toLowerCase().includes(termo) ||
          (d.id_processual ?? '').includes(termo)
        return passaTipo && passaBusca ? null : 'none'
      })
      edgeSel.style('display', (d) => {
        const s = typeof d.source === 'object' ? d.source : byId.get(d.source as string)!
        const t = typeof d.target === 'object' ? d.target : byId.get(d.target as string)!
        if (fixadoIds) return fixadoIds.has(s.id) && fixadoIds.has(t.id) ? null : 'none'
        return tiposAtivos.has(s.tipo) && tiposAtivos.has(t.tipo) ? null : 'none'
      })
    }
    buscaInput.addEventListener('input', aplicarFiltro)

    // ---- seleção / painel ----
    let selecionadoId: string | null = null

    function vizinhos(id: string): Set<string> {
      const ids = new Set([id])
      links.forEach((l) => {
        const s = typeof l.source === 'object' ? l.source.id : l.source
        const t = typeof l.target === 'object' ? l.target.id : l.target
        if (s === id) ids.add(t as string)
        if (t === id) ids.add(s as string)
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
        if (a.peca_destino_id && byId.has(a.peca_destino_id)) {
          const alvo = byId.get(a.peca_destino_id)!
          return `<span class="${styles.chip} ${styles.chipResolved}" data-goto="${a.peca_destino_id}" title="Clique para abrir">${escapeHtml(a.id_mencionado)}${driveIconHtml(alvo)}</span>`
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
      edgeSel.classed(styles.edgeDim, (l) => {
        const s = typeof l.source === 'object' ? l.source.id : l.source
        const t = typeof l.target === 'object' ? l.target.id : l.target
        return !(s === id || t === id)
      })
      edgeSel.classed(styles.edgeHi, (l) => {
        const s = typeof l.source === 'object' ? l.source.id : l.source
        const t = typeof l.target === 'object' ? l.target.id : l.target
        return s === id || t === id
      })

      q<HTMLSpanElement>('[data-role="pTipo"]').textContent = NOME_TIPO[d.tipo]
      q<HTMLSpanElement>('[data-role="pTipo"]').style.background = COR_POR_TIPO[d.tipo]
      const linkDrive = q<HTMLAnchorElement>('[data-role="pDrive"]')
      linkDrive.style.display = d.arquivo_drive_link ? 'inline-flex' : 'none'
      if (d.arquivo_drive_link) linkDrive.href = d.arquivo_drive_link
      q<HTMLHeadingElement>('[data-role="pTitulo"]').textContent = d.titulo
      const paginas = d.pagina_inicio === d.pagina_fim ? `p. ${d.pagina_inicio}` : `p. ${d.pagina_inicio}–${d.pagina_fim}`
      q<HTMLDivElement>('[data-role="pMeta"]').innerHTML =
        `${formatarData(d.data_peca)}${d.autor ? ' · ' + escapeHtml(d.autor) : ''} · ${paginas} · ${d.citacoes}x citada` +
        (d.id_processual ? ` <span class="${styles.ownId}">ID ${escapeHtml(d.id_processual)}</span>` : '')
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
        .filter((a) => a.peca_destino_id && byId.has(a.peca_destino_id))
        .map((a) => byId.get(a.peca_destino_id!)!)
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
    })

    const resizeObserver = new ResizeObserver(() => {
      const w = canvasWrap.clientWidth, h = canvasWrap.clientHeight
      if (w <= 0 || h <= 0) return
      if (xScale) {
        xScale.range([64, Math.max(64 + 40, w - 24)])
        axisLayer.attr('transform', `translate(0,${h - 34})`)
        sim.force('y', d3.forceY<NoInterno>(h / 2 - 14).strength(0.05))
      } else {
        sim.force('center', d3.forceCenter(w / 2, h / 2))
      }
      sim.alpha(0.3).restart()
    })
    resizeObserver.observe(canvasWrap)

    return () => {
      resizeObserver.disconnect()
      sim.stop()
      root.innerHTML = ''
    }
  }, [nos, arestas])

  const temPecaRaiz = nos.some((n) => !n.peca_pai_id)
  if (!temPecaRaiz) {
    return <p className={styles.vazio}>Nenhuma peça indexada ainda.</p>
  }

  return <div ref={rootRef} />
}
