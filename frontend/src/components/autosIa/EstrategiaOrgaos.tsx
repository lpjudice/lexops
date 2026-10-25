import { useQuery } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import { Id } from './EstrategiaAdvogados'
import styles from './Estrategia.module.css'

const dataBr = (d: string | null) => (d ? d.split('-').reverse().join('/') : '—')
const TOM: Record<string, string> = { favoravel: 'pFav', contraria: 'pCon', condicionada: 'pCond', neutra: 'pNeu' }
const STATUS_ROTULO: Record<string, string> = {
  cumprida: 'Cumprida', parcial: 'Em parte', nao_localizada: 'Não localizada', em_prazo: 'Em prazo', prejudicada: 'Prejudicada',
  nao_aplicavel: 'Sem ato a verificar', vencida_sem_cumprimento: 'Vencida sem cumprimento', nao_avaliada: 'Não avaliada',
}

export default function EstrategiaOrgaos({ casoId }: { casoId: string }) {
  const q = useQuery({ queryKey: ['autos-ia', 'perfil-orgaos', casoId], queryFn: () => autosIa.perfilOrgaos(casoId), staleTime: 30_000 })
  if (q.isLoading) return <p className={styles.vazio}>Carregando…</p>
  return (
    <div className={styles.wrap}>
      <p className={styles.explica}>
        Como cada órgão atuou no processo: peças, o que determinou, os números que afirmou e as posições que assumiu (as posições e as ordens dependem de terem sido lidas nas abas "Posições" e "Cumprimento").
      </p>
      <div className={styles.orgaosGrade}>
        {q.data?.orgaos.map((o) => (
          <section key={o.chave} className={styles.orgao} aria-label={o.rotulo}>
            <h3>{o.rotulo}</h3>
            <div className={styles.dica}>{o.n_pecas} peça(s){o.primeira ? ` · de ${dataBr(o.primeira)} a ${dataBr(o.ultima)}` : ''}</div>
            {o.tipos.length > 0 && <div className={styles.chips}>{o.tipos.map((t) => <span key={t.tipo} className={styles.chip}>{t.tipo} · {t.n}</span>)}</div>}

            {o.ordens && (
              <div className={styles.bloco}>
                <h4>Ordens</h4>
                {o.ordens.total === 0 ? <span className={styles.dica}>Nenhuma ordem lida (aba Cumprimento).</span> : (
                  <>
                    <div className={styles.dica}>{o.ordens.total} ordem(ns) em {o.ordens.decisoes} decisão(ões) · prazo médio {o.ordens.prazo_medio_dias != null ? `${o.ordens.prazo_medio_dias.toLocaleString('pt-BR')} dias` : '—'} ({o.ordens.com_prazo} com prazo) · {o.ordens.ligadas_a_mediacao} ligada(s) à mediação · {o.ordens.com_sancao} com sanção</div>
                    <div className={styles.chips}>{o.ordens.por_destinatario.map((d) => <span key={d.destinatario} className={styles.chip}>{d.destinatario} · {d.n}</span>)}</div>
                    <div className={styles.chips}>{Object.entries(o.ordens.por_status).map(([k, n]) => <span key={k} className={`${styles.pBadge} ${styles[k === 'vencida_sem_cumprimento' ? 'pCon' : k === 'cumprida' ? 'pFav' : k === 'em_prazo' ? 'pNeu' : 'pCond']}`}>{STATUS_ROTULO[k] ?? k} · {n}</span>)}</div>
                  </>
                )}
              </div>
            )}

            <div className={styles.bloco}>
              <h4>Posições</h4>
              {o.posicoes.length === 0 ? <span className={styles.dica}>Nenhuma posição lida ainda.</span> : o.posicoes.map((p) => (
                <div key={p.tema} className={styles.linhaTopo}>
                  <span className={`${styles.pBadge} ${styles[TOM[p.atual]]}`}>{p.atual_rotulo}{p.mudou ? ' ↯' : ''}</span>
                  <span className={styles.nome}>{p.tema_rotulo}</span>
                  <Id p={p.ultima.peticao} />
                  <span className={styles.pResumo}>{p.ultima.resumo}</span>
                </div>
              ))}
            </div>

            <div className={styles.bloco}>
              <h4>Números que afirmou ({o.valores.n})</h4>
              {o.valores.principais.length === 0 ? <span className={styles.dica}>Nenhum valor.</span> : o.valores.principais.map((v) => (
                <div key={v.id} className={styles.linhaTopo}>
                  <span className={styles.valor}>{v.valor}</span><span className={styles.chip}>{v.tema_rotulo}</span>
                  <span className={styles.dica}>{v.sujeito_canonico ?? ''}</span><Id p={v.peticao} />
                </div>
              ))}
            </div>

            <div className={styles.bloco}>
              <h4>Peças recentes</h4>
              <div className={styles.chips}>{o.recentes.map((p) => <span key={p.peca_id} title={`${p.tipo_pje} · ${dataBr(p.data)}`}><Id p={{ peca_id: p.peca_id, id_processual: p.id_processual, data: p.data, titulo: p.titulo ?? '', link_pdf: p.link_pdf, link_md: p.link_md }} /></span>)}</div>
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
