import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { clientesApi } from '../api/clientes'
import type { Cliente, ClienteCreate } from '../api/clientes'
import CadastrosPendentes from '../components/CadastrosPendentes'
import DuplicatasClientes from '../components/DuplicatasClientes'
import EnviarLinkModal from '../components/EnviarLinkModal'
import ConfirmarWhatsappModal from '../components/ConfirmarWhatsappModal'
import WhatsappBadge from '../components/WhatsappBadge'
import VinculosEditor, { ClienteVinculos } from '../components/VinculosEditor'
import { isoParaBr } from '../utils/masks'
import ClienteFormFields, { comDataIso } from '../components/ClienteFormFields'
import styles from './Page.module.css'
import cs from './ClientesPage.module.css'

const EMPTY: ClienteCreate = { nome: '', tipo: 'PF', cpf_cnpj: '', email: '', telefone: '', observacoes: '' }

export default function ClientesPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ClienteCreate>(EMPTY)
  const [editando, setEditando] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Partial<ClienteCreate>>({})
  const [busca, setBusca] = useState('')
  const [enviarPara, setEnviarPara] = useState<{ id: string; nome: string; email?: string } | null>(null)
  const [enviarGenerico, setEnviarGenerico] = useState(false)
  // Vínculos pendentes do cliente que está sendo criado (aplicados após o POST).
  const [novoVinculos, setNovoVinculos] = useState<Cliente[]>([])

  const [confirmarWa, setConfirmarWa] = useState(false)
  const { data: waPendentes = [] } = useQuery({
    queryKey: ['clientes-whatsapp-pendentes'],
    queryFn: clientesApi.whatsappPendentes,
  })
  const { data: clientes = [], isLoading } = useQuery({
    queryKey: ['clientes'],
    queryFn: clientesApi.listar,
  })

  // Cria um cliente inline a partir do combobox ("nome|tipo"); retorna o id.
  const criarClienteInline = async (raw: string): Promise<string> => {
    const [nome, tipo] = raw.split('|')
    const c = await clientesApi.criar({ nome, tipo: (tipo as 'PF' | 'PJ') ?? 'PF', incompleto: true })
    qc.invalidateQueries({ queryKey: ['clientes'] })
    return c.id
  }

  const clientesFiltrados = clientes.filter((c) => {
    if (!busca.trim()) return true
    const q = busca.toLowerCase()
    return (
      c.nome.toLowerCase().includes(q) ||
      (c.email?.toLowerCase().includes(q) ?? false)
    )
  })

  const criar = useMutation({
    mutationFn: clientesApi.criar,
    onSuccess: async (novo) => {
      // Aplica os vínculos escolhidos no formulário de criação.
      for (const v of novoVinculos) {
        try { await clientesApi.adicionarVinculo(novo.id, v.id) } catch { /* segue */ }
      }
      qc.invalidateQueries({ queryKey: ['clientes'] })
      qc.invalidateQueries({ queryKey: ['vinculos'] })
      setShowForm(false)
      setForm(EMPTY)
      setNovoVinculos([])
    },
  })

  const criarErro = criar.error
    ? ((criar.error as any)?.response?.data?.detail ?? 'Erro ao salvar. Verifique os dados e tente novamente.')
    : null

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ClienteCreate> }) =>
      clientesApi.atualizar(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clientes'] })
      setEditando(null)
    },
  })

  const deletar = useMutation({
    mutationFn: (id: string) => clientesApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clientes'] }),
  })

  const toggleMonitorar = useMutation({
    mutationFn: ({ id, monitorar_diario }: { id: string; monitorar_diario: boolean }) =>
      clientesApi.atualizar(id, { monitorar_diario }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clientes'] }),
  })

  return (
    <div>
      {confirmarWa && <ConfirmarWhatsappModal onClose={() => setConfirmarWa(false)} />}
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Clientes</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className={styles.btnTable}
            title="Copiar ou enviar o link público de autocadastro (cliente novo)"
            onClick={() => setEnviarGenerico(true)}>
            🔗 Link de cadastro
          </button>
          {waPendentes.length > 0 && (
            <button className={styles.btnTable}
              title="Clientes com celular cadastrado, sem confirmação de que é WhatsApp"
              onClick={() => setConfirmarWa(true)}>
              📱 Confirmar WhatsApp ({waPendentes.length})
            </button>
          )}
          <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancelar' : '+ Novo Cliente'}
          </button>
        </div>
      </div>

      <DuplicatasClientes />
      <CadastrosPendentes />

      {enviarPara && (
        <EnviarLinkModal cliente={enviarPara} onClose={() => setEnviarPara(null)} />
      )}
      {enviarGenerico && (
        <EnviarLinkModal onClose={() => setEnviarGenerico(false)} />
      )}

      <div className={cs.buscaRow}>
        <input
          className={cs.buscaInput}
          placeholder="Buscar por nome ou email..."
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        {busca && (
          <button className={cs.buscaLimpar} onClick={() => setBusca('')}>×</button>
        )}
      </div>

      {showForm && (
        <form onSubmit={(e) => { e.preventDefault(); criar.mutate(comDataIso(form)) }} className={styles.form}>
          <ClienteFormFields
            form={form}
            onChange={(f) => { criar.reset(); setForm(f) }}
          />
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Outras pessoas vinculadas</label>
            <VinculosEditor
              vinculados={novoVinculos}
              clientes={clientes}
              onCreateCliente={criarClienteInline}
              onAdd={async (id) => {
                if (novoVinculos.some((v) => v.id === id)) return
                // Pode ser um cliente recém-criado inline (ainda fora do cache).
                const c = clientes.find((x) => x.id === id) ?? await clientesApi.obter(id)
                setNovoVinculos((prev) => prev.some((v) => v.id === id) ? prev : [...prev, c])
              }}
              onRemove={(id) => setNovoVinculos(novoVinculos.filter((v) => v.id !== id))}
            />
          </div>
          {criarErro && (
            <p style={{ color: '#b91c1c', fontSize: 13, margin: '4px 0' }}>
              ⚠ {String(criarErro)}
            </p>
          )}
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : clientes.length === 0 ? (
        <p className={styles.empty}>Nenhum cliente cadastrado.</p>
      ) : clientesFiltrados.length === 0 ? (
        <p className={styles.empty}>Nenhum cliente encontrado para "{busca}".</p>
      ) : (
        <div className={cs.lista}>
          {clientesFiltrados.map((c) => (
            <div key={c.id} className={cs.card}>
              <div className={cs.cardRow}>
                <div className={cs.cardInfo}>
                  <span className={cs.nome}>{c.nome}</span>
                  <span className={styles.badge}>{c.tipo}</span>
                  {c.incompleto && <span className={cs.incompleto}>Incompleto</span>}
                  {c.monitorar_diario && (
                    <span className={styles.badge} style={{ background: '#064e3b', color: '#6ee7b7', borderColor: '#065f46' }} title="Nome incluído na busca automática do Diário Oficial">
                      ◎ Diário
                    </span>
                  )}
                  {c.email && <span className={cs.meta}>✉ {c.email}</span>}
                  {c.telefone && <span className={cs.meta}>☏ {c.telefone} <WhatsappBadge cliente={c} /></span>}
                </div>
                <div className={cs.cardActions}>
                  <button
                    className={styles.btnTable}
                    disabled={toggleMonitorar.isPending}
                    title={c.monitorar_diario ? 'Parar de monitorar este cliente no Diário Oficial' : 'Monitorar o nome deste cliente no Diário Oficial'}
                    style={c.monitorar_diario ? { color: '#6ee7b7', borderColor: '#065f46' } : undefined}
                    onClick={() => toggleMonitorar.mutate({ id: c.id, monitorar_diario: !c.monitorar_diario })}
                  >
                    {c.monitorar_diario ? '◎ Monitorando' : '○ Monitorar Diário'}
                  </button>
                  <button className={styles.btnTable}
                    title="Enviar link para o cliente atualizar os próprios dados"
                    onClick={() => setEnviarPara({ id: c.id, nome: c.nome, email: c.email })}>
                    🔗 Enviar link
                  </button>
                  <Link to={`/clientes/${c.id}`} className={styles.btnTable}>Ver</Link>
                  <button className={styles.btnTable}
                    onClick={() => {
                      setEditando(editando === c.id ? null : c.id)
                      setEditForm({
                        nome: c.nome, tipo: c.tipo, cpf_cnpj: c.cpf_cnpj, email: c.email,
                        telefone: c.telefone, whatsapp: c.whatsapp, observacoes: c.observacoes,
                        cep: c.cep, logradouro: c.logradouro, numero: c.numero, complemento: c.complemento,
                        bairro: c.bairro, cidade: c.cidade, uf: c.uf,
                        data_nascimento: isoParaBr(c.data_nascimento), rg: c.rg, nacionalidade: c.nacionalidade, estado_civil: c.estado_civil,
                        profissao: c.profissao, empresas_vinculadas: c.empresas_vinculadas,
                        nome_fantasia: c.nome_fantasia, responsavel_nome: c.responsavel_nome,
                        responsavel_cpf: c.responsavel_cpf, responsavel_email: c.responsavel_email,
                        responsavel_telefone: c.responsavel_telefone,
                      })
                    }}>
                    {editando === c.id ? 'Cancelar' : 'Editar'}
                  </button>
                  <button className={styles.btnDanger}
                    onClick={() => { if (confirm(`Remover ${c.nome}?`)) deletar.mutate(c.id) }}>
                    ×
                  </button>
                </div>
              </div>

              {editando === c.id && (
                <div className={cs.editPanel}>
                  <ClienteFormFields
                    form={editForm as ClienteCreate}
                    onChange={(f) => setEditForm(f)}
                  />
                  <div className={styles.formRow}>
                    <label className={styles.formLabel}>Outras pessoas vinculadas</label>
                    {c.empresas_vinculadas && (
                      <p style={{ fontSize: 12, color: '#64748b', margin: '0 0 6px', whiteSpace: 'pre-wrap' }}>
                        Informado no cadastro: {c.empresas_vinculadas}
                      </p>
                    )}
                    <ClienteVinculos clienteId={c.id} clientes={clientes} onCreateCliente={criarClienteInline} />
                  </div>
                  <button className={styles.btnPrimary} disabled={atualizar.isPending}
                    onClick={() => atualizar.mutate({ id: c.id, data: comDataIso({ ...editForm, incompleto: false }) })}>
                    {atualizar.isPending ? 'Salvando...' : 'Salvar alterações'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
