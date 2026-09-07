import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { informativosApi, erroApi } from '../api/informativos'
import styles from './Page.module.css'

interface Assinante {
  id: string
  email: string
  nome: string | null
  ativo: boolean
  created_at: string
}

interface EnvioStatus {
  total_enviados: number
  ultimo_numero: number | null
  ultimo_titulo: string | null
  ultimo_enviado_em: string | null
}

interface Entrada {
  email: string
  nome: string
  opt_out: boolean
  envio_status: EnvioStatus | null
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

function fmtDataHora(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

function EnvioBadge({ status }: { status: EnvioStatus | null }) {
  if (!status || !status.total_enviados) return <span style={{ color: '#9ca3af' }}>— nunca</span>
  return (
    <span title={status.ultimo_titulo || undefined} style={{ color: '#374151' }}>
      ✓ {status.total_enviados}x · último {status.ultimo_enviado_em ? fmtDataHora(status.ultimo_enviado_em) : '—'}
    </span>
  )
}

function AcoesEmail({ email, opt_out }: { email: string; opt_out: boolean }) {
  const qc = useQueryClient()
  const invalidar = () => qc.invalidateQueries({ queryKey: ['informativos', 'destinatarios-por-fonte'] })

  const optOutMutation = useMutation({ mutationFn: () => informativosApi.optOut(email), onSuccess: invalidar })
  const reativarMutation = useMutation({ mutationFn: () => informativosApi.reativarEmail(email), onSuccess: invalidar })
  const excluirMutation = useMutation({ mutationFn: () => informativosApi.excluirEmail(email), onSuccess: invalidar })

  return (
    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
      {opt_out ? (
        <button className={styles.btnTable} onClick={() => reativarMutation.mutate()} disabled={reativarMutation.isPending}>
          Reativar
        </button>
      ) : (
        <button className={styles.btnTable} onClick={() => optOutMutation.mutate()} disabled={optOutMutation.isPending}>
          Opt-out
        </button>
      )}
      <button
        className={styles.btnTable}
        style={{ color: '#b91c1c' }}
        onClick={() => {
          if (window.confirm(`Excluir ${email} completamente da lista de Informativos? Ele some daqui e nunca mais recebe a newsletter (não afeta o cadastro dele em Clientes/Expansão).`)) {
            excluirMutation.mutate()
          }
        }}
        disabled={excluirMutation.isPending}
      >
        Excluir
      </button>
    </div>
  )
}

function Secao({ titulo, descricao, entradas }: { titulo: string; descricao: string; entradas: Entrada[] }) {
  return (
    <details style={{ marginBottom: 16 }} open>
      <summary style={{ cursor: 'pointer', fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
        {titulo} — {entradas.length}
      </summary>
      <p style={{ fontSize: 12.5, color: '#6b7280', marginTop: 4 }}>{descricao}</p>
      {entradas.length === 0 ? (
        <p className={styles.empty}>Nenhum e-mail.</p>
      ) : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>E-mail</th>
                <th>Nome</th>
                <th>Newsletter enviada</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {entradas.map((e, idx) => (
                <tr key={idx}>
                  <td>{e.email}</td>
                  <td>{e.nome || '—'}</td>
                  <td><EnvioBadge status={e.envio_status} /></td>
                  <td>{e.opt_out ? '🚫 Descadastrado' : '—'}</td>
                  <td><AcoesEmail email={e.email} opt_out={e.opt_out} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
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

  const envioPorEmail = new Map((porFonte?.assinantes ?? []).map((a) => [a.email.toLowerCase(), a.envio_status]))

  const publicado = informativosLista.find((i) => i.status === 'publicado')
  const linkSite = publicado ? `https://www.pimentajudice.com.br/informativos/ler/${publicado.id}` : null

  const total = (porFonte?.clientes.length ?? 0) + (porFonte?.contatos.length ?? 0) + (porFonte?.assinantes.length ?? 0)

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>E-mails (Informativos) — {total} no total</h1>
      </div>
      <p style={{ fontSize: 13, color: '#6b7280', marginTop: 0 }}>
        A newsletter dos informativos vai pra todos os e-mails abaixo (Clientes e Contatos da
        Expansão entram automaticamente, sem precisar se inscrever), menos quem estiver com
        opt-out (por escolha própria ou sua). "Excluir" tira o e-mail da lista por completo (não
        mexe no cadastro de Cliente/Contato em si).
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

      <details style={{ marginBottom: 8 }} open>
        <summary style={{ cursor: 'pointer', fontSize: 15, fontWeight: 600 }}>
          Inscritos pelo formulário público — {assinantes.length}
        </summary>
        <p style={{ fontSize: 12.5, color: '#6b7280', marginTop: 4 }}>
          Quem se inscreveu direto na página pública de um informativo (não é Cliente nem Contato).
        </p>
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
                  <th>Newsletter enviada</th>
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
                    <td><EnvioBadge status={envioPorEmail.get(a.email.toLowerCase()) ?? null} /></td>
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
                      {excluirMutation.isError && <div style={{ color: '#b91c1c', fontSize: 11 }}>{erroApi(excluirMutation.error)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>
    </div>
  )
}
