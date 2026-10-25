import { useState } from 'react'
import EstrategiaAdvogados from './EstrategiaAdvogados'
import EstrategiaPosicoes from './EstrategiaPosicoes'
import styles from './Estrategia.module.css'

type Sub = 'advogados' | 'posicoes'

/** Cruzamentos para a estratégia de uma eventual mediação incidental. Cada visão é um módulo próprio
 *  (nada aqui altera a leitura dos autos): entram aos poucos nesta aba. */
export default function Estrategia({ casoId }: { casoId: string }) {
  const [sub, setSub] = useState<Sub>('advogados')
  return (
    <div className={styles.wrap}>
      <div className={styles.seg} role="tablist" aria-label="Estratégia">
        <button role="tab" aria-selected={sub === 'advogados'} className={sub === 'advogados' ? styles.segOn : ''} onClick={() => setSub('advogados')}>Advogados × valores</button>
        <button role="tab" aria-selected={sub === 'posicoes'} className={sub === 'posicoes' ? styles.segOn : ''} onClick={() => setSub('posicoes')}>Posições</button>
      </div>
      {sub === 'advogados' && <EstrategiaAdvogados casoId={casoId} />}
      {sub === 'posicoes' && <EstrategiaPosicoes casoId={casoId} />}
    </div>
  )
}
