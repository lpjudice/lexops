import { useState } from 'react'
import EstrategiaAdvogados from './EstrategiaAdvogados'
import styles from './Estrategia.module.css'

type Sub = 'advogados'

/** Cruzamentos para a estratégia de uma eventual mediação incidental. Cada visão é um módulo próprio
 *  (nada aqui altera a leitura dos autos): entram aos poucos nesta aba. */
export default function Estrategia({ casoId }: { casoId: string }) {
  const [sub] = useState<Sub>('advogados')
  return (
    <div className={styles.wrap}>
      {sub === 'advogados' && <EstrategiaAdvogados casoId={casoId} />}
    </div>
  )
}
