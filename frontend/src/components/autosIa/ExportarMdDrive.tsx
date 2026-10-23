import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import pageStyles from '../../pages/Page.module.css'
import styles from './ExportarMdDrive.module.css'

/** Exporta resumo + inteiro teor de cada peça (.md) para a pasta "Andamentos (MD)" do Drive,
 *  espelhando os PDFs. Depois da primeira exportação, cada sincronização mantém a pasta em dia. */
export default function ExportarMdDrive({ casoId }: { casoId: string }) {
  const qc = useQueryClient()
  const chave = ['autos-ia', 'export-md', casoId]

  const { data: st } = useQuery({
    queryKey: chave,
    queryFn: () => autosIa.statusExportMdDrive(casoId),
    refetchInterval: (q) => (q.state.data?.estado === 'rodando' ? 3000 : false),
  })

  const exportar = useMutation({
    mutationFn: (opts: { limite?: number; forcar?: boolean }) => autosIa.exportarMdDrive(casoId, opts),
    onSuccess: (r) => qc.setQueryData(chave, r),
    onError: (e: any) => alert(`Erro ao exportar para o Drive: ${e?.response?.data?.detail || e?.message}`),
  })

  const rodando = st?.estado === 'rodando' || exportar.isPending
  const primeira = (st?.exportadas ?? 0) === 0

  const iniciar = (limite?: number) => {
    const msg = limite
      ? `Enviar uma AMOSTRA de ${limite} peças (resumo + inteiro teor em .md) para a pasta "${st?.pasta_nome}" do Drive?`
      : `Enviar o resumo + inteiro teor de ${st?.total ?? 'todas as'} peça(s), em .md, para a pasta "${st?.pasta_nome}" do Drive (ao lado da pasta Andamentos, com os mesmos nomes)? O que já estiver lá e não mudou é pulado. Depois disso, cada sincronização atualiza a pasta sozinha.`
    if (window.confirm(msg)) exportar.mutate({ limite })
  }

  let linha: string | null = null
  if (rodando && st) linha = `Exportando… ${st.feitos}/${st.total} (${st.enviados} enviadas)`
  else if (st?.estado === 'erro') linha = st.mensagem || 'Falhou — veja os logs.'
  else if (st && st.exportadas > 0) {
    linha = `${st.exportadas}/${st.total} no Drive` + (st.erros ? ` · ${st.erros} com erro (rode de novo)` : '')
  }

  return (
    <>
      <button
        className={pageStyles.btnSmall}
        disabled={rodando}
        onClick={() => iniciar()}
        title='Cria/atualiza, na pasta "Andamentos (MD)" do Drive, um .md por peça (resumo + inteiro teor) com o mesmo nome do PDF'
      >
        {rodando ? 'Exportando .md…' : primeira ? 'Exportar .md p/ Drive' : 'Atualizar .md no Drive'}
      </button>
      {primeira && !rodando && (
        <button className={pageStyles.btnSmall} onClick={() => iniciar(10)} title="Envia só 10 peças, para conferir o resultado antes de exportar tudo">
          Amostra (10)
        </button>
      )}
      {linha && (
        <span className={st?.estado === 'erro' ? styles.erro : styles.status}>
          {linha}
          {st?.pasta_link && !rodando && (
            <>
              {' · '}
              <a href={st.pasta_link} target="_blank" rel="noreferrer">abrir pasta ↗</a>
            </>
          )}
        </span>
      )}
    </>
  )
}
