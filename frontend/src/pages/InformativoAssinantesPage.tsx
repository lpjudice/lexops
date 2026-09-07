import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import styles from './Page.module.css'

interface Assinante {
  id: string
  email: string
  nome: string | null
  ativo: boolean
  created_at: string
}

const assinantesApi = {
  listar: () => api.get<Assinante[]>('/informativos/assinantes').then((r) => r.data),
  excluir: (id: string) => api.delete(`/informativos/assinantes/${id}`),
}

function fmtData(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR')
}

export default function InformativoAssinantesPage() {
  const qc = useQueryClient()
  const { data: assinantes = [], isLoading } = useQuery({
    queryKey: ['informativos', 'assinantes'],
    queryFn: assinantesApi.listar,
  })

  const excluirMutation = useMutation({
    mutationFn: assinantesApi.excluir,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativos', 'assinantes'] }),
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>E-mails cadastrados (Informativos)</h1>
      </div>
      <p style={{ fontSize: 13, color: '#6b7280', marginTop: 0 }}>
        Pessoas que se inscreveram pelo formulário na página pública de um informativo — não
        inclui Clientes nem Contatos do Conselho (esses entram automaticamente na newsletter,
        sem precisar se inscrever aqui).
      </p>

      {isLoading ? (
        <p>Carregando...</p>
      ) : assinantes.length === 0 ? (
        <p className={styles.empty}>Nenhuma inscrição ainda.</p>
      ) : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>E-mail</th>
                <th>Nome</th>
                <th>Inscrito em</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {assinantes.map((a) => (
                <tr key={a.id}>
                  <td>{a.email}</td>
                  <td>{a.nome || '—'}</td>
                  <td>{fmtData(a.created_at)}</td>
                  <td>{a.ativo ? 'Ativo' : 'Inativo'}</td>
                  <td>
                    <button
                      className={styles.btnTable}
                      onClick={() => {
                        if (window.confirm(`Remover ${a.email} da lista?`)) excluirMutation.mutate(a.id)
                      }}
                    >
                      Remover
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
