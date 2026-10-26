import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { estrutura } from '../../../api/estrutura'
import type { FiltrosCreditos } from '../../../api/estrutura'
import { baixarCsv, brl, dataBr } from './util'
import styles from './Estrutura.module.css'

const POR_PAGINA = 100
const COLS: { k: string; r: string; ordem?: string; num?: boolean }[] = [
  { k: 'devedora', r: 'Devedora', ordem: 'devedora' }, { k: 'credor', r: 'Credor', ordem: 'credor' }, { k: 'cat', r: 'Categoria / natureza', ordem: 'categoria' },
  { k: 'classe', r: 'Classe' }, { k: 'valor', r: 'Valor', ordem: 'valor', num: true }, { k: 'venc', r: 'Vencimento', ordem: 'vencimento' }, { k: 'pag', r: 'Pág. PDF' },
]

export default function TabelaCreditos({ casoId, f }: { casoId: string; f: FiltrosCreditos }) {
  const [ordem, setOrdem] = useState('-valor')
  const [pagina, setPagina] = useState(0)
  const [aberta, setAberta] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['estrutura', 'creditos', casoId, f, ordem, pagina], queryFn: () => estrutura.creditos(casoId, f, { ordem, limite: POR_PAGINA, offset: pagina * POR_PAGINA }), placeholderData: (p) => p })
  const d = q.data
  const alterna = (o: string) => { setPagina(0); setOrdem(ordem === o ? `-${o}` : ordem === `-${o}` ? o : o === 'valor' ? `-${o}` : o) }
  const seta = (o?: string) => (!o ? '' : ordem === o ? ' ▲' : ordem === `-${o}` ? ' ▼' : '')
  const exportar = async () => {
    const tudo = await estrutura.creditos(casoId, f, { ordem, limite: 5000 })
    baixarCsv('creditos.csv', [
      ['Linha', 'CNPJ devedora', 'Devedora', 'Nível da devedora', 'CNPJ credor', 'Credor', 'Intragrupo', 'Categoria', 'Subcategoria', 'Natureza', 'Classe', 'Valor (R$)', 'Data-base', 'Vencimento', 'Coobrigados/fiadores', 'Página do PDF'],
      ...tudo.itens.map((i) => [i.linha, i.devedor_cnpj_fmt, i.devedor, i.nivel_devedor, i.credor_cnpj_fmt, i.credor, i.intragrupo ? 'Sim' : 'Não', i.categoria, i.subcategoria, i.natureza, i.classe,
        (i.valor_centavos / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, useGrouping: false }), i.data_base, i.vencimento, i.coobrigados, i.pagina_pdf]),
    ])
  }
  if (!d) return <p className={styles.vazio}>{q.isLoading ? 'Carregando…' : 'Sem dados.'}</p>
  const paginas = Math.max(1, Math.ceil(d.total / POR_PAGINA))
  return (
    <div className={styles.wrap}>
      <div className={styles.barra}>
        <span className={styles.dica}><strong>{d.total.toLocaleString('pt-BR')}</strong> linha(s) · total <strong>{brl(d.total_centavos)}</strong></span>
        <button className={styles.btnSec} onClick={exportar} disabled={d.total === 0}>Exportar CSV ({Math.min(d.total, 5000).toLocaleString('pt-BR')} linhas)</button>
        <span className={styles.pag} style={{ marginLeft: 'auto' }}>
          <button className={styles.link} disabled={pagina === 0} onClick={() => setPagina(pagina - 1)}>‹ anterior</button>
          <span className={styles.dica}>página {pagina + 1} de {paginas}</span>
          <button className={styles.link} disabled={pagina + 1 >= paginas} onClick={() => setPagina(pagina + 1)}>próxima ›</button>
        </span>
      </div>
      <div className={styles.tabelaWrap}>
        <table className={styles.tabela}>
          <thead><tr>{COLS.map((c) => <th key={c.k} className={c.num ? styles.num : ''}>{c.ordem ? <button onClick={() => alterna(c.ordem!)}>{c.r}{seta(c.ordem)}</button> : c.r}</th>)}</tr></thead>
          <tbody>
            {d.itens.map((i) => (
              <Fragment key={i.id}>
                <tr className={styles.clicavel} onClick={() => setAberta(aberta === i.id ? null : i.id)} aria-expanded={aberta === i.id}>
                  <td>{i.devedor}{!i.devedor_no_organograma && <> <span className={styles.tagFora} title="Devedora que não consta do organograma">fora do organograma</span></>}</td>
                  <td>{i.credor}{i.intragrupo && <> <span className={styles.tagIntra} title="O credor é empresa do grupo">intragrupo</span></>}</td>
                  <td>{i.categoria}{i.subcategoria ? ` · ${i.subcategoria}` : ''}</td>
                  <td>{i.classe ?? '—'}</td>
                  <td className={styles.num}>{i.valor}</td>
                  <td>{dataBr(i.vencimento)}{i.vencido && <> <span className={styles.tagVenc}>vencido</span></>}</td>
                  <td>{i.pagina_pdf ?? '—'}</td>
                </tr>
                {aberta === i.id && (
                  <tr className={styles.detalheLinha}><td colSpan={COLS.length}>
                    <div><strong>Natureza:</strong> {i.natureza ?? '—'}</div>
                    <div><strong>Devedora:</strong> {i.devedor_cnpj_fmt ?? '—'}{i.nivel_devedor ? ` · ${i.nivel_devedor}` : ''} &nbsp; <strong>Credor:</strong> {i.credor_cnpj_fmt ?? 'sem CNPJ'}{i.credor_email ? ` · ${i.credor_email}` : ''}</div>
                    {i.credor_endereco && <div><strong>Endereço do credor:</strong> {i.credor_endereco}</div>}
                    <div><strong>Data-base:</strong> {dataBr(i.data_base)} &nbsp; <strong>Linha da planilha:</strong> {i.linha ?? '—'}</div>
                    {i.coobrigados && <div><strong>Coobrigados/fiadores:</strong> {i.coobrigados}</div>}
                  </td></tr>
                )}
              </Fragment>
            ))}
            {d.itens.length === 0 && <tr><td colSpan={COLS.length} className={styles.vazio}>Nenhuma linha com esses filtros.</td></tr>}
          </tbody>
          <tfoot><tr><td colSpan={4}>Total do filtro</td><td className={styles.num}>{brl(d.total_centavos)}</td><td colSpan={2} /></tr></tfoot>
        </table>
      </div>
    </div>
  )
}
