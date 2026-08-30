import { useEffect, useState } from 'react'
import { useCatalogoPrazos } from '../api/prazosLegais'
import type { PrazoLegal } from '../api/prazosLegais'
import s from './LegendaPrazos.module.css'

/** Chip "Prazos da lei" + modal de consulta.
 *
 * Usado nos três menus onde se lança prazo (Prazos, Diário Oficial e Recorte
 * Digital). É material de CONFERÊNCIA: o objetivo é o Lucas bater o prazo que
 * está prestes a lançar contra o artigo, antes de errar a data.
 *
 * Lê o mesmo catálogo que alimenta a sugestão automática do formulário — se as
 * duas fontes divergissem, a legenda passaria a induzir ao erro em vez de
 * evitá-lo.
 */
export default function LegendaPrazos({ compacto = false }: { compacto?: boolean }) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const { data, isLoading, isError } = useCatalogoPrazos()

  // Esc fecha — modal sem saída por teclado é armadilha de acessibilidade.
  useEffect(() => {
    if (!aberto) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setAberto(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [aberto])

  const filtra = (lista: PrazoLegal[]) => {
    const q = busca.trim().toLowerCase()
    if (!q) return lista
    return lista.filter((p) =>
      `${p.rotulo} ${p.fundamento} ${p.observacao ?? ''}`.toLowerCase().includes(q),
    )
  }

  const linha = (p: PrazoLegal) => (
    <div key={p.chave} className={s.item}>
      <div className={s.itemHead}>
        <span className={s.itemRotulo}>{p.rotulo}</span>
        <span className={p.dias == null ? s.badgeSemPrazo : s.badgeDias}>
          {p.dias == null
            ? 'sem prazo em dias'
            : `${p.dias} ${p.contagem === 'corridos' ? 'corridos' : 'úteis'}`}
        </span>
      </div>
      <div className={s.fundamento}>{p.fundamento}</div>
      {p.observacao && <div className={s.observacao}>{p.observacao}</div>}
    </div>
  )

  const secao = (titulo: string, lista: PrazoLegal[], subtitulo?: string) => {
    const itens = filtra(lista)
    if (itens.length === 0) return null
    return (
      <section className={s.secao}>
        <h3 className={s.secaoTitulo}>{titulo}</h3>
        {subtitulo && <p className={s.secaoSub}>{subtitulo}</p>}
        <div className={s.lista}>{itens.map(linha)}</div>
      </section>
    )
  }

  return (
    <>
      <button
        type="button"
        className={compacto ? s.chipCompacto : s.chip}
        title="Consultar os prazos do CPC e dos Juizados antes de lançar"
        onClick={() => setAberto(true)}
      >
        ⚖️ {compacto ? 'Prazos da lei' : 'Legenda — prazos da lei'}
      </button>

      {aberto && (
        <div className={s.overlay} onClick={() => setAberto(false)}>
          <div className={s.modal} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <header className={s.header}>
              <div>
                <h2 className={s.titulo}>Prazos processuais — CPC e Juizados</h2>
                <p className={s.subtitulo}>{data?.aviso}</p>
              </div>
              <button className={s.fechar} onClick={() => setAberto(false)} aria-label="Fechar">×</button>
            </header>

            {isLoading ? (
              <p className={s.estado}>Carregando catálogo...</p>
            ) : isError || !data ? (
              <p className={s.estado}>Não foi possível carregar o catálogo de prazos.</p>
            ) : (
              <>
                <input
                  className={s.busca}
                  placeholder="Buscar por peça, artigo ou palavra (ex.: apelação, 1.023, embargos)"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                />

                <div className={s.conteudo}>
                  {secao('Principais prazos — procedimento comum', data.principais)}
                  {secao('Juizados Especiais', data.juizados,
                    'Lei 9.099/95 (estadual), Lei 10.259/01 (federal) e Lei 12.153/09 (Fazenda).')}
                  {secao('Outros prazos', data.outros)}

                  {!busca && (
                    <>
                      <section className={s.secao}>
                        <h3 className={s.secaoTitulo}>Regras de contagem</h3>
                        <div className={s.lista}>
                          {data.regras_contagem.map((r) => (
                            <div key={r.regra} className={s.item}>
                              <div className={s.itemHead}>
                                <span className={s.itemRotulo}>{r.regra}</span>
                              </div>
                              <div className={s.fundamento}>{r.fundamento}</div>
                              <div className={s.observacao}>{r.detalhe}</div>
                            </div>
                          ))}
                        </div>
                      </section>

                      <section className={s.secao}>
                        <h3 className={s.secaoTitulo}>Prazo em dobro</h3>
                        <p className={s.secaoSub}>
                          Multiplicam qualquer prazo acima — o sistema não aplica sozinho.
                        </p>
                        <div className={s.lista}>
                          {data.prazos_em_dobro.map((d) => (
                            <div key={d.quem} className={s.item}>
                              <div className={s.itemHead}>
                                <span className={s.itemRotulo}>{d.quem}</span>
                              </div>
                              <div className={s.fundamento}>{d.fundamento}</div>
                              <div className={s.observacao}>{d.regra}</div>
                            </div>
                          ))}
                        </div>
                      </section>
                    </>
                  )}

                  {busca && filtra([...data.principais, ...data.juizados, ...data.outros]).length === 0 && (
                    <p className={s.estado}>Nada encontrado para “{busca}”.</p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
