import { useQuery } from '@tanstack/react-query'
import { prazosApi } from '../api/prazos'
import styles from './AnotacoesPrazosSection.module.css'

interface Props {
  processoId: string
}

const PRAZO_TIPO_LABEL: Record<string, string> = {
  contestacao: 'Contestação', recurso: 'Recurso', contrarrazoes: 'Contrarrazões',
  manifestacao: 'Manifestação', audiencia: 'Audiência', pericia: 'Perícia', outro: 'Prazo',
}
const PRAZO_STATUS_LABEL: Record<string, string> = {
  pendente: 'pendente', cumprido: 'cumprido', perdido: 'perdido',
  ignorado: 'ignorado', nada_a_fazer: 'nada a fazer',
}

function formatDate(d?: string | null): string {
  if (!d) return '—'
  const [y, m, day] = d.split('-')
  return `${day}/${m}/${y}`
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

/** Painel "📝 Anotações de Prazos" — feed de TODOS os comentários de prazo
 * deste processo, vinculados a um andamento ou não. Mostrado ao lado de
 * Andamentos (mesma query/cache da nota interleaved em AndamentosSection,
 * ver ali): aqui é o lugar que nunca exige vínculo pra uma anotação aparecer,
 * e que nunca mistura dado de tribunal com opinião humana na mesma linha.
 * Some por completo quando não há nenhuma anotação — não é um painel
 * permanente, só aparece quando há algo pra mostrar. */
export default function AnotacoesPrazosSection({ processoId }: Props) {
  const { data: comentarios = [] } = useQuery({
    queryKey: ['comentarios-prazo-processo', processoId],
    queryFn: () => prazosApi.listarComentariosDoProcesso(processoId),
    staleTime: 30_000,
  })

  if (comentarios.length === 0) return null

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.title}>📝 Anotações de Prazos</span>
        <span className={styles.count}>{comentarios.length}</span>
      </div>
      <div className={styles.lista}>
        {comentarios.map((c) => {
          const peca = c.prazo_peca || PRAZO_TIPO_LABEL[c.prazo_tipo] || c.prazo_tipo
          const statusLabel = PRAZO_STATUS_LABEL[c.prazo_status] ?? c.prazo_status
          return (
            <div key={c.id} className={styles.card}>
              <div className={styles.top}>
                <span className={styles.peca}>{peca}</span>
                {c.andamento_id ? (
                  <span className={`${styles.chip} ${styles.chipVinculado}`}>⧉ vinculado</span>
                ) : (
                  <span className={`${styles.chip} ${styles.chipNaoVinculado}`}>◻ não vinculado</span>
                )}
              </div>
              <p className={styles.texto}>"{c.texto}"</p>
              <div className={styles.foot}>
                {c.autor_nome || 'usuário'} · {formatDateTime(c.created_at)}
                {c.andamento_id
                  ? <> · vinculado a {c.andamento_tipo || 'andamento'}, {formatDate(c.andamento_data)}</>
                  : c.prazo_data_limite && <> · {statusLabel === 'pendente' ? 'vence' : statusLabel} {formatDate(c.prazo_data_limite)}</>}
                {' · '}
                <a href={`/prazos?destaque=${c.prazo_id}`} className={styles.link}>ver em Prazos</a>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
