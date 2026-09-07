import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { informativosApi } from '../api/informativos'
import styles from './Page.module.css'

interface Assinante {
  id: string
  email: string
  nome: string | null
  ativo: boolean
  created_at: string
}

interface Entrada {
  email: string
  nome: string
  opt_out: boolean
}

interface DestinatariosPorFonte {
  clientes: Entrada[]
  contatos: Entrada[]
  assinantes: (Entrada & { ativo: boolean; created_at: string })[]
}

const assinantesApi = {
  listar: () => api.get<Assinante[]>('/informativos/assinantes').then((r) => r.data),
  excluir: (id: string) => api.delete(`/informativos/assinantes/${id}`),
  porFonte: () => api.get<DestinatariosPorFonte>('/informativos/destinatarios-por-fonte').then((r) => r.data),
}

function fmtData(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR')
}

function Secao({ titulo, descricao, entradas }: { titulo: string; descricao: string; entradas: Entrada[] }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h3 style={{ fontSize: 15, marginBottom: 2 }}>{titulo} — {entradas.length}</h3>
      <p style={{ fontSize: 12.5, color: '#6b7280', marginTop: 0 }}>{descricao}</p>
      {entradas.length === 0 ? (
        <p className={styles.empty}>Nenhum e-mail.</p>
      ) : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>E-mail</th>
                <th>Nome</th>
                <th>Opt-out</th>
              </tr>
            </thead>
            <tbody>
              {entradas.map((e, idx) => (
                <tr key={idx}>
                  <td>{e.email}</td>
                  <td>{e.nome || '—'}</td>
                  <td>{e.opt_out ? '🚫 Descadastrado' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function InformativoAssinantesPage() {
  const qc = useQueryClient()
  const { data: assinantes = [], isLoading: carregandoAssinantes } = useQuery({
    queryKey: ['informativos', 'assinantes'],
    queryFn: assinantesApi.listar,
  })
  const { data: porFonte, isLoading: carregandoFontes } = useQuery({
    queryKey: ['informativos', 'destinatarios-por-fonte'],
    queryFn: assinantesApi.porFonte,
  })
  const { data: informativosLista = [] } = useQuery({
    queryKey: ['informativos'],
    queryFn: () => informativosApi.listar(),
  })

  const excluirMutation = useMutation({
    mutationFn: assinantesApi.excluir,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['informativos', 'assinantes'] })
      qc.invalidateQueries({ queryKey: ['informativos', 'destinatarios-por-fonte'] })
    },
  })

  const publicado = informativosLista.find((i) => i.status === 'publicado')
  const linkSite = publicado ? `${window.location.origin}/api/publico/informativos/${publicado.id}.html` : null

  const total = (porFonte?.clientes.length ?? 0) + (porFonte?.contatos.length ?? 0) + (porFonte?.assinantes.length ?? 0)

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>E-mails (Informativos) — {total} no total</h1>
      </div>
      <p style={{ fontSize: 13, color: '#6b7280', marginTop: 0 }}>
        A newsletter dos informativos vai pra todos os e-mails abaixo (Clientes e Contatos da
        Expansão entram automaticamente, sem precisar se inscrever), menos quem clicou em
        "descadastrar" no rodapé de um e-mail.
        {linkSite && (
          <> Formulário de inscrição pública: <a href={linkSite} target="_blank" rel="noreferrer">ver no informativo publicado →</a></>
        )}
      </p>

      {carregandoFontes ? (
        <p>Carregando...</p>
      ) : (
        <>
          <Secao
            titulo="Clientes cadastrados"
            descricao="E-mail de Clientes do sistema — entram automaticamente, sem cadastro à parte."
            entradas={porFonte?.clientes ?? []}
          />
          <Secao
            titulo="Contatos da Expansão"
            descricao="E-mail de Contatos do módulo Expansão (Eventos) — entram automaticamente."
            entradas={porFonte?.contatos ?? []}
          />
        </>
      )}

      <div style={{ marginBottom: 8 }}>
        <h3 style={{ fontSize: 15, marginBottom: 2 }}>Inscritos pelo formulário público — {assinantes.length}</h3>
        <p style={{ fontSize: 12.5, color: '#6b7280', marginTop: 0 }}>
          Quem se inscreveu direto na página pública de um informativo (não é Cliente nem Contato).
          Únicos que dá pra remover por aqui.
        </p>
      </div>
      {carregandoAssinantes ? (
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
