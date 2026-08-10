import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contratosApi } from '../api/contratos'
import type { ContratoCreate, SignatarioCreate, PapelSignatario, StatusContrato, GerarPdfRequest } from '../api/contratos'
import { clientesApi } from '../api/clientes'
import { processosApi } from '../api/processos'
import ComboBox from '../components/ComboBox'
import ClienteCombobox from '../components/ClienteCombobox'
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

export default function ContratosPage() {
  const qc = useQueryClient()
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({})
  const autoSyncRef = useRef<Set<string>>(new Set())

  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ContratoCreate>(EMPTY_CONTRATO)
  const [expandido, setExpandido] = useState<string | null>(null)
  const [sigForms, setSigForms] = useState<Record<string, SignatarioCreate>>({})
  const [gerarAberto, setGerarAberto] = useState<string | null>(null)
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
    queryKey: ['contratos-pasta-mestra'],
    queryFn: () => contratosApi.pastaMestra(),
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

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Contratos</h1>
        <div className={cs.headerActions}>
          {pastaMestra?.link && (
            <a href={pastaMestra.link} target="_blank" rel="noreferrer" className={cs.btnDrive}>
              ☁ Pasta mestra de Contratos
            </a>
          )}
          <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancelar' : '+ Novo Contrato'}
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={(e) => { e.preventDefault(); if (!form.cliente_id) { alert('Selecione ou crie um cliente'); return } criar.mutate(form) }} className={styles.form}>
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

      {isLoading ? <p className={styles.empty}>Carregando...</p> :
       contratos.length === 0 ? <p className={styles.empty}>Nenhum contrato cadastrado.</p> : (
        <div className={cs.lista}>
          {contratos.map((c) => {
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
                  <div>
                    <div className={cs.cardTitulo}>{c.titulo}</div>
                    <div className={cs.cardMeta}>
                      {cliente?.nome ?? '—'} · {formatDate(c.created_at)}
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
                        {c.status === 'rascunho' && (
                          <div className={cs.sectionActions}>
                            <button className={cs.btnSmall}
                              onClick={() => abrirGerar(c.id, c.cliente_id)}>
                              ✨ Gerar contrato
                            </button>
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
                          </div>
                        )}
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
                                <td>
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
                          <button className={styles.btnPrimary}
                            disabled={!sf.nome || !sf.email}
                            onClick={() => adicionarSig.mutate({ id: c.id, data: sf })}>
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
    </div>
  )
}
