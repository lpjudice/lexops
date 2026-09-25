import { useState } from 'react'
import type { GrafoNo } from '../../api/autosIa'
import styles from './ReferenciaHover.module.css'

interface Props {
  idMencionado: string
  no?: GrafoNo
  onClickIrPara?: () => void
}

/** Chip com o ID mencionado; ao passar o mouse mostra resumo e keywords da peça
 * referenciada, sem precisar clicar/navegar. */
export default function ReferenciaHover({ idMencionado, no, onClickIrPara }: Props) {
  const [visivel, setVisivel] = useState(false)

  return (
    <span
      className={`${styles.chip} ${!no ? styles.chipNaoResolvido : ''}`}
      onMouseEnter={() => setVisivel(true)}
      onMouseLeave={() => setVisivel(false)}
      onFocus={() => setVisivel(true)}
      onBlur={() => setVisivel(false)}
      tabIndex={0}
    >
      {idMencionado}
      {visivel && (
        <div className={styles.tooltip}>
          {no ? (
            <>
              <div className={styles.tooltipTitulo}>{no.titulo}</div>
              <div className={styles.tooltipMeta}>
                {no.tipo} · págs. {no.pagina_inicio}-{no.pagina_fim}
                {no.data_peca ? ` · ${new Date(no.data_peca).toLocaleDateString('pt-BR')}` : ''}
              </div>
              <div className={styles.tooltipResumo}>{no.resumo || 'Ainda sem resumo gerado.'}</div>
              {no.keywords && no.keywords.length > 0 && (
                <div className={styles.tooltipKeywords}>
                  {no.keywords.map((k) => <span key={k}>{k}</span>)}
                </div>
              )}
              {onClickIrPara && (
                <button className={styles.tooltipBtn} onClick={onClickIrPara}>Ver peça →</button>
              )}
            </>
          ) : (
            <div className={styles.tooltipVazio}>
              Referência a "{idMencionado}" ainda não localizada no acervo carregado.
            </div>
          )}
        </div>
      )}
    </span>
  )
}
