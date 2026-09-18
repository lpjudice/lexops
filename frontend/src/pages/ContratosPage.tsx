import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contratosApi } from '../api/contratos'
import type { ContratoCreate, SignatarioCreate, PapelSignatario, StatusContrato, GerarPdfRequest, TipoDocumento, GerarProcuracaoRequest, OutorgadoInput, PoderEspecial } from '../api/contratos'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import ComboBox from '../components/ComboBox'
import ClienteCombobox from '../components/ClienteCombobox'
import ContratantesIAModal from '../components/ContratantesIAModal'
import CurrencyInput, { formatBRL } from '../components/CurrencyInput'
import styles from './Page.module.css'
import cs from './ContratosPage.module.css'

const STATUS_LABEL: Record<StatusContrato, string> = {
  rascunho: 'Rascunho',
  aguardando_assinatura: 'Ag. Assinaturas',
  parcialmente_assinado: 'Parc. Assinado',
  assinado: 'Assinado ✓',
  cancelado: 'Cancelado',
}

const PAPEIS: PapelSignatario[] = ['contratante', 'contratado', 'testemunha', 'outro']
const PAPEL_LABEL: Record<PapelSignatario, string> = {
  contratante: 'Contratante', contratado: 'Contratado', testemunha: 'Testemunha', outro: 'Outro',
}

const EMPTY_CONTRATO: ContratoCreate = { cliente_id: '', titulo: '' }
const EMPTY_SIG: SignatarioCreate = { nome: '', email: '', papel: 'outro' }

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('pt-BR')
}

function maskCPFCNPJ(v: string): string {
  const digits = v.replace(/\D/g, '')
  if (digits.length <= 11) {
    return digits
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d{1,2})$/, '$1-$2')
  }
  return digits
    .replace(/(\d{2})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1/$2')
    .replace(/(\d{4})(\d{1,2})$/, '$1-$2')
}

function isoToPortugues(iso: string): string {
  if (!iso) return ''
  const meses = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro']
  const [ano, mes, dia] = iso.split('-').map(Number)
  if (!ano || !mes || !dia) return iso
  return `${dia} de ${meses[mes - 1]} de ${ano}`
}

const OBJETOS_DISPONIVEIS = [
  { key: 'PPS', label: 'PPS — Proteção Patrimonial e Sucessória' },
  { key: 'Personalizado', label: 'Personalizado (texto livre)' },
]

const ENDERECO_ESCRITORIO_PADRAO = 'Av. Desembargador Sampaio, n. 300, Praia do Canto, Vitória/ES - CEP 29.055-250'

const EMPTY_OUTORGADO: OutorgadoInput = { nome: '', oab: '', cpf: '' }

const TIPO_LABEL: Record<TipoDocumento, string> = { contrato: 'Contrato', procuracao: 'Procuração' }
const TIPO_LABEL_PLURAL: Record<TipoDocumento, string> = { contrato: 'Contratos', procuracao: 'Procurações' }

const PODERES_ESPECIAIS_OPCOES: { key: PoderEspecial; label: string }[] = [
  { key: 'confessar', label: 'Confessar' },
  { key: 'desistir', label: 'Desistir' },
  { key: 'transigir', label: 'Transigir' },
  { key: 'firmar_acordos', label: 'Firmar compromissos ou acordos' },
  { key: 'receber_quitacao', label: 'Receber e dar quitação' },
  { key: 'substabelecer', label: 'Substabelecer (com ou sem reserva de poderes)' },
]
const DEFAULT_PODERES_ESPECIAIS: PoderEspecial[] = PODERES_ESPECIAIS_OPCOES.map((o) => o.key)

function camposEmAbertoProcuracao(f: GerarProcuracaoRequest): string[] {
  const faltando: string[] = []
  if (!f.outorgante_estado_civil?.trim()) faltando.push('Estado civil do outorgante')
  if (!f.outorgante_profissao?.trim()) faltando.push('Profissão do outorgante')
  if (!f.outorgante_cpf_cnpj?.trim()) faltando.push('CPF/CNPJ do outorgante')
  if (!f.outorgante_endereco?.trim()) faltando.push('Endereço do outorgante')
  if (!f.outorgante_email?.trim()) faltando.push('E-mail do outorgante')
  f.outorgados.forEach((o) => {
    if (!o.nome.trim()) return
    if (!o.oab?.trim()) faltando.push(`OAB de ${o.nome}`)
    if (!o.cpf?.trim()) faltando.push(`CPF de ${o.nome}`)
  })
  return faltando
}

const EMPTY_GERAR_PROC_FORM: GerarProcuracaoRequest = {
  outorgante_nome: '',
  outorgante_nacionalidade: 'brasileiro(a)',
  outorgante_estado_civil: '',
  outorgante_profissao: '',
  outorgante_cpf_cnpj: '',
  outorgante_endereco: '',
  outorgante_email: '',
  outorgados: [{ nome: 'Lucas Pimenta Júdice', oab: '', cpf: '' }],
  endereco_escritorio: ENDERECO_ESCRITORIO_PADRAO,
  incluir_poderes_gerais: true,
  poderes_especiais: DEFAULT_PODERES_ESPECIAIS,
  poderes_adicionais: '',
  finalidade: '',
  data_validade: '',
  data_procuracao: new Date().toISOString().slice(0, 10),
}

export default function ContratosPage() {
  const qc = useQueryClient()
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({})
  const autoSyncRef = useRef<Set<string>>(new Set())

  const [showForm, setShowForm] = useState(false)
  const [abaTipo, setAbaTipo] = useState<TipoDocumento>('contrato')
  const [filtroStatus, setFiltroStatus] = useState<StatusContrato | ''>('')
  const [editandoTitulo, setEditandoTitulo] = useState<string | null>(null)
  const [editTitulo, setEditTitulo] = useState('')
  const [editDescricao, setEditDescricao] = useState('')
  const [form, setForm] = useState<ContratoCreate>(EMPTY_CONTRATO)
  const [expandido, setExpandido] = useState<string | null>(null)
  const [sigForms, setSigForms] = useState<Record<string, SignatarioCreate>>({})
  const [gerarAberto, setGerarAberto] = useState<string | null>(null)
  const [gerarProcAberto, setGerarProcAberto] = useState<string | null>(null)
  const [lerIAFor, setLerIAFor] = useState<string | null>(null)
  const [gerarProcErro, setGerarProcErro] = useState<string | null>(null)
  const [gerarProcForm, setGerarProcForm] = useState<GerarProcuracaoRequest>(EMPTY_GERAR_PROC_FORM)
  const [poderesPanelOpen, setPoderesPanelOpen] = useState(false)
  const [gerarForm, setGerarForm] = useState<GerarPdfRequest>({
    contratante_nome: '',
    contratante_qualificacao: '',
    contratante_cpf_cnpj: '',
    contratante_endereco: '',
    contratante_email: '',
    objeto_tipo: 'PPS',
    objeto_texto_livre: '',
    valor_honorarios: '',
    valor_honorarios_num: null,
    valor_causa: null,
    data_vencimento: '',
    condicao_pagamento: '',
    percentual_exito: '15%',
    percentual_exito_num: null,
    data_contrato: new Date().toISOString().slice(0, 10),
  })

  const { data: contratos = [], isLoading } = useQuery({
    queryKey: ['contratos'],
    queryFn: () => contratosApi.listar(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })
  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })
  const { data: pastaMestra } = useQuery({
    queryKey: ['contratos-pasta-mestra', abaTipo],
    queryFn: () => contratosApi.pastaMestra(abaTipo),
  })

  const criar = useMutation({
    mutationFn: contratosApi.criar,
    onSuccess: (novo) => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      setShowForm(false)
      setForm(EMPTY_CONTRATO)
      setExpandido(novo.id)
    },
  })

  const uploadPdfs = useMutation({
    mutationFn: ({ id, files }: { id: string; files: File[] }) => contratosApi.uploadPdfs(id, files),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contratos'] }),
  })

  const removerArquivo = useMutation({
    mutationFn: ({ id, filename }: { id: string; filename: string }) =>
      contratosApi.removerArquivo(id, filename),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contratos'] }),
  })

  const [gerarErro, setGerarErro] = useState<string | null>(null)

  const gerarPdf = useMutation({
    mutationFn: ({ id, data }: { id: string; data: GerarPdfRequest }) =>
      contratosApi.gerarPdf(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      setGerarAberto(null)
      setGerarErro(null)
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setGerarErro(detail || 'Erro ao gerar PDF. Verifique o console.')
    },
  })

  const gerarProcuracao = useMutation({
    mutationFn: ({ id, data }: { id: string; data: GerarProcuracaoRequest }) =>
      contratosApi.gerarProcuracao(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      setGerarProcAberto(null)
      setGerarProcErro(null)
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setGerarProcErro(detail || 'Erro ao gerar PDF. Verifique o console.')
    },
  })

  const adicionarSig = useMutation({
    mutationFn: ({ id, data }: { id: string; data: SignatarioCreate }) =>
      contratosApi.adicionarSignatario(id, data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      setSigForms((prev) => ({ ...prev, [vars.id]: EMPTY_SIG }))
    },
  })

  const removerSig = useMutation({
    mutationFn: ({ cid, sid }: { cid: string; sid: string }) =>
      contratosApi.removerSignatario(cid, sid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contratos'] }),
  })

  const lembrarSig = useMutation({
    mutationFn: ({ cid, sid }: { cid: string; sid: string }) =>
      contratosApi.lembrarSignatario(cid, sid),
    onSuccess: () => alert('Lembrete enviado.'),
    onError: (e: any) => alert(`Erro ao enviar lembrete:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`),
  })

  const enviar = useMutation({
    mutationFn: (id: string) => contratosApi.enviar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contratos'] }),
    onError: (e: any) => alert(`Erro ao enviar para ClickSign:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`),
  })

  const cancelar = useMutation({
    mutationFn: (id: string) => contratosApi.cancelar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contratos'] }),
  })

  const confirmarAssinatura = useMutation({
    mutationFn: (id: string) => contratosApi.confirmarAssinatura(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['honorarios-pendentes-assinatura'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
    },
  })

  const finalizarManual = useMutation({
    mutationFn: (id: string) => contratosApi.finalizarAssinadoManual(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['honorarios-pendentes-assinatura'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
    },
    onError: (e: any) => alert(`Erro ao finalizar contrato:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`),
  })

  const deletar = useMutation({
    mutationFn: (id: string) => contratosApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contratos'] }),
  })

  const atualizarContrato = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { titulo: string; descricao?: string } }) =>
      contratosApi.atualizar(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      setEditandoTitulo(null)
    },
    onError: (e: any) => alert(`Erro ao salvar:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`),
  })

  const sincronizar = useMutation({
    mutationFn: ({ id }: { id: string; manual: boolean }) => contratosApi.sincronizarStatus(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contratos'] })
      qc.invalidateQueries({ queryKey: ['honorarios'] })
      qc.invalidateQueries({ queryKey: ['honorarios-pendentes-assinatura'] })
      qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
    },
    onError: (e: any, vars) => {
      // Só alerta quando o usuário clicou explicitamente; o auto-sync ao abrir falha em silêncio.
      if (vars.manual)
        alert(`Erro ao atualizar status no ClickSign:\n${e?.response?.data?.detail || e?.message || 'Erro desconhecido'}`)
    },
  })

  const clientePorId = (cid: string) => clientes.find((c) => c.id === cid)

  // Cria um cliente "só com o nome" direto do combobox quando o nome digitado não existe.
  // Marca incompleto=true (pendente de revisão) — mesmo padrão de Processos/Tarefas.
  const criarCliente = async (raw: string): Promise<string> => {
    const [nome, tipo] = raw.split('|')
    const c = await clientesApi.criar({ nome, tipo: (tipo as 'PF' | 'PJ') ?? 'PF', incompleto: true })
    qc.invalidateQueries({ queryKey: ['clientes'] })
    return c.id
  }

  // Sincroniza automaticamente ao abrir um contrato em andamento (uma vez por sessão).
  const toggleExpandido = (c: (typeof contratos)[0]) => {
    const abrindo = expandido !== c.id
    setExpandido(abrindo ? c.id : null)
    if (
      abrindo &&
      c.clicksign_document_key &&
      ['aguardando_assinatura', 'parcialmente_assinado'].includes(c.status) &&
      !autoSyncRef.current.has(c.id)
    ) {
      autoSyncRef.current.add(c.id)
      sincronizar.mutate({ id: c.id, manual: false })
    }
  }

  const abrirGerar = (cid: string, clienteId: string) => {
    const cliente = clientePorId(clienteId)
    setGerarForm({
      contratante_nome: cliente?.nome || '',
      contratante_qualificacao: '',
      contratante_cpf_cnpj: cliente?.cpf_cnpj || '',
      contratante_endereco: '',
      contratante_email: cliente?.email || '',
      objeto_tipo: 'PPS',
      objeto_texto_livre: '',
      valor_honorarios: '',
      valor_honorarios_num: null,
      valor_causa: null,
      data_vencimento: '',
      condicao_pagamento: '',
      percentual_exito: '15%',
      percentual_exito_num: null,
      data_contrato: new Date().toISOString().slice(0, 10),
    })
    setGerarAberto(cid)
  }

  const abrirGerarProcuracao = (c: (typeof contratos)[0]) => {
    if (c.procuracao_dados) {
      // Editando: reabre com os dados exatos da última geração (não os do cadastro do cliente).
      setGerarProcForm({ ...EMPTY_GERAR_PROC_FORM, ...c.procuracao_dados })
    } else {
      const cliente = clientePorId(c.cliente_id)
      setGerarProcForm({
        ...EMPTY_GERAR_PROC_FORM,
        outorgante_nome: cliente?.nome || '',
        outorgante_cpf_cnpj: cliente?.cpf_cnpj || '',
        outorgante_email: cliente?.email || '',
        outorgante_endereco: cliente?.endereco || '',
        outorgante_estado_civil: cliente?.estado_civil || '',
        outorgante_profissao: cliente?.profissao || '',
      })
    }
    setGerarProcErro(null)
    setPoderesPanelOpen(false)
    setGerarProcAberto(c.id)
  }

  const adicionarContratadoAutomatico = (cid: string) => {
    adicionarSig.mutate({
      id: cid,
      data: { nome: 'Lucas Pimenta Júdice', email: 'pj@pimentajudice.com.br', papel: 'contratado' },
    })
  }

  const adicionarClienteComoContratante = (cid: string, clienteId: string) => {
    const cliente = clientePorId(clienteId)
    if (!cliente?.email) return
    adicionarSig.mutate({
      id: cid,
      data: { nome: cliente.nome, email: cliente.email, papel: 'contratante' },
    })
  }

  const adicionarTestemunhaMonielly = (cid: string) => {
    adicionarSig.mutate({
      id: cid,
      data: { nome: 'Monielly Moreira Vieira', email: 'moni@pimentajudice.com.br', papel: 'testemunha' },
    })
  }

  const temArquivos = (c: (typeof contratos)[0]) =>
    (c.arquivos?.length ?? 0) > 0 || !!c.arquivo_path

  const contratosDaAba = contratos.filter((c) => c.tipo_documento === abaTipo)
  const contratosFiltrados = filtroStatus
    ? contratosDaAba.filter((c) => c.status === filtroStatus)
    : contratosDaAba

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>{TIPO_LABEL_PLURAL[abaTipo]}</h1>
        <div className={cs.headerActions}>
          {pastaMestra?.link && (
            <a href={pastaMestra.link} target="_blank" rel="noreferrer" className={cs.btnDrive}>
              ☁ Pasta mestra de {TIPO_LABEL_PLURAL[abaTipo]}
            </a>
          )}
          <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancelar' : `+ Novo${abaTipo === 'procuracao' ? 'a' : ''} ${TIPO_LABEL[abaTipo]}`}
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['contrato', 'procuracao'] as TipoDocumento[]).map((t) => (
          <button
            key={t}
            onClick={() => { setAbaTipo(t); setFiltroStatus(''); setShowForm(false) }}
            style={{
              padding: '6px 16px',
              borderRadius: 8,
              border: '1px solid #e5e7eb',
              background: abaTipo === t ? '#1d1e20' : '#fff',
              color: abaTipo === t ? '#fff' : '#1d1e20',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {TIPO_LABEL_PLURAL[t]}
          </button>
        ))}
      </div>

      {showForm && (
        <form onSubmit={(e) => { e.preventDefault(); if (!form.cliente_id) { alert('Selecione ou crie um cliente'); return } criar.mutate({ ...form, tipo_documento: abaTipo }) }} className={styles.form}>
          <div className={cs.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Título *</label>
              <input className={styles.input} value={form.titulo}
                onChange={(e) => setForm({ ...form, titulo: e.target.value })} required />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Cliente *</label>
              <ClienteCombobox
                value={form.cliente_id}
                onChange={(v) => setForm({ ...form, cliente_id: v })}
                clientes={clientes}
                onCreateCliente={criarCliente}
              />
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Processo (opcional)</label>
            <ComboBox
              options={processos.map((p) => {
                const cl = clientes.find((c) => c.id === p.cliente_id)
                return { value: p.id, label: p.numero_cnj, sublabel: cl ? `Cliente: ${cl.nome}` : undefined }
              })}
              value={form.processo_id ?? ''}
              onChange={(v) => setForm({ ...form, processo_id: v || undefined })}
              placeholder="Buscar por CNJ ou cliente..."
            />
          </div>
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Salvando...' : 'Criar Contrato'}
          </button>
        </form>
      )}

      {contratosDaAba.length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          {(['', ...Object.keys(STATUS_LABEL)] as (StatusContrato | '')[]).map((s) => {
            const count = s === '' ? contratosDaAba.length : contratosDaAba.filter((c) => c.status === s).length
            return (
              <button
                key={s || 'todos'}
                onClick={() => setFiltroStatus(s)}
                style={{
                  padding: '4px 12px',
                  borderRadius: 999,
                  border: '1px solid #e5e7eb',
                  background: filtroStatus === s ? '#7c3aed' : '#f3f4f6',
                  color: filtroStatus === s ? '#fff' : '#6b7280',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {s === '' ? 'Todos' : STATUS_LABEL[s]} ({count})
              </button>
            )
          })}
        </div>
      )}

      {isLoading ? <p className={styles.empty}>Carregando...</p> :
       contratosDaAba.length === 0 ? <p className={styles.empty}>Nenhum{abaTipo === 'procuracao' ? 'a' : ''} {TIPO_LABEL[abaTipo].toLowerCase()} cadastrad{abaTipo === 'procuracao' ? 'a' : 'o'}.</p> :
       contratosFiltrados.length === 0 ? <p className={styles.empty}>Nenhum{abaTipo === 'procuracao' ? 'a' : ''} {TIPO_LABEL[abaTipo].toLowerCase()} com esse status.</p> : (
        <div className={cs.lista}>
          {contratosFiltrados.map((c) => {
            const isOpen = expandido === c.id
            const sf = sigForms[c.id] ?? EMPTY_SIG
            const cliente = clientePorId(c.cliente_id)
            const arquivos = c.arquivos?.length > 0
              ? c.arquivos
              : c.arquivo_path ? [{ filename: 'contrato.pdf', path: c.arquivo_path }] : []

            return (
              <div key={c.id} className={cs.card}>
                {/* Cabeçalho */}
                <div className={cs.cardTop}>
                  <div style={{ flex: 1 }}>
                    {editandoTitulo === c.id ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 480 }}>
                        <input className={styles.input} value={editTitulo}
                          onChange={(e) => setEditTitulo(e.target.value)}
                          placeholder="Título do contrato" autoFocus />
                        <textarea className={styles.input} rows={2} value={editDescricao}
                          onChange={(e) => setEditDescricao(e.target.value)}
                          placeholder="Descrição (opcional)" />
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className={styles.btnPrimary} style={{ padding: '5px 14px', fontSize: 12 }}
                            disabled={!editTitulo.trim() || atualizarContrato.isPending}
                            onClick={() => atualizarContrato.mutate({
                              id: c.id,
                              data: { titulo: editTitulo.trim(), descricao: editDescricao.trim() || undefined },
                            })}>
                            {atualizarContrato.isPending ? 'Salvando...' : 'Salvar'}
                          </button>
                          <button className={styles.btnTable} onClick={() => setEditandoTitulo(null)}>
                            Cancelar
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div className={cs.cardTitulo}>{c.titulo}</div>
                        <button className={cs.btnExpand} title="Editar nome/descrição"
                          onClick={() => {
                            setEditandoTitulo(c.id)
                            setEditTitulo(c.titulo)
                            setEditDescricao(c.descricao ?? '')
                          }}>
                          ✎
                        </button>
                      </div>
                    )}
                    <div className={cs.cardMeta}>
                      {cliente?.nome ?? '—'} · {formatDate(c.created_at)}
                      {c.descricao && editandoTitulo !== c.id && ` · ${c.descricao}`}
                    </div>
                  </div>
                  <div className={cs.cardActions}>
                    <span className={`${cs.statusBadge} ${cs[`status_${c.status}`]}`}>
                      {STATUS_LABEL[c.status]}
                    </span>
                    {c.assinatura_manual && (
                      <span className={cs.badgeManual}>Ass. Manual</span>
                    )}
                    <button className={cs.btnExpand}
                      onClick={() => toggleExpandido(c)}>
                      {isOpen ? '▲' : '▼'}
                    </button>
                    <button className={styles.btnDanger}
                      onClick={() => { if (confirm('Remover contrato?')) deletar.mutate(c.id) }}>
                      ×
                    </button>
                  </div>
                </div>

                {isOpen && (
                  <div className={cs.cardBody}>
                    {/* ── ARQUIVOS ────────────────────────────────────── */}
                    <div className={cs.section}>
                      <div className={cs.sectionHeader}>
                        <span className={cs.sectionTitle}>Documentos PDF</span>
                        <div className={cs.sectionActions}>
                          {c.status === 'rascunho' && c.tipo_documento === 'contrato' && (
                            <button className={cs.btnSmall}
                              onClick={() => abrirGerar(c.id, c.cliente_id)}>
                              ✨ Gerar contrato
                            </button>
                          )}
                          {c.status === 'rascunho' && c.tipo_documento === 'procuracao' && (
                            <button className={cs.btnSmall}
                              onClick={() => abrirGerarProcuracao(c)}>
                              {c.doc_gerado_filename ? '✏️ Editar procuração' : '✨ Gerar procuração'}
                            </button>
                          )}
                          <label className={cs.btnSmall}>
                            ↑ Upload
                            <input
                              ref={(el) => { fileRefs.current[c.id] = el }}
                              type="file" accept=".pdf" multiple style={{ display: 'none' }}
                              onChange={(e) => {
                                const files = Array.from(e.target.files ?? [])
                                if (files.length) uploadPdfs.mutate({ id: c.id, files })
                                if (fileRefs.current[c.id]) fileRefs.current[c.id]!.value = ''
                              }}
                            />
                          </label>
                          {temArquivos(c) && (
                            <button className={cs.btnSmall}
                              onClick={() => setLerIAFor(c.id)}
                              title="A IA lê o PDF e popula/atualiza o cadastro dos contratantes">
                              🔎 Ler contratantes (IA)
                            </button>
                          )}
                        </div>
                      </div>

                      {arquivos.length === 0 ? (
                        <p className={cs.hint}>Nenhum arquivo. Gere o contrato ou faça upload de um PDF.</p>
                      ) : (
                        <ul className={cs.arquivoList}>
                          {arquivos.map((arq) => (
                            <li key={arq.filename} className={cs.arquivoItem}>
                              <a
                                href={arq.drive_link || contratosApi.verArquivoUrl(c.id, arq.filename)}
                                target="_blank" rel="noreferrer"
                                className={cs.arquivoLink}
                              >
                                📄 {arq.filename}
                              </a>
                              {arq.drive_link && <span className={cs.arquivoNome}>Drive</span>}
                              {arq.docs_link && (
                                <a href={arq.docs_link} target="_blank" rel="noreferrer" className={cs.arquivoNome}
                                  title="Cópia editável — não sincroniza de volta com o PDF. Se alterar aqui, baixe como PDF no Google Docs e substitua o anexo (remova este e faça upload do novo).">
                                  📝 Editar no Google Docs
                                </a>
                              )}
                              {c.status === 'rascunho' && (
                                <button className={cs.btnRemove}
                                  onClick={() => {
                                    if (confirm(`Remover ${arq.filename}?`))
                                      removerArquivo.mutate({ id: c.id, filename: arq.filename })
                                  }}>
                                  ×
                                </button>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}

                      {c.arquivo_assinado_path && (
                        <a href={contratosApi.downloadAssinadoUrl(c.id)}
                          className={cs.btnDownload} target="_blank" rel="noreferrer">
                          ⬇ Baixar versão assinada
                        </a>
                      )}
                      {(c.drive_link_cliente || c.drive_link_master) && (
                        <div className={cs.driveLinks}>
                          {c.drive_link_cliente && (
                            <a href={c.drive_link_cliente} target="_blank" rel="noreferrer" className={cs.btnDrive}>
                              ☁ Ver no Drive (pasta do cliente)
                            </a>
                          )}
                          {c.drive_link_master && (
                            <a href={c.drive_link_master} target="_blank" rel="noreferrer" className={cs.btnDrive}>
                              ☁ Ver na pasta mestra
                            </a>
                          )}
                        </div>
                      )}
                    </div>

                    {/* ── GERAR CONTRATO FORM ──────────────────────────── */}
                    {gerarAberto === c.id && (
                      <div className={cs.gerarForm}>
                        <div className={cs.sectionTitle}>✨ Gerar PDF do Contrato</div>
                        <div className={cs.twoCol}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Nome do contratante *</label>
                            <input className={styles.input} value={gerarForm.contratante_nome}
                              onChange={(e) => setGerarForm({ ...gerarForm, contratante_nome: e.target.value })} />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Qualificação</label>
                            <input className={styles.input} placeholder="ex: brasileira, empresária, divorciada"
                              value={gerarForm.contratante_qualificacao}
                              onChange={(e) => setGerarForm({ ...gerarForm, contratante_qualificacao: e.target.value })} />
                          </div>
                        </div>
                        <div className={cs.twoCol}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>CPF / CNPJ</label>
                            <input className={styles.input} value={gerarForm.contratante_cpf_cnpj}
                              onChange={(e) => setGerarForm({ ...gerarForm, contratante_cpf_cnpj: maskCPFCNPJ(e.target.value) })} />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>E-mail</label>
                            <input type="email" className={styles.input} value={gerarForm.contratante_email}
                              onChange={(e) => setGerarForm({ ...gerarForm, contratante_email: e.target.value })} />
                          </div>
                        </div>
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Endereço</label>
                          <input className={styles.input} value={gerarForm.contratante_endereco}
                            onChange={(e) => setGerarForm({ ...gerarForm, contratante_endereco: e.target.value })} />
                        </div>
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Objeto do contrato</label>
                          <div className={cs.chipRow}>
                            {OBJETOS_DISPONIVEIS.map((o) => (
                              <button key={o.key} type="button"
                                className={`${cs.chip} ${gerarForm.objeto_tipo === o.key ? cs.chipAtivo : ''}`}
                                onClick={() => setGerarForm({ ...gerarForm, objeto_tipo: o.key })}>
                                {o.label}
                              </button>
                            ))}
                          </div>
                          {gerarForm.objeto_tipo === 'Personalizado' && (
                            <textarea className={styles.input} rows={6} style={{ marginTop: '8px' }}
                              placeholder="Digite o texto da Cláusula Primeira..."
                              value={gerarForm.objeto_texto_livre}
                              onChange={(e) => setGerarForm({ ...gerarForm, objeto_texto_livre: e.target.value })} />
                          )}
                        </div>
                        <div className={cs.twoCol}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Honorários (valor)</label>
                            <CurrencyInput
                              className={styles.input}
                              value={gerarForm.valor_honorarios ? parseFloat(gerarForm.valor_honorarios.replace(/\./g, '').replace(',', '.')) || 0 : 0}
                              onChange={(v) => setGerarForm({ ...gerarForm, valor_honorarios: v > 0 ? formatBRL(v) : '', valor_honorarios_num: v > 0 ? v : null })}
                              placeholder="0,00"
                            />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Data de vencimento</label>
                            <input type="date" className={styles.input}
                              value={gerarForm.data_vencimento}
                              onChange={(e) => setGerarForm({ ...gerarForm, data_vencimento: e.target.value })} />
                          </div>
                        </div>
                        <div className={cs.twoCol}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Condição de pagamento</label>
                            <input className={styles.input} placeholder="ex: em parcela única"
                              value={gerarForm.condicao_pagamento}
                              onChange={(e) => setGerarForm({ ...gerarForm, condicao_pagamento: e.target.value })} />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>% Êxito</label>
                            <input className={styles.input} placeholder="15%"
                              value={gerarForm.percentual_exito}
                              onChange={(e) => {
                                const pct = parseFloat(e.target.value) || 0
                                setGerarForm({
                                  ...gerarForm,
                                  percentual_exito: e.target.value,
                                  percentual_exito_num: pct,
                                })
                              }} />
                            {(gerarForm.percentual_exito === '0%' || gerarForm.percentual_exito === '0') && (
                              <span style={{ fontSize: 11, color: '#6b7280', marginTop: 3 }}>
                                → será escrito como: <em>não haverá êxito</em>
                              </span>
                            )}
                          </div>
                        </div>
                        {gerarForm.percentual_exito && gerarForm.percentual_exito !== '0%' && gerarForm.percentual_exito !== '0' && (
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Valor da causa (R$) — para cálculo de êxito</label>
                            <CurrencyInput
                              className={styles.input}
                              value={gerarForm.valor_causa ?? 0}
                              onChange={(v) => setGerarForm({ ...gerarForm, valor_causa: v || null })}
                              placeholder="Valor estimado da causa"
                            />
                            {gerarForm.valor_causa && gerarForm.valor_causa > 0 && gerarForm.percentual_exito_num && (
                              <span style={{ fontSize: 11, color: '#6b7280', marginTop: 3 }}>
                                Êxito estimado: {((gerarForm.valor_causa * (gerarForm.percentual_exito_num / 100))).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                              </span>
                            )}
                          </div>
                        )}
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Data do contrato</label>
                          <input type="date" className={styles.input} value={gerarForm.data_contrato}
                            onChange={(e) => setGerarForm({ ...gerarForm, data_contrato: e.target.value })} />
                        </div>
                        {gerarErro && (
                          <div style={{ color: '#b91c1c', background: '#fee2e2', border: '1px solid #fecaca', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                            ❌ {gerarErro}
                          </div>
                        )}
                        <div className={cs.gerarAcoes}>
                          <button className={styles.btnPrimary}
                            disabled={gerarPdf.isPending || !gerarForm.contratante_nome}
                            onClick={() => {
                              const exito = (gerarForm.percentual_exito === '0%' || gerarForm.percentual_exito === '0')
                                ? 'não haverá êxito'
                                : gerarForm.percentual_exito
                              gerarPdf.mutate({
                                id: c.id,
                                data: {
                                  ...gerarForm,
                                  data_vencimento: isoToPortugues(gerarForm.data_vencimento || '') || gerarForm.data_vencimento,
                                  percentual_exito: exito,
                                },
                              })
                            }}>
                            {gerarPdf.isPending ? '⏳ Gerando...' : '📄 Gerar e anexar PDF'}
                          </button>
                          <button className={styles.btnTable} onClick={() => setGerarAberto(null)}>Fechar</button>
                        </div>
                      </div>
                    )}

                    {/* ── GERAR PROCURAÇÃO FORM ────────────────────────── */}
                    {gerarProcAberto === c.id && (
                      <div className={cs.gerarForm}>
                        <div className={cs.sectionTitle}>✨ Gerar PDF da Procuração</div>

                        <div className={cs.sectionTitle} style={{ fontSize: 12, marginTop: 4 }}>Outorgante (cliente)</div>
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Nome do outorgante *</label>
                          <input className={styles.input} value={gerarProcForm.outorgante_nome}
                            onChange={(e) => setGerarProcForm({ ...gerarProcForm, outorgante_nome: e.target.value })} />
                        </div>
                        <div className={cs.twoCol} style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Nacionalidade</label>
                            <input className={styles.input}
                              value={gerarProcForm.outorgante_nacionalidade}
                              onChange={(e) => setGerarProcForm({ ...gerarProcForm, outorgante_nacionalidade: e.target.value })} />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Estado civil</label>
                            <input className={styles.input} placeholder="ex: casado(a)"
                              value={gerarProcForm.outorgante_estado_civil}
                              onChange={(e) => setGerarProcForm({ ...gerarProcForm, outorgante_estado_civil: e.target.value })} />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Profissão</label>
                            <input className={styles.input} placeholder="ex: empresário(a)"
                              value={gerarProcForm.outorgante_profissao}
                              onChange={(e) => setGerarProcForm({ ...gerarProcForm, outorgante_profissao: e.target.value })} />
                          </div>
                        </div>
                        <div className={cs.twoCol}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>CPF / CNPJ</label>
                            <input className={styles.input} value={gerarProcForm.outorgante_cpf_cnpj}
                              onChange={(e) => setGerarProcForm({ ...gerarProcForm, outorgante_cpf_cnpj: maskCPFCNPJ(e.target.value) })} />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>E-mail</label>
                            <input type="email" className={styles.input} value={gerarProcForm.outorgante_email}
                              onChange={(e) => setGerarProcForm({ ...gerarProcForm, outorgante_email: e.target.value })} />
                          </div>
                        </div>
                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Endereço (residencial/sede)</label>
                          <input className={styles.input} value={gerarProcForm.outorgante_endereco}
                            onChange={(e) => setGerarProcForm({ ...gerarProcForm, outorgante_endereco: e.target.value })} />
                        </div>

                        <div className={cs.sectionTitle} style={{ fontSize: 12, marginTop: 12 }}>Outorgado(s) — advogado(s)</div>
                        {gerarProcForm.outorgados.map((adv, i) => (
                          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6, alignItems: 'center' }}>
                            <input className={styles.input} placeholder="Nome do advogado" style={{ flex: 2 }}
                              value={adv.nome}
                              onChange={(e) => {
                                const outorgados = [...gerarProcForm.outorgados]
                                outorgados[i] = { ...outorgados[i], nome: e.target.value }
                                setGerarProcForm({ ...gerarProcForm, outorgados })
                              }} />
                            <input className={styles.input} placeholder="OAB" style={{ flex: 1 }}
                              value={adv.oab}
                              onChange={(e) => {
                                const outorgados = [...gerarProcForm.outorgados]
                                outorgados[i] = { ...outorgados[i], oab: e.target.value }
                                setGerarProcForm({ ...gerarProcForm, outorgados })
                              }} />
                            <input className={styles.input} placeholder="CPF" style={{ flex: 1 }}
                              value={adv.cpf}
                              onChange={(e) => {
                                const outorgados = [...gerarProcForm.outorgados]
                                outorgados[i] = { ...outorgados[i], cpf: maskCPFCNPJ(e.target.value) }
                                setGerarProcForm({ ...gerarProcForm, outorgados })
                              }} />
                            {gerarProcForm.outorgados.length > 1 && (
                              <button className={styles.btnDanger} type="button"
                                onClick={() => setGerarProcForm({
                                  ...gerarProcForm,
                                  outorgados: gerarProcForm.outorgados.filter((_, idx) => idx !== i),
                                })}>
                                ×
                              </button>
                            )}
                          </div>
                        ))}
                        <button className={cs.btnAtalho} type="button" style={{ marginBottom: 8 }}
                          onClick={() => setGerarProcForm({
                            ...gerarProcForm,
                            outorgados: [...gerarProcForm.outorgados, { ...EMPTY_OUTORGADO }],
                          })}>
                          + Adicionar outorgado
                        </button>

                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>Endereço profissional (escritório)</label>
                          <input className={styles.input} value={gerarProcForm.endereco_escritorio}
                            onChange={(e) => setGerarProcForm({ ...gerarProcForm, endereco_escritorio: e.target.value })} />
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 }}>
                          <span className={cs.sectionTitle} style={{ fontSize: 12 }}>Poderes</span>
                          <button className={cs.btnAtalho} type="button" onClick={() => setPoderesPanelOpen((v) => !v)}>
                            ⚙️ Configurar poderes
                          </button>
                        </div>

                        {poderesPanelOpen && (
                          <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, marginBottom: 8, background: '#fafafa' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                              <input type="checkbox" checked={gerarProcForm.incluir_poderes_gerais}
                                onChange={(e) => setGerarProcForm({ ...gerarProcForm, incluir_poderes_gerais: e.target.checked })} />
                              Incluir cláusula geral "ad judicia et extra"
                            </label>

                            {gerarProcForm.incluir_poderes_gerais ? (
                              <>
                                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>
                                  Poderes especiais a manter na cláusula:
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10 }}>
                                  {PODERES_ESPECIAIS_OPCOES.map((op) => (
                                    <label key={op.key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                                      <input type="checkbox"
                                        checked={gerarProcForm.poderes_especiais?.includes(op.key) ?? false}
                                        onChange={(e) => {
                                          const atuais = gerarProcForm.poderes_especiais ?? []
                                          const poderes_especiais = e.target.checked
                                            ? [...atuais, op.key]
                                            : atuais.filter((k) => k !== op.key)
                                          setGerarProcForm({ ...gerarProcForm, poderes_especiais })
                                        }} />
                                      {op.label}
                                    </label>
                                  ))}
                                </div>
                                <label className={styles.formLabel}>Poderes adicionais (entram na mesma frase, além dos marcados acima)</label>
                                <textarea className={styles.input} rows={2}
                                  placeholder="ex: representar perante o INSS"
                                  value={gerarProcForm.poderes_adicionais}
                                  onChange={(e) => setGerarProcForm({ ...gerarProcForm, poderes_adicionais: e.target.value })} />
                              </>
                            ) : (
                              <div style={{ fontSize: 12, color: '#6b7280' }}>
                                Cláusula geral desligada — a procuração terá só os poderes descritos em "Finalidade específica" abaixo.
                              </div>
                            )}
                          </div>
                        )}

                        <div className={styles.formRow}>
                          <label className={styles.formLabel}>
                            {gerarProcForm.incluir_poderes_gerais
                              ? 'Finalidade específica (opcional — some à cláusula geral acima)'
                              : 'Poderes específicos (obrigatório — cláusula geral está desligada)'}
                          </label>
                          <textarea className={styles.input} rows={3}
                            placeholder="ex: representar o outorgante especificamente no processo nº..."
                            value={gerarProcForm.finalidade}
                            onChange={(e) => setGerarProcForm({ ...gerarProcForm, finalidade: e.target.value })} />
                        </div>
                        <div className={cs.twoCol}>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Data da procuração</label>
                            <input type="date" className={styles.input} value={gerarProcForm.data_procuracao}
                              onChange={(e) => setGerarProcForm({ ...gerarProcForm, data_procuracao: e.target.value })} />
                          </div>
                          <div className={styles.formRow}>
                            <label className={styles.formLabel}>Válida até (opcional — se vazio, não fala em prazo)</label>
                            <input type="date" className={styles.input} value={gerarProcForm.data_validade}
                              onChange={(e) => setGerarProcForm({ ...gerarProcForm, data_validade: e.target.value })} />
                          </div>
                        </div>
                        {gerarProcErro && (
                          <div style={{ color: '#b91c1c', background: '#fee2e2', border: '1px solid #fecaca', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                            ❌ {gerarProcErro}
                          </div>
                        )}
                        <div className={cs.gerarAcoes}>
                          <button className={styles.btnPrimary}
                            disabled={
                              gerarProcuracao.isPending || !gerarProcForm.outorgante_nome ||
                              !gerarProcForm.outorgados.some((o) => o.nome.trim()) ||
                              (!gerarProcForm.incluir_poderes_gerais && !gerarProcForm.finalidade?.trim())
                            }
                            onClick={() => {
                              const faltando = camposEmAbertoProcuracao(gerarProcForm)
                              if (faltando.length > 0) {
                                const prosseguir = confirm(
                                  `Campos em aberto:\n- ${faltando.join('\n- ')}\n\nDeseja gerar a procuração mesmo assim?`
                                )
                                if (!prosseguir) return
                              }
                              gerarProcuracao.mutate({ id: c.id, data: gerarProcForm })
                            }}>
                            {gerarProcuracao.isPending ? '⏳ Gerando...' : '📄 Gerar e anexar PDF'}
                          </button>
                          <button className={styles.btnTable} onClick={() => setGerarProcAberto(null)}>Fechar</button>
                        </div>
                      </div>
                    )}

                    {/* ── SIGNATÁRIOS ─────────────────────────────────── */}
                    <div className={cs.section}>
                      <div className={cs.sectionTitle}>Signatários</div>

                      {/* Botões de atalho */}
                      {c.status === 'rascunho' && (
                        <div className={cs.sigAtalhos}>
                          <button className={cs.btnAtalho}
                            onClick={() => adicionarContratadoAutomatico(c.id)}>
                            + Lucas Júdice (Contratado)
                          </button>
                          {cliente?.email && (
                            <button className={cs.btnAtalho}
                              onClick={() => adicionarClienteComoContratante(c.id, c.cliente_id)}>
                              + {cliente.nome} (Contratante)
                            </button>
                          )}
                          <button className={cs.btnAtalho}
                            onClick={() => adicionarTestemunhaMonielly(c.id)}>
                            + Monielly Moreira Vieira (Testemunha)
                          </button>
                        </div>
                      )}

                      {c.signatarios.length > 0 && (
                        <table className={cs.sigTable}>
                          <thead>
                            <tr><th>Nome</th><th>Email</th><th>Papel</th><th>Status</th><th></th></tr>
                          </thead>
                          <tbody>
                            {c.signatarios.map((s) => (
                              <tr key={s.id}>
                                <td>{s.nome}</td>
                                <td>{s.email}</td>
                                <td>{PAPEL_LABEL[s.papel as PapelSignatario] || s.papel}</td>
                                <td>
                                  <span className={`${cs.sigStatus} ${cs[`sig_${s.status_assinatura}`]}`}>
                                    {s.status_assinatura === 'pendente' ? 'Pendente' :
                                     s.status_assinatura === 'assinado' ? '✓ Assinado' : 'Recusado'}
                                  </span>
                                </td>
                                <td style={{ display: 'flex', gap: 4 }}>
                                  {s.status_assinatura === 'pendente' &&
                                    ['aguardando_assinatura', 'parcialmente_assinado'].includes(c.status) && (
                                    <button className={styles.btnTable} title="Reenviar e-mail de assinatura"
                                      disabled={lembrarSig.isPending}
                                      onClick={() => lembrarSig.mutate({ cid: c.id, sid: s.id })}>
                                      🔔 Lembrar
                                    </button>
                                  )}
                                  {c.status === 'rascunho' && (
                                    <button className={styles.btnDanger}
                                      onClick={() => removerSig.mutate({ cid: c.id, sid: s.id })}>
                                      ×
                                    </button>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}

                      {c.status === 'rascunho' && (
                        <div className={cs.sigForm}>
                          <input className={styles.input} placeholder="Nome"
                            value={sf.nome}
                            onChange={(e) => setSigForms({ ...sigForms, [c.id]: { ...sf, nome: e.target.value } })} />
                          <input className={styles.input} placeholder="Email" type="email"
                            value={sf.email}
                            onChange={(e) => setSigForms({ ...sigForms, [c.id]: { ...sf, email: e.target.value } })} />
                          <select className={styles.input} value={sf.papel}
                            onChange={(e) => setSigForms({ ...sigForms, [c.id]: { ...sf, papel: e.target.value as PapelSignatario } })}>
                            {PAPEIS.map((p) => <option key={p} value={p}>{PAPEL_LABEL[p]}</option>)}
                          </select>
                          <input className={styles.input} placeholder="CPF (opcional)"
                            value={sf.cpf ?? ''}
                            onChange={(e) => setSigForms({ ...sigForms, [c.id]: { ...sf, cpf: maskCPFCNPJ(e.target.value) } })} />
                          <input className={styles.input} type="date" placeholder="Nascimento (opcional)"
                            value={sf.data_nascimento ?? ''}
                            onChange={(e) => setSigForms({ ...sigForms, [c.id]: { ...sf, data_nascimento: e.target.value } })} />
                          <button className={styles.btnPrimary}
                            disabled={!sf.nome || !sf.email}
                            onClick={() => adicionarSig.mutate({
                              id: c.id,
                              data: { ...sf, cpf: sf.cpf?.trim() || undefined, data_nascimento: sf.data_nascimento?.trim() || undefined },
                            })}>
                            + Adicionar
                          </button>
                        </div>
                      )}
                    </div>

                    {/* ── AÇÕES CLICKSIGN ─────────────────────────────── */}
                    <div className={cs.acoes}>
                      {c.status === 'rascunho' && temArquivos(c) && c.signatarios.length > 0 && (
                        <button className={`${styles.btnPrimary} ${cs.btnEnviar}`}
                          onClick={() => {
                            if (confirm('Enviar para assinatura via ClickSign?\n\nIsso notificará todos os signatários por e-mail.'))
                              enviar.mutate(c.id)
                          }}
                          disabled={enviar.isPending}>
                          {enviar.isPending ? '⏳ Enviando...' : '✉ Enviar para assinatura (ClickSign)'}
                        </button>
                      )}
                      {c.status === 'rascunho' && temArquivos(c) && (
                        <button className={styles.btnTable}
                          onClick={() => {
                            if (confirm('Finalizar este contrato como já assinado?\n\nO(s) PDF(s) anexados serão marcados como versão final. Não passa pelo ClickSign e não notifica nem reenvia nada ao cliente.'))
                              finalizarManual.mutate(c.id)
                          }}
                          disabled={finalizarManual.isPending}
                          title="Para contratos já assinados fora do sistema (fisicamente ou por outro meio)">
                          {finalizarManual.isPending ? '⏳ Finalizando...' : '📥 Finalizar (já assinado, upload direto)'}
                        </button>
                      )}
                      {['aguardando_assinatura', 'parcialmente_assinado'].includes(c.status) && (
                        <>
                          {c.clicksign_document_key && (
                            <button className={styles.btnTable}
                              onClick={() => sincronizar.mutate({ id: c.id, manual: true })}
                              disabled={sincronizar.isPending}
                              title="Puxa o status real das assinaturas direto do ClickSign">
                              {sincronizar.isPending ? '⏳ Atualizando...' : '🔄 Atualizar status'}
                            </button>
                          )}
                          <button className={styles.btnTable}
                            onClick={() => { if (confirm('Confirmar assinatura manual? Isso marca o contrato como Assinado e remove a tag "Pendente" do financeiro.')) confirmarAssinatura.mutate(c.id) }}
                            title="Para contratos assinados fora do ClickSign">
                            ✓ Confirmar assinado (manual)
                          </button>
                          <button className={styles.btnDanger}
                            onClick={() => { if (confirm('Cancelar envelope no ClickSign?')) cancelar.mutate(c.id) }}>
                            Cancelar envelope
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {lerIAFor && (
        <ContratantesIAModal
          contratoId={lerIAFor}
          onClose={() => setLerIAFor(null)}
          onApplied={() => {
            qc.invalidateQueries({ queryKey: ['contratos'] })
            qc.invalidateQueries({ queryKey: ['clientes'] })
            qc.invalidateQueries({ queryKey: ['honorarios'] })
            qc.invalidateQueries({ queryKey: ['honorarios-pendentes-assinatura'] })
            qc.invalidateQueries({ queryKey: ['financeiro-resumo'] })
          }}
        />
      )}
    </div>
  )
}
