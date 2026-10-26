import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { estrutura } from '../../../api/estrutura'
import type { FiltrosCreditos } from '../../../api/estrutura'
import FiltrosPainel from './FiltrosPainel'
import ImportarEstrutura from './ImportarEstrutura'
import Organograma from './Organograma'
import PivotCreditos from './PivotCreditos'
import TabelaCreditos from './TabelaCreditos'
import VisaoGeral from './VisaoGeral'
import { brl } from './util'
import styles from './Estrutura.module.css'

type Sub = 'geral' | 'dividas' | 'pivot' | 'organograma' | 'importar'

/** Estrutura do grupo × relação de créditos: visão geral, tabela filtrável, tabela dinâmica e organograma com as dívidas. */
export default function EstruturaDividas({ casoId }: { casoId: string }) {
  const [sub, setSub] = useState<Sub>('geral')
  const [f, setF] = useState<FiltrosCreditos>({})
  const lotes = useQuery({ queryKey: ['estrutura', 'lotes', casoId], queryFn: () => estrutura.lotes(casoId) })
  const opcoes = useQuery({ queryKey: ['estrutura', 'opcoes', casoId, lotes.data?.find((l) => l.ativo)?.id], queryFn: () => estrutura.opcoes(casoId), enabled: !!lotes.data?.length })
  const ativo = lotes.data?.find((l) => l.ativo)
  const semDados = lotes.isSuccess && lotes.data.length === 0
  const usaFiltros = sub === 'geral' || sub === 'dividas' || sub === 'pivot'
  const detalhar = (nf: FiltrosCreditos) => { setF(nf); setSub('dividas') }

  return (
    <div className={styles.wrap}>
      <div className={styles.barra}>
        <div className={styles.seg} role="tablist" aria-label="Estrutura e dívidas">
          <button role="tab" aria-selected={sub === 'geral'} className={sub === 'geral' ? styles.segOn : ''} onClick={() => setSub('geral')}>Visão geral</button>
          <button role="tab" aria-selected={sub === 'dividas'} className={sub === 'dividas' ? styles.segOn : ''} onClick={() => setSub('dividas')}>Dívidas</button>
          <button role="tab" aria-selected={sub === 'pivot'} className={sub === 'pivot' ? styles.segOn : ''} onClick={() => setSub('pivot')}>Tabela dinâmica</button>
          <button role="tab" aria-selected={sub === 'organograma'} className={sub === 'organograma' ? styles.segOn : ''} onClick={() => setSub('organograma')}>Organograma</button>
          <button role="tab" aria-selected={sub === 'importar'} className={sub === 'importar' ? styles.segOn : ''} onClick={() => setSub('importar')}>Importar / versões</button>
        </div>
        {ativo && <span className={styles.dica}>Planilha em uso: {ativo.nome_arquivo ?? 'sem nome'} · {ativo.total_linhas.toLocaleString('pt-BR')} linhas · {brl(ativo.total_centavos)}</span>}
      </div>

      {semDados && sub !== 'importar' && sub !== 'organograma' ? (
        <p className={styles.vazio}>Nenhuma planilha de credores importada ainda. Vá em <button className={styles.link} onClick={() => setSub('importar')}>Importar / versões</button>.</p>
      ) : (
        <>
          {usaFiltros && <FiltrosPainel f={f} setF={setF} opcoes={opcoes.data} />}
          {sub === 'geral' && <VisaoGeral casoId={casoId} f={f} setF={setF} />}
          {sub === 'dividas' && <TabelaCreditos casoId={casoId} f={f} />}
          {sub === 'pivot' && <PivotCreditos casoId={casoId} f={f} onDetalhar={detalhar} />}
          {sub === 'organograma' && <Organograma casoId={casoId} onVerDividas={(cnpj) => detalhar({ devedor: [cnpj] })} />}
        </>
      )}
      {sub === 'importar' && <ImportarEstrutura casoId={casoId} />}
    </div>
  )
}
