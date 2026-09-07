import { useRef, useState } from 'react'
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
  fonte: string
  criado_por: string | null
  duplicado?: boolean
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
  created_at: string | null
  duplicado: boolean
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

const FONTE_LABEL: Record<string, string> = {
  formulario_publico: 'Formulário público',
  manual: 'Manual',
  csv: 'CSV colado',
  xls: 'Planilha',
}

function fmtData(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR')
}

function DuplicadoBadge({ duplicado }: { duplicado: boolean }) {
  if (!duplicado) return null
  return (
    <span title="Esse e-mail aparece em mais de uma seção" style={{ marginLeft: 6, fontSize: 11, background: '#fef3c7', color: '#92400e', padding: '1px 6px', borderRadius: 999 }}>
      🔁 duplicado
    </span>
  )
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

function NomeEditavel({ id, nome }: { id: string; nome: string | null }) {
  const qc = useQueryClient()
  const [editando, setEditando] = useState(false)
  const [valor, setValor] = useState(nome || '')
  const mutation = useMutation({
    mutationFn: (v: string) => informativosApi.editarNomeAssinante(id, v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['informativos', 'assinantes'] }); setEditando(false) },
  })

  if (!editando) {
    return (
      <span style={{ cursor: 'pointer' }} onClick={() => { setValor(nome || ''); setEditando(true) }} title="Clique pra editar">
        {nome || '—'} <span style={{ fontSize: 11, color: '#9ca3af' }}>✎</span>
      </span>
    )
  }
  return (
    <span style={{ display: 'inline-flex', gap: 4 }}>
      <input
        autoFocus
        value={valor}
        onChange={(e) => setValor(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') mutation.mutate(valor); if (e.key === 'Escape') setEditando(false) }}
        style={{ padding: 3, fontSize: 12.5, width: 140 }}
      />
      <button className={styles.btnTable} onClick={() => mutation.mutate(valor)} disabled={mutation.isPending}>OK</button>
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
                <th>Cadastrado em</th>
                <th>Newsletter enviada</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {entradas.map((e, idx) => (
                <tr key={idx}>
                  <td>{e.email}<DuplicadoBadge duplicado={e.duplicado} /></td>
                  <td>{e.nome || '—'}</td>
                  <td>{e.created_at ? fmtData(e.created_at) : '—'}</td>
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

function parseCsvColado(texto: string): { email: string; nome?: string }[] {
  return texto
    .split(/\r?\n/)
    .map((linha) => linha.trim())
    .filter(Boolean)
    .map((linha) => {
      const partes = linha.split(/[,;\t]/).map((p) => p.trim())
      return { email: partes[0], nome: partes.slice(1).join(' ') || undefined }
    })
    .filter((item) => item.email.includes('@'))
}

function AdicionarPanel() {
  const qc = useQueryClient()
  const [modo, setModo] = useState<'manual' | 'csv' | 'arquivo'>('manual')
  const [email, setEmail] = useState('')
  const [nome, setNome] = useState('')
  const [csvTexto, setCsvTexto] = useState('')
  const [resultado, setResultado] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ['informativos', 'assinantes'] })
    qc.invalidateQueries({ queryKey: ['informativos', 'destinatarios-por-fonte'] })
  }

  const manualMutation = useMutation({
    mutationFn: () => informativosApi.criarAssinante(email, nome),
    onSuccess: () => { invalidar(); setEmail(''); setNome(''); setResultado('Adicionado.') },
  })
  const csvMutation = useMutation({
    mutationFn: () => informativosApi.importarAssinantes(parseCsvColado(csvTexto)),
    onSuccess: (r) => { invalidar(); setCsvTexto(''); setResultado(`${r.criados} novo(s), ${r.atualizados} atualizado(s)${r.invalidos ? `, ${r.invalidos} inválido(s)` : ''}.`) },
  })
  const arquivoMutation = useMutation({
    mutationFn: (file: File) => informativosApi.importarAssinantesArquivo(file),
    onSuccess: (r) => { invalidar(); if (fileRef.current) fileRef.current.value = ''; setResultado(`${r.criados} novo(s), ${r.atualizados} atualizado(s)${r.invalidos ? `, ${r.invalidos} inválido(s)` : ''}.`) },
  })

  const erro = manualMutation.error || csvMutation.error || arquivoMutation.error

  return (
    <details style={{ marginBottom: 20 }}>
      <summary style={{ cursor: 'pointer', fontSize: 15, fontWeight: 600 }}>+ Adicionar e-mail(s) manualmente</summary>
      <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
        {(['manual', 'csv', 'arquivo'] as const).map((m) => (
          <button
            key={m}
            className={styles.btnTable}
            style={{ fontWeight: modo === m ? 700 : 400, background: modo === m ? '#eef2ff' : undefined }}
            onClick={() => { setModo(m); setResultado(null) }}
          >
            {m === 'manual' ? 'Um a um' : m === 'csv' ? 'Colar lista (CSV)' : 'Upload de planilha'}
          </button>
        ))}
      </div>

      {modo === 'manual' && (
        <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center' }}>
          <input placeholder="email@exemplo.com" value={email} onChange={(e) => setEmail(e.target.value)} style={{ padding: 6, minWidth: 220 }} />
          <input placeholder="Nome (opcional)" value={nome} onChange={(e) => setNome(e.target.value)} style={{ padding: 6, minWidth: 180 }} />
          <button className={styles.btnPrimary} onClick={() => manualMutation.mutate()} disabled={!email.includes('@') || manualMutation.isPending}>
            Adicionar
          </button>
        </div>
      )}

      {modo === 'csv' && (
        <div style={{ marginTop: 10 }}>
          <p style={{ fontSize: 12, color: '#6b7280', margin: '0 0 6px' }}>
            Uma linha por pessoa — <code>email</code> ou <code>email, nome</code>.
          </p>
          <textarea
            value={csvTexto}
            onChange={(e) => setCsvTexto(e.target.value)}
            rows={6}
            style={{ width: '100%', maxWidth: 480, fontFamily: 'monospace', fontSize: 12.5, padding: 8 }}
            placeholder={'joao@empresa.com, João Silva\nmaria@empresa.com'}
          />
          <div style={{ marginTop: 6 }}>
            <button className={styles.btnPrimary} onClick={() => csvMutation.mutate()} disabled={!csvTexto.trim() || csvMutation.isPending}>
              Importar
            </button>
          </div>
        </div>
      )}

      {modo === 'arquivo' && (
        <div style={{ marginTop: 10 }}>
          <p style={{ fontSize: 12, color: '#6b7280', margin: '0 0 6px' }}>
            Arquivo .xlsx, .xls ou .csv com colunas <code>email</code> e <code>nome</code> (nomes de coluna flexíveis).
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) arquivoMutation.mutate(f) }}
          />
        </div>
      )}

      {resultado && <p style={{ fontSize: 12.5, color: '#15803d', marginTop: 8 }}>{resultado}</p>}
      {erro ? <p style={{ fontSize: 12.5, color: '#b91c1c', marginTop: 8 }}>{erroApi(erro)}</p> : null}
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
  const duplicadoPorEmail = new Map((porFonte?.assinantes ?? []).map((a) => [a.email.toLowerCase(), a.duplicado]))

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
        mexe no cadastro de Cliente/Contato em si). 🔁 marca e-mail repetido em mais de uma seção.
        {linkSite && (
          <> Formulário de inscrição pública: <a href={linkSite} target="_blank" rel="noreferrer">ver no informativo publicado →</a></>
        )}
      </p>

      <AdicionarPanel />

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
          Inscritos/cadastrados manualmente — {assinantes.length}
        </summary>
        <p style={{ fontSize: 12.5, color: '#6b7280', marginTop: 4 }}>
          Quem se inscreveu direto na página pública de um informativo, ou foi adicionado à mão/por
          planilha aqui (não é Cliente nem Contato da Expansão).
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
                  <th>Cadastrado em</th>
                  <th>Fonte</th>
                  <th>Cadastrado por</th>
                  <th>Newsletter enviada</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {assinantes.map((a) => (
                  <tr key={a.id}>
                    <td>{a.email}<DuplicadoBadge duplicado={Boolean(duplicadoPorEmail.get(a.email.toLowerCase()))} /></td>
                    <td><NomeEditavel id={a.id} nome={a.nome} /></td>
                    <td>{fmtData(a.created_at)}</td>
                    <td>{FONTE_LABEL[a.fonte] || a.fonte}</td>
                    <td>{a.criado_por || '—'}</td>
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
