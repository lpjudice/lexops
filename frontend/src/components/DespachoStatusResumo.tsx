import type { DespachoStatus } from '../api/diario'

/** Resumo do que já foi feito no Despacho pra essa publicação — usado no
 * Diário Oficial e no Recorte Digital OAB, pra não precisar abrir o Despacho
 * pra saber se e como uma publicação já foi tratada. */
export default function DespachoStatusResumo({ status }: { status: DespachoStatus | null | undefined }) {
  if (!status) return null

  return (
    <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: 10, margin: '8px 0', fontSize: 12 }}>
      <div style={{ fontWeight: 700, color: '#334155', marginBottom: 4 }}>⚙️ Tratado no Despacho</div>
      {status.disposicao === 'nao_e_nosso' ? (
        <div style={{ color: '#b91c1c' }}>✕ Não é do escritório</div>
      ) : status.disposicao === 'sem_acao' ? (
        <div style={{ color: '#6b7280' }}>◯ Revisado — sem necessidade de ação</div>
      ) : (
        <>
          {status.prazo && (
            <div style={{ marginBottom: 2 }}>
              📅 Prazo <strong>{status.prazo.tipo}</strong>
              {status.prazo.data_limite ? ` — vence ${status.prazo.data_limite}` : ''}
              {' '}<a href="/prazos" style={{ color: 'var(--teal)' }}>ver em Prazos</a>
              {status.prazo.status !== 'pendente' && <span style={{ marginLeft: 6, color: '#6b7280' }}>({status.prazo.status})</span>}
            </div>
          )}
          {status.tarefa_card && (
            <div style={{ marginBottom: 2 }}>
              📌 Card <strong>{status.tarefa_card.titulo}</strong>{' '}
              <a href="/tarefas-cards" style={{ color: 'var(--teal)' }}>ver em Tarefas Cards</a>
              {status.tarefa_card.subtasks.length > 0 && (
                <span style={{ marginLeft: 6, color: '#6b7280' }}>
                  ({status.tarefa_card.subtasks.filter((s) => s.concluida).length}/{status.tarefa_card.subtasks.length} concluídas)
                </span>
              )}
            </div>
          )}
          {status.tarefas.length > 0 && (
            <div style={{ marginBottom: 2 }}>
              ✅ {status.tarefas.length} tarefa(s) — <a href="/tarefas" style={{ color: 'var(--teal)' }}>ver em Tarefas</a>
            </div>
          )}
          {status.peca_doc_url && (
            <div>
              📄 <a href={status.peca_doc_url} target="_blank" rel="noreferrer" style={{ color: 'var(--teal)' }}>Abrir peça no Google Docs</a>
            </div>
          )}
          {!status.prazo && !status.tarefa_card && status.tarefas.length === 0 && !status.peca_doc_url && (
            <div style={{ color: '#6b7280' }}>Vínculo confirmado, sem prazo/tarefa criados.</div>
          )}
        </>
      )}
    </div>
  )
}
