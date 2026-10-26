import { useState } from 'react'
import type { FiltrosCreditos, OpcoesCreditos } from '../../../api/estrutura'
import { etiquetasFiltros, removerFiltro } from './util'
import styles from './Estrutura.module.css'

function Multi({ rotulo, opcoes, valor, onChange, busca = false }: {
  rotulo: string; opcoes: { chave: string; rotulo: string }[]; valor: string[]; onChange: (v: string[]) => void; busca?: boolean
}) {
  const [q, setQ] = useState('')
  const visiveis = opcoes.filter((o) => !q || o.rotulo.toLowerCase().includes(q.toLowerCase()) || o.chave.includes(q))
  const alterna = (c: string) => onChange(valor.includes(c) ? valor.filter((x) => x !== c) : [...valor, c])
  return (
    <div className={styles.campo}>{rotulo}
      <details className={styles.multi}>
        <summary aria-label={rotulo}><span>{valor.length ? `${valor.length} selecionado(s)` : 'Todas'}</span><span>▾</span></summary>
        <div className={styles.multiLista}>
          {busca && <input type="search" placeholder="Filtrar a lista…" value={q} onChange={(e) => setQ(e.target.value)} aria-label={`Filtrar ${rotulo}`} />}
          {visiveis.slice(0, 300).map((o) => (
            <label key={o.chave}><input type="checkbox" checked={valor.includes(o.chave)} onChange={() => alterna(o.chave)} />{o.rotulo}</label>
          ))}
          {visiveis.length > 300 && <span className={styles.dica}>Mostrando 300 de {visiveis.length} — refine a busca.</span>}
          {visiveis.length === 0 && <span className={styles.dica}>Nada encontrado.</span>}
        </div>
      </details>
    </div>
  )
}

const tri = (v: boolean | undefined) => (v === undefined ? '' : v ? 'sim' : 'nao')
const deTri = (s: string) => (s === '' ? undefined : s === 'sim')

export default function FiltrosPainel({ f, setF, opcoes, total }: { f: FiltrosCreditos; setF: (f: FiltrosCreditos) => void; opcoes: OpcoesCreditos | undefined; total?: string }) {
  const nomeDev = (c: string) => opcoes?.devedoras.find((d) => d.chave === c)?.rotulo ?? c
  const nomeCre = (c: string) => opcoes?.credores.find((d) => d.chave === c)?.rotulo ?? c
  const etiquetas = etiquetasFiltros(f, nomeDev, nomeCre)
  const set = (p: Partial<FiltrosCreditos>) => {
    const n: any = { ...f, ...p }
    for (const k of Object.keys(n)) if (n[k] === undefined || n[k] === '' || (Array.isArray(n[k]) && n[k].length === 0)) delete n[k]
    setF(n)
  }
  const [aberto, setAberto] = useState(true)
  const reais = (s: string) => { const n = Number(s.replace(/\./g, '').replace(',', '.')); return s.trim() === '' || !Number.isFinite(n) ? undefined : n }
  return (
    <div className={styles.painel} aria-label="Filtros">
      <div className={styles.painelTopo}>
        <strong style={{ fontSize: 13 }}>Filtros</strong>
        <button className={styles.link} onClick={() => setAberto((v) => !v)}>{aberto ? 'recolher' : 'expandir'}</button>
        {etiquetas.length > 0 && <button className={styles.miniLink} onClick={() => setF({ lote: f.lote })}>limpar tudo</button>}
        {total && <span className={styles.dica} style={{ marginLeft: 'auto' }}>{total}</span>}
      </div>
      {etiquetas.length > 0 && (
        <div className={styles.etiquetas}>
          {etiquetas.map((e, i) => (
            <span key={`${e.chave}${e.valor ?? ''}${i}`} className={styles.etiqueta}>{e.rotulo}
              <button aria-label={`Remover filtro ${e.rotulo}`} onClick={() => setF(removerFiltro(f, e.chave, e.valor))}>×</button></span>
          ))}
        </div>
      )}
      {aberto && (
        <div className={styles.grade}>
          <Multi rotulo="Categoria da dívida" opcoes={(opcoes?.categorias ?? []).map((c) => ({ chave: c, rotulo: c }))} valor={f.categoria ?? []} onChange={(v) => set({ categoria: v })} />
          <Multi rotulo="Subcategoria" opcoes={(opcoes?.subcategorias ?? []).map((c) => ({ chave: c, rotulo: c }))} valor={f.subcategoria ?? []} onChange={(v) => set({ subcategoria: v })} busca />
          <Multi rotulo="Classe" opcoes={(opcoes?.classes ?? []).map((c) => ({ chave: c, rotulo: c }))} valor={f.classe ?? []} onChange={(v) => set({ classe: v })} />
          <Multi rotulo="Empresa devedora" opcoes={opcoes?.devedoras ?? []} valor={f.devedor ?? []} onChange={(v) => set({ devedor: v })} busca />
          <Multi rotulo="Nível da devedora" opcoes={(opcoes?.niveis ?? []).map((c) => ({ chave: c, rotulo: c }))} valor={f.nivel_devedor ?? []} onChange={(v) => set({ nivel_devedor: v })} />
          <Multi rotulo="Credor (lista)" opcoes={opcoes?.credores ?? []} valor={f.credor ?? []} onChange={(v) => set({ credor: v })} busca />
          <label className={styles.campo}>Credor contém (nome ou CNPJ)<input value={f.credor_q ?? ''} onChange={(e) => set({ credor_q: e.target.value })} placeholder="ex.: rhino, 36.519.605" /></label>
          <label className={styles.campo}>Natureza contém<input value={f.natureza_q ?? ''} onChange={(e) => set({ natureza_q: e.target.value })} placeholder="ex.: earn-out, CCB" /></label>
          <label className={styles.campo}>Busca livre<input value={f.q ?? ''} onChange={(e) => set({ q: e.target.value })} placeholder="devedora, credor, natureza, fiador…" /></label>
          <label className={styles.campo}>Origem do credor
            <select value={tri(f.intragrupo)} onChange={(e) => set({ intragrupo: deTri(e.target.value) })} aria-label="Origem do credor">
              <option value="">Todos</option><option value="sim">Intragrupo (credor é empresa do grupo)</option><option value="nao">Externo</option></select></label>
          <label className={styles.campo}>Vencimento
            <select value={tri(f.vencidos)} onChange={(e) => set({ vencidos: deTri(e.target.value) })} aria-label="Situação do vencimento">
              <option value="">Todos</option><option value="sim">Vencidos</option><option value="nao">A vencer / sem data</option></select></label>
          <label className={styles.campo}>Coobrigado / fiador
            <select value={tri(f.com_coobrigado)} onChange={(e) => set({ com_coobrigado: deTri(e.target.value) })} aria-label="Coobrigado">
              <option value="">Todos</option><option value="sim">Com coobrigado</option><option value="nao">Sem</option></select></label>
          <label className={styles.campo}>Devedora no organograma
            <select value={tri(f.no_organograma)} onChange={(e) => set({ no_organograma: deTri(e.target.value) })} aria-label="Devedora no organograma">
              <option value="">Todas</option><option value="sim">Sim</option><option value="nao">Fora do organograma</option></select></label>
          <label className={styles.campo}>Valor mínimo (R$)<input inputMode="decimal" defaultValue={f.valor_min ?? ''} key={`min${f.valor_min ?? ''}`} onBlur={(e) => set({ valor_min: reais(e.target.value) })} placeholder="0" aria-label="Valor mínimo" /></label>
          <label className={styles.campo}>Valor máximo (R$)<input inputMode="decimal" defaultValue={f.valor_max ?? ''} key={`max${f.valor_max ?? ''}`} onBlur={(e) => set({ valor_max: reais(e.target.value) })} placeholder="sem limite" aria-label="Valor máximo" /></label>
          <label className={styles.campo}>Vence a partir de<input type="date" value={f.venc_de ?? ''} onChange={(e) => set({ venc_de: e.target.value || undefined })} aria-label="Vence a partir de" /></label>
          <label className={styles.campo}>Vence até<input type="date" value={f.venc_ate ?? ''} onChange={(e) => set({ venc_ate: e.target.value || undefined })} aria-label="Vence até" /></label>
        </div>
      )}
    </div>
  )
}
