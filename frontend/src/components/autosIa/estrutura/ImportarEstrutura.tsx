import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { estrutura } from '../../../api/estrutura'
import styles from './Estrutura.module.css'

const msgErro = (e: any) => e?.response?.data?.detail || e?.message || 'Não foi possível concluir.'

export default function ImportarEstrutura({ casoId }: { casoId: string }) {
  const qc = useQueryClient()
  const lotes = useQuery({ queryKey: ['estrutura', 'lotes', casoId], queryFn: () => estrutura.lotes(casoId) })
  const org = useQuery({ queryKey: ['estrutura', 'organograma', casoId], queryFn: () => estrutura.organograma(casoId) })
  const planilha = useRef<HTMLInputElement>(null)
  const pdf = useRef<HTMLInputElement>(null)
  const [notas, setNotas] = useState('')
  const [resultadoOrg, setResultadoOrg] = useState<Awaited<ReturnType<typeof estrutura.importarOrganograma>> | null>(null)
  const tudo = () => qc.invalidateQueries({ queryKey: ['estrutura'] })

  const importar = useMutation({
    mutationFn: (f: File) => estrutura.importarPlanilha(casoId, f, notas.trim() || undefined),
    onSuccess: () => { setNotas(''); if (planilha.current) planilha.current.value = ''; tudo() },
    onError: (e) => alert(msgErro(e)),
  })
  const ativar = useMutation({ mutationFn: (id: string) => estrutura.ativarLote(casoId, id), onSuccess: tudo, onError: (e) => alert(msgErro(e)) })
  const excluir = useMutation({ mutationFn: (id: string) => estrutura.excluirLote(casoId, id), onSuccess: tudo, onError: (e) => alert(msgErro(e)) })
  const lerOrg = useMutation({
    mutationFn: (f?: File) => estrutura.importarOrganograma(casoId, f),
    onSuccess: (r) => { setResultadoOrg(r); if (pdf.current) pdf.current.value = ''; tudo() },
    onError: (e) => alert(msgErro(e)),
  })
  const data = (s: string) => new Date(s).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })

  return (
    <div className={styles.wrap}>
      <div className={styles.upload}>
        <h3>1. Relação de credores (planilha .xlsx)</h3>
        <p className={styles.explica}>
          Colunas esperadas na primeira linha (como a planilha atual): <em>CNPJ devedor, Razão social devedora, Credor / razão social, CPF/CNPJ do credor, Natureza/origem do crédito, Classe sugerida, Valor na data-base (R$), Data de vencimento, Coobrigados/fiadores, Página do PDF</em>.
          Cada envio vira uma <strong>nova versão</strong>: a mais recente passa a valer e as anteriores ficam guardadas para você comparar ou reativar. A ligação com o organograma é pelo CNPJ.
        </p>
        <div className={styles.barra}>
          <input ref={planilha} type="file" accept=".xlsx,.xlsm" aria-label="Planilha de credores" />
          <input value={notas} onChange={(e) => setNotas(e.target.value)} placeholder="Nota desta versão (opcional)" aria-label="Nota da versão" style={{ padding: '6px 10px', border: '1px solid var(--gray-border)', borderRadius: 8, font: 'inherit', fontSize: 13, minWidth: 220 }} />
          <button className={styles.btn} disabled={importar.isPending} onClick={() => { const f = planilha.current?.files?.[0]; if (!f) { alert('Escolha a planilha.'); return } importar.mutate(f) }}>{importar.isPending ? 'Importando…' : 'Importar planilha'}</button>
        </div>
        {lotes.data && lotes.data.length > 0 && (
          <div className={styles.tabelaWrap}>
            <table className={styles.tabela}>
              <thead><tr><th>Versão importada em</th><th>Arquivo</th><th className={styles.num}>Linhas</th><th className={styles.num}>Total</th><th>Nota</th><th /></tr></thead>
              <tbody>
                {lotes.data.map((l) => (
                  <tr key={l.id}>
                    <td>{data(l.importado_em)} {l.ativo && <span className={styles.chip}>em uso</span>}</td><td>{l.nome_arquivo ?? '—'}</td>
                    <td className={styles.num}>{l.total_linhas.toLocaleString('pt-BR')}</td><td className={styles.num}>{l.total}</td><td>{l.notas ?? ''}</td>
                    <td>{!l.ativo && <button className={styles.link} onClick={() => ativar.mutate(l.id)}>usar esta</button>} <button className={styles.miniLink} onClick={() => window.confirm('Excluir esta versão da planilha?') && excluir.mutate(l.id)}>excluir</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className={styles.upload}>
        <h3>2. Organograma societário do grupo</h3>
        <p className={styles.explica}>
          Lê o desenho do PDF do processo (“Doc. 06 — Organograma Grupo Apex”: cada caixa é uma empresa, cada linha uma participação, com o percentual) e o nível de cada empresa na “Lista de empresas e atividades” (Doc. 06).
          É leitura do próprio desenho — não é interpretação por IA. {org.data && org.data.empresas.length > 0 && <strong>Já há {org.data.empresas.length} empresas e {org.data.participacoes.length} vínculos; ler de novo atualiza sem apagar o que você validou ou editou.</strong>}
        </p>
        <div className={styles.barra}>
          <button className={styles.btn} disabled={lerOrg.isPending} onClick={() => lerOrg.mutate(undefined)}>{lerOrg.isPending ? 'Lendo…' : 'Ler organograma do processo'}</button>
          <span className={styles.dica}>ou envie outro PDF:</span>
          <input ref={pdf} type="file" accept="application/pdf,.pdf" aria-label="PDF do organograma" onChange={(e) => { const f = e.target.files?.[0]; if (f) lerOrg.mutate(f) }} />
        </div>
        {resultadoOrg && (
          <>
            <div className={styles.ok}>Organograma lido: {resultadoOrg.empresas} empresas ({resultadoOrg.empresas_novas} novas), {resultadoOrg.vinculos} vínculos ({resultadoOrg.vinculos_novos} novos, {resultadoOrg.vinculos_removidos} removidos), níveis lidos para {resultadoOrg.niveis_lidos} empresas.</div>
            {resultadoOrg.avisos.length > 0 && <div className={styles.avisos}>{resultadoOrg.avisos.map((a) => <div key={a}>{a}</div>)}</div>}
          </>
        )}
      </div>
    </div>
  )
}
