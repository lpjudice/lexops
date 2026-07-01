import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conselhoApi } from '../api/conselho'
import type {
  CategoriaDiretriz, Contato, Diretriz, Evento, LogDiario, Parceiro, PipelineItem,
  StatusDiretriz, StatusParceiro, TipoParceiro,
} from '../api/conselho'
import ComboBox from '../components/ComboBox'
import type { ComboOption } from '../components/ComboBox'
import Modal from '../components/Modal'
import styles from './Page.module.css'
import cs from './ConselhoPage.module.css'

const CATEGORIAS: { value: CategoriaDiretriz; label: string }[] = [
  { value: 'operacional', label: 'Operacional' },
  { value: 'juridico', label: 'Jurídico' },
  { value: 'comercial', label: 'Comercial' },
  { value: 'parcerias', label: 'Parcerias' },
]
const STATUS_DIRETRIZ: StatusDiretriz[] = ['Não iniciado', 'Em andamento', 'Bloqueado', 'Concluído', 'Atrasado']
const TIPOS_PARCEIRO: TipoParceiro[] = ['Advogado', 'Contador', 'Assessor de investimentos', 'Outro']
const STATUS_PARCEIRO: StatusParceiro[] = ['Quente', 'Frio', 'Reativado']
const ESTAGIOS_PIPELINE = ['Prospecção', 'Contato inicial', 'Reunião agendada', 'Proposta enviada', 'Negociação', 'Fechado', 'Perdido']

function fmtData(d?: string | null) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

function diasDesde(d?: string | null) {
  if (!d) return Infinity
  return Math.floor((Date.now() - new Date(d + 'T12:00:00').getTime()) / 86400000)
}

// encodeURIComponent codifica emojis acima de U+FFFF como 4 bytes percent-encoded (%F0...),
// mas o WhatsApp Desktop/macOS não os decodifica corretamente. Passá-los como chars raw
// funciona porque o browser converte Unicode raw em UTF-8 antes de enviar ao wa.me.
function encodeWaText(text: string): string {
  return encodeURIComponent(text).replace(
    /%[Ff][0-4](?:%[89ABab][0-9A-Fa-f]){3}/g,
    m => decodeURIComponent(m),
  )
}

function aplicarPlaceholders(template: string, primeiro: string, ultimo: string, evento: string) {
  return template
    .replaceAll('{primeiro}', primeiro)
    .replaceAll('{ultimo}', ultimo || '')
    .replaceAll('{evento}', evento)
}

// Painel colapsável de mensagem individual por convidado.
// Usa useEffect para sincronizar com mensagem_pessoal quando aplicarATodos atualiza os dados.
function MensagemConvidadoPanel({
  cv, templateAtual, eventoNome, onSave,
}: {
  cv: import('../api/conselho').Convidado
  templateAtual: string
  eventoNome: string
  onSave: (texto: string) => void
}) {
  const textoPadrao = aplicarPlaceholders(templateAtual, cv.contato.primeiro_nome, cv.contato.sobrenome || '', eventoNome)
  const [aberto, setAberto] = useState(false)
  const [texto, setTexto] = useState(cv.mensagem_pessoal || '')

  // Sincroniza quando aplicarATodos (ou outra mutation) atualiza cv.mensagem_pessoal
  useEffect(() => {
    setTexto(cv.mensagem_pessoal || '')
  }, [cv.mensagem_pessoal])

  const isPersonalizada = !!texto && texto !== textoPadrao

  return (
    <div style={{ marginTop: 4 }}>
      <button
        className={styles.btnSmall}
        style={{ fontSize: 11, opacity: 0.8 }}
        onClick={() => setAberto((s) => !s)}
      >
        {isPersonalizada ? '✏️ Personalizada' : '📋 Padrão'} {aberto ? '▲' : '▼'}
      </button>
      {aberto && (
        <textarea
          className={cs.textarea}
          style={{ marginTop: 4, fontSize: 12 }}
          placeholder="Mensagem individual (editável)"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onBlur={() => onSave(texto)}
        />
      )}
    </div>
  )
}

function exportarCSV(nomeArquivo: string, headers: string[], rows: (string | number)[][]) {
  const escape = (v: string | number) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const conteudo = [headers, ...rows].map((r) => r.map(escape).join(';')).join('\n')
  const blob = new Blob(['﻿' + conteudo], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nomeArquivo
  a.click()
  URL.revokeObjectURL(url)
}

export default function ConselhoPage() {
  const [aba, setAba] = useState<'diretrizes' | 'pipeline' | 'eventos' | 'parcerias' | 'metricas'>('diretrizes')

  return (
    <div>
      <div className={styles.pageHeader}>
        <div className={styles.pageTitle}>Painel de <strong>Expansão</strong></div>
      </div>
      <div className={cs.tabs}>
        {([
          ['diretrizes', 'Diretrizes'],
          ['pipeline', 'Pipeline'],
          ['eventos', 'Eventos & Contatos'],
          ['parcerias', 'Parcerias'],
          ['metricas', 'Métricas'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            className={`${cs.tabBtn} ${aba === key ? cs.tabBtnActive : ''}`}
            onClick={() => setAba(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {aba === 'diretrizes' && <DiretrizesTab />}
      {aba === 'pipeline' && <PipelineTab />}
      {aba === 'eventos' && <EventosContatosTab />}
      {aba === 'parcerias' && <ParceriasTab />}
      {aba === 'metricas' && <MetricasTab />}
    </div>
  )
}

// ───────────────────────────── Diretrizes ─────────────────────────────

function DiretrizesTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [categoria, setCategoria] = useState<CategoriaDiretriz>('operacional')
  const [titulo, setTitulo] = useState('')
  const [descricao, setDescricao] = useState('')
  const [prazo, setPrazo] = useState('')
  const [novaSubtask, setNovaSubtask] = useState<Record<string, string>>({})

  const { data: diretrizes = [], isLoading } = useQuery({
    queryKey: ['conselho-diretrizes'],
    queryFn: () => conselhoApi.listarDiretrizes(),
  })

  const criar = useMutation({
    mutationFn: conselhoApi.criarDiretriz,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] })
      setShowForm(false)
      setTitulo(''); setDescricao(''); setPrazo('')
    },
  })

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Diretriz> }) => conselhoApi.atualizarDiretriz(id, data as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] }),
  })

  const deletar = useMutation({
    mutationFn: conselhoApi.deletarDiretriz,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] }),
  })

  const addSubtask = useMutation({
    mutationFn: ({ id, texto }: { id: string; texto: string }) => conselhoApi.addSubtask(id, texto),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] }),
  })

  const toggleSubtask = useMutation({
    mutationFn: ({ id, concluida }: { id: string; concluida: boolean }) => conselhoApi.toggleSubtask(id, concluida),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-diretrizes'] }),
  })

  return (
    <div>
      <button className={styles.btnPrimary} onClick={() => setShowForm((s) => !s)} style={{ marginBottom: 16 }}>
        {showForm ? 'Cancelar' : '+ Nova diretriz'}
      </button>

      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Categoria</label>
            <select className={styles.input} value={categoria} onChange={(e) => setCategoria(e.target.value as CategoriaDiretriz)}>
              {CATEGORIAS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Título</label>
            <input className={styles.input} value={titulo} onChange={(e) => setTitulo(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição</label>
            <textarea className={cs.textarea} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Prazo</label>
            <input type="date" className={styles.input} value={prazo} onChange={(e) => setPrazo(e.target.value)} />
          </div>
          <button
            className={styles.btnPrimary}
            disabled={!titulo || criar.isPending}
            onClick={() => criar.mutate({ categoria, titulo, descricao: descricao || undefined, prazo: prazo || undefined })}
          >
            Criar diretriz
          </button>
        </div>
      )}

      {isLoading ? <p>Carregando...</p> : diretrizes.length === 0 ? (
        <div className={styles.empty}>Nenhuma diretriz cadastrada</div>
      ) : (
        <div className={cs.cardGrid}>
          {diretrizes.map((d) => (
            <div key={d.id} className={`${cs.card} ${cs[`card_${d.categoria}` as keyof typeof cs]}`}>
              <div className={cs.cardTitle}>{d.titulo}</div>
              {d.descricao && <div className={cs.cardDesc}>{d.descricao}</div>}
              <div className={cs.cardMeta}>
                <select
                  className={styles.input}
                  style={{ padding: '4px 8px', fontSize: 12 }}
                  value={d.status}
                  onChange={(e) => atualizar.mutate({ id: d.id, data: { status: e.target.value as StatusDiretriz } })}
                >
                  {STATUS_DIRETRIZ.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <span style={{ fontSize: 11, color: '#9ca3af' }}>{fmtData(d.prazo)}</span>
              </div>
              {d.subtasks.map((st) => (
                <div key={st.id} className={cs.subtaskRow}>
                  <input
                    type="checkbox"
                    checked={st.concluida}
                    onChange={(e) => toggleSubtask.mutate({ id: st.id, concluida: e.target.checked })}
                  />
                  <span className={st.concluida ? cs.subtaskDone : ''}>{st.texto}</span>
                </div>
              ))}
              <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                <input
                  className={styles.input}
                  style={{ padding: '5px 8px', fontSize: 12 }}
                  placeholder="+ subtarefa"
                  value={novaSubtask[d.id] || ''}
                  onChange={(e) => setNovaSubtask((s) => ({ ...s, [d.id]: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && novaSubtask[d.id]) {
                      addSubtask.mutate({ id: d.id, texto: novaSubtask[d.id] })
                      setNovaSubtask((s) => ({ ...s, [d.id]: '' }))
                    }
                  }}
                />
              </div>
              <button className={styles.btnDanger} style={{ marginTop: 10 }} onClick={() => { if (confirm('Excluir diretriz?')) deletar.mutate(d.id) }}>
                Excluir
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ───────────────────────────── Pipeline ─────────────────────────────

function PipelineTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [nome, setNome] = useState('')
  const [origem, setOrigem] = useState('')
  const [tema, setTema] = useState('')

  const { data: pipeline = [], isLoading } = useQuery({
    queryKey: ['conselho-pipeline'],
    queryFn: () => conselhoApi.listarPipeline(),
  })

  const criar = useMutation({
    mutationFn: conselhoApi.criarPipeline,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conselho-pipeline'] })
      setShowForm(false); setNome(''); setOrigem(''); setTema('')
    },
  })
  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PipelineItem> }) => conselhoApi.atualizarPipeline(id, data as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-pipeline'] }),
  })
  const deletar = useMutation({
    mutationFn: conselhoApi.deletarPipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-pipeline'] }),
  })

  return (
    <div>
      <button className={styles.btnPrimary} onClick={() => setShowForm((s) => !s)} style={{ marginBottom: 16 }}>
        {showForm ? 'Cancelar' : '+ Nova oportunidade'}
      </button>
      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Nome</label>
            <input className={styles.input} value={nome} onChange={(e) => setNome(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Origem</label>
            <input className={styles.input} value={origem} onChange={(e) => setOrigem(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Tema</label>
            <input className={styles.input} value={tema} onChange={(e) => setTema(e.target.value)} />
          </div>
          <button className={styles.btnPrimary} disabled={!nome} onClick={() => criar.mutate({ nome, origem: origem || undefined, tema: tema || undefined })}>
            Criar
          </button>
        </div>
      )}
      {isLoading ? <p>Carregando...</p> : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Nome</th><th>Origem</th><th>Estágio</th><th>Último contato</th><th>Próxima ação</th><th>Ticket</th><th>Prob.</th><th></th>
              </tr>
            </thead>
            <tbody>
              {pipeline.map((p) => {
                const alerta = diasDesde(p.ultimo_contato) >= 10
                return (
                  <tr key={p.id} className={alerta ? cs.alertRow : ''}>
                    <td>{p.nome}</td>
                    <td>{p.origem || '—'}</td>
                    <td>
                      <select
                        className={styles.input}
                        style={{ padding: '4px 6px', fontSize: 12 }}
                        value={p.estagio}
                        onChange={(e) => atualizar.mutate({ id: p.id, data: { estagio: e.target.value } })}
                      >
                        {ESTAGIOS_PIPELINE.map((e) => <option key={e} value={e}>{e}</option>)}
                      </select>
                    </td>
                    <td>
                      <input
                        type="date"
                        className={styles.input}
                        style={{ padding: '4px 6px', fontSize: 12 }}
                        value={p.ultimo_contato || ''}
                        onChange={(e) => atualizar.mutate({ id: p.id, data: { ultimo_contato: e.target.value } })}
                      />
                    </td>
                    <td>{p.proxima_acao || '—'}</td>
                    <td>{p.ticket ? p.ticket.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '—'}</td>
                    <td>{p.probabilidade != null ? `${p.probabilidade}%` : '—'}</td>
                    <td><button className={styles.btnDanger} onClick={() => deletar.mutate(p.id)}>Excluir</button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {pipeline.length === 0 && <div className={styles.empty}>Nenhuma oportunidade no pipeline</div>}
        </div>
      )}
    </div>
  )
}

// ───────────────────────────── Eventos & Contatos ─────────────────────────────

function EventosContatosTab() {
  const [sub, setSub] = useState<'eventos' | 'contatos' | 'disparador'>('eventos')
  return (
    <div>
      <div className={cs.subTabs}>
        {([['eventos', 'Eventos'], ['contatos', 'Base de Contatos'], ['disparador', 'Disparador']] as const).map(([key, label]) => (
          <button key={key} className={`${cs.subTabBtn} ${sub === key ? cs.subTabBtnActive : ''}`} onClick={() => setSub(key)}>
            {label}
          </button>
        ))}
      </div>
      {sub === 'eventos' && <EventosSubTab />}
      {sub === 'contatos' && <ContatosSubTab />}
      {sub === 'disparador' && <DisparadorSubTab />}
    </div>
  )
}

function ContatoAutocomplete({ onSelect }: { onSelect: (c: Contato) => void }) {
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const { data: resultados = [] } = useQuery({
    queryKey: ['conselho-contatos-busca', query],
    queryFn: () => conselhoApi.buscarContatos(query),
    enabled: query.length > 1,
  })
  const criar = useMutation({
    mutationFn: (nome: string) => {
      const [primeiro, ...resto] = nome.trim().split(' ')
      return conselhoApi.criarContato({ primeiro_nome: primeiro, sobrenome: resto.join(' ') || undefined })
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['conselho-contatos'] })
      onSelect(c)
    },
  })
  const options: ComboOption[] = resultados.map((c) => ({
    value: c.id,
    label: `${c.primeiro_nome} ${c.sobrenome || ''}`.trim(),
    sublabel: c.email || c.whatsapp || undefined,
  }))
  return (
    <ComboBox
      options={options}
      value=""
      onChange={(v) => {
        setQuery('')
        const c = resultados.find((r) => r.id === v)
        if (c) onSelect(c)
      }}
      onQueryChange={setQuery}
      placeholder="Buscar contato por nome, e-mail ou WhatsApp..."
      onCreate={(q) => criar.mutate(q)}
      createLabel="Criar contato"
    />
  )
}

/** Modal: busca/cria contato por nome e captura e-mail/WhatsApp antes de adicionar ao evento.
 *  Se o contato já existir, os campos vêm pré-preenchidos e são atualizados ao salvar (dedupe). */
function AdicionarConvidadoModal({ onClose, onAdded }: { onClose: () => void; onAdded: (contato: Contato) => void }) {
  const qc = useQueryClient()
  const [selecionado, setSelecionado] = useState<Contato | null>(null)
  const [empresa, setEmpresa] = useState('')
  const [email, setEmail] = useState('')
  const [whatsapp, setWhatsapp] = useState('')

  const salvar = useMutation({
    mutationFn: async () => {
      if (!selecionado) throw new Error('Selecione ou crie um contato')
      const atualizado = await conselhoApi.atualizarContato(selecionado.id, {
        empresa: empresa || undefined,
        email: email || undefined,
        whatsapp: whatsapp || undefined,
      })
      return atualizado
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['conselho-contatos'] })
      onAdded(c)
      onClose()
    },
  })

  return (
    <Modal title="Adicionar convidado" onClose={onClose}>
      {!selecionado ? (
        <div className={styles.formRow}>
          <label className={styles.formLabel}>Nome</label>
          <ContatoAutocomplete onSelect={(c) => { setSelecionado(c); setEmpresa(c.empresa || ''); setEmail(c.email || ''); setWhatsapp(c.whatsapp || '') }} />
        </div>
      ) : (
        <div>
          <p style={{ fontSize: 13, marginBottom: 12 }}>
            <strong>{selecionado.primeiro_nome} {selecionado.sobrenome || ''}</strong>
            {selecionado.eventos.length > 0 && <span style={{ color: '#9ca3af' }}> — já participou de: {selecionado.eventos.join(', ')}</span>}
          </p>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Empresa</label>
            <input className={styles.input} value={empresa} onChange={(e) => setEmpresa(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>E-mail</label>
            <input className={styles.input} value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>WhatsApp</label>
            <input className={styles.input} value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} placeholder="DDI+DDD+número" />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className={styles.btnPrimary} disabled={salvar.isPending} onClick={() => salvar.mutate()}>Salvar e adicionar</button>
            <button className={styles.btnSmall} onClick={() => setSelecionado(null)}>Trocar contato</button>
          </div>
        </div>
      )}
    </Modal>
  )
}

/** Seletor de anexo PDF reutilizável em qualquer tela de disparo do módulo (upload novo ou da biblioteca). */
function AnexoPicker({ anexoId, onChange }: { anexoId: string; onChange: (id: string) => void }) {
  const qc = useQueryClient()
  const { data: anexos = [] } = useQuery({ queryKey: ['conselho-anexos'], queryFn: () => conselhoApi.listarAnexos() })
  const upload = useMutation({
    mutationFn: (file: File) => conselhoApi.uploadAnexo(file),
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ['conselho-anexos'] })
      onChange(a.id)
    },
  })
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <select className={styles.input} style={{ maxWidth: 240 }} value={anexoId} onChange={(e) => onChange(e.target.value)}>
        <option value="">Sem anexo</option>
        {anexos.map((a) => <option key={a.id} value={a.id}>{a.nome_arquivo}</option>)}
      </select>
      <label className={styles.btnSmall} style={{ cursor: 'pointer' }}>
        + Enviar PDF
        <input type="file" accept="application/pdf" style={{ display: 'none' }} onChange={(e) => { if (e.target.files?.[0]) upload.mutate(e.target.files[0]) }} />
      </label>
    </div>
  )
}

interface EmailSendTarget {
  contatoId: string
  email: string
  nome: string
  assunto: string
  corpo: string
  eventoId?: string
  eventoNome?: string
}

/** Modal de confirmação de envio real (via backend/Gmail) — substitui o antigo link mailto:. */
function EmailSendModal({ target, onClose }: { target: EmailSendTarget; onClose: () => void }) {
  const [assunto, setAssunto] = useState(target.assunto)
  const [corpo, setCorpo] = useState(target.corpo)
  const [anexoId, setAnexoId] = useState('')
  const [resultado, setResultado] = useState<string | null>(null)

  const enviar = useMutation({
    mutationFn: () => conselhoApi.dispararEmail({
      destinatarios: [{ contato_id: target.contatoId, evento_id: target.eventoId }],
      assunto,
      corpo_template: corpo,
      modo: 'individual',
      evento_nome: target.eventoNome,
      anexo_id: anexoId || undefined,
    }),
    onSuccess: (r) => {
      const item = r.resultados[0]
      setResultado(item?.sucesso ? `Enviado com sucesso (via ${r.enviado_por}).` : `Falha: ${item?.erro || 'erro desconhecido'}`)
    },
    onError: (e: Error) => setResultado(`Falha: ${e.message}`),
  })

  return (
    <Modal title={`Enviar e-mail para ${target.nome}`} onClose={onClose}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Para</label>
        <input className={styles.input} value={target.email} disabled />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Assunto</label>
        <input className={styles.input} value={assunto} onChange={(e) => setAssunto(e.target.value)} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Mensagem</label>
        <textarea className={cs.textarea} style={{ minHeight: 140 }} value={corpo} onChange={(e) => setCorpo(e.target.value)} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Anexo (PDF)</label>
        <AnexoPicker anexoId={anexoId} onChange={setAnexoId} />
      </div>
      {resultado && <p style={{ fontSize: 13, marginBottom: 10 }}>{resultado}</p>}
      <button className={styles.btnPrimary} disabled={enviar.isPending} onClick={() => enviar.mutate()}>
        {enviar.isPending ? 'Enviando...' : 'Enviar'}
      </button>
    </Modal>
  )
}

const TEMPLATE_LEMBRETE = (dias: number) =>
  `Olá {primeiro}, passando para lembrar que faltam ${dias} dia(s) para o {evento}. Confirma presença?`
const TEMPLATE_POS_EVENTO =
  'Olá {primeiro}, muito obrigado por participar do {evento}! Segue em anexo um material adicional que preparamos.'

function GuestComments({ contato, eventoId, onSaved }: { contato: Contato; eventoId: string; onSaved: () => void }) {
  const [aberto, setAberto] = useState(false)
  const [texto, setTexto] = useState('')
  const notasDoEvento = contato.notas.filter((n) => n.evento_id === eventoId)

  const addNota = useMutation({
    mutationFn: () => conselhoApi.addNotaContato(contato.id, texto, eventoId),
    onSuccess: () => { setTexto(''); onSaved() },
  })
  const deletarNota = useMutation({
    mutationFn: (notaId: string) => conselhoApi.deletarNotaContato(notaId),
    onSuccess: onSaved,
  })

  return (
    <div style={{ flexBasis: '100%', marginTop: 6 }}>
      <button className={styles.btnSmall} onClick={() => setAberto((a) => !a)}>
        {aberto ? 'Fechar comentários' : `Comentários (${notasDoEvento.length})`}
      </button>
      {aberto && (
        <div style={{ marginTop: 8 }}>
          {notasDoEvento.map((n) => (
            <div key={n.id} style={{ fontSize: 12.5, padding: '4px 0', borderBottom: '1px solid #eee', display: 'flex', alignItems: 'flex-start', gap: 6 }}>
              <span style={{ flex: 1 }}>{n.texto}</span>
              <button
                className={styles.btnDanger}
                style={{ padding: '1px 6px', fontSize: 11 }}
                onClick={() => deletarNota.mutate(n.id)}
              >✕</button>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <input className={styles.input} style={{ flex: 1 }} placeholder="Novo comentário sobre este convidado neste evento" value={texto} onChange={(e) => setTexto(e.target.value)} />
            <button className={styles.btnSmall} disabled={!texto || addNota.isPending} onClick={() => addNota.mutate()}>Salvar</button>
          </div>
        </div>
      )}
    </div>
  )
}

function EventCard({ evento, onClick }: { evento: Evento; onClick: () => void }) {
  const confirmados = evento.convidados.filter((c) => c.presenca_confirmada).length
  const recusaram = evento.convidados.filter((c) => c.recusou).length
  const participaram = evento.convidados.filter((c) => c.participacao_confirmada).length
  const pendentes = evento.convidados.filter((c) => c.pendente).length
  return (
    <div className={cs.eventCard} onClick={onClick}>
      <div className={cs.cardTitle}>{evento.nome}</div>
      <div style={{ fontSize: 12, color: '#9ca3af' }}>{fmtData(evento.data)}</div>
      <div className={cs.eventStats}>
        <span>{evento.convidados.length} convidados</span>
        <span style={{ color: '#22c55e' }}>✓ {confirmados} confirm.</span>
        {recusaram > 0 && <span style={{ color: '#ef4444' }}>✗ {recusaram} recus.</span>}
        {pendentes > 0 && <span style={{ color: '#f59e0b' }}>⏳ {pendentes} pend.</span>}
        <span>{participaram} particip.</span>
      </div>
    </div>
  )
}

function EventosSubTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [nome, setNome] = useState('')
  const [data, setData] = useState('')
  const [expandido, setExpandido] = useState<string | null>(null)
  const [expandidoConvidado, setExpandidoConvidado] = useState<string | null>(null)
  const [masterMsg, setMasterMsg] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [emailTarget, setEmailTarget] = useState<EmailSendTarget | null>(null)
  const [mostrarPassados, setMostrarPassados] = useState(false)

  const { data: eventos = [], isLoading } = useQuery({
    queryKey: ['conselho-eventos'],
    queryFn: () => conselhoApi.listarEventos(),
  })

  const hoje = new Date().toISOString().slice(0, 10)
  const eventosProximos = eventos
    .filter((e) => !e.data || e.data >= hoje)
    .sort((a, b) => (a.data || '9999-12-31').localeCompare(b.data || '9999-12-31'))
  const eventosPassados = eventos
    .filter((e) => e.data && e.data < hoje)
    .sort((a, b) => b.data!.localeCompare(a.data!))

  const criar = useMutation({
    mutationFn: conselhoApi.criarEvento,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['conselho-eventos'] }); setShowForm(false); setNome(''); setData('') },
  })
  const atualizar = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<Evento> }) => conselhoApi.atualizarEvento(id, payload as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })
  const deletar = useMutation({
    mutationFn: conselhoApi.deletarEvento,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })
  const addConvidado = useMutation({
    mutationFn: ({ eventoId, contatoId }: { eventoId: string; contatoId: string }) => conselhoApi.addConvidado(eventoId, contatoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })
  const atualizarConvidado = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { presenca_confirmada?: boolean; participacao_confirmada?: boolean; recusou?: boolean; pendente?: boolean; pendente_obs?: string; followup_data?: string | null; mensagem_pessoal?: string } }) =>
      conselhoApi.atualizarConvidado(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })
  const removerConvidado = useMutation({
    mutationFn: conselhoApi.removerConvidado,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-eventos'] }),
  })

  const eventoExpandido = eventos.find((e) => e.id === expandido)
  const templateAtual = masterMsg || eventoExpandido?.mensagem_master || ''

  async function aplicarATodos() {
    if (!eventoExpandido) return
    for (const cv of eventoExpandido.convidados) {
      const texto = aplicarPlaceholders(templateAtual, cv.contato.primeiro_nome, cv.contato.sobrenome || '', eventoExpandido.nome)
      await conselhoApi.atualizarConvidado(cv.id, { mensagem_pessoal: texto })
    }
    qc.invalidateQueries({ queryKey: ['conselho-eventos'] })
  }

  function exportarPresenca() {
    if (!eventoExpandido) return
    exportarCSV(
      `presenca_${eventoExpandido.nome.replace(/\s+/g, '_')}.csv`,
      ['Nome', 'E-mail', 'WhatsApp', 'Presença', 'Participação'],
      eventoExpandido.convidados.map((cv) => [
        `${cv.contato.primeiro_nome} ${cv.contato.sobrenome || ''}`.trim(),
        cv.contato.email || '',
        cv.contato.whatsapp || '',
        cv.presenca_confirmada ? 'Sim' : 'Não',
        cv.participacao_confirmada ? 'Sim' : 'Não',
      ]),
    )
  }

  return (
    <div>
      <button className={styles.btnPrimary} onClick={() => setShowForm((s) => !s)} style={{ marginBottom: 16 }}>
        {showForm ? 'Cancelar' : '+ Novo evento'}
      </button>
      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Nome do evento</label>
            <input className={styles.input} value={nome} onChange={(e) => setNome(e.target.value)} />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data</label>
            <input type="date" className={styles.input} value={data} onChange={(e) => setData(e.target.value)} />
          </div>
          <button className={styles.btnPrimary} disabled={!nome} onClick={() => criar.mutate({ nome, data: data || undefined })}>
            Criar evento
          </button>
        </div>
      )}

      {eventoExpandido ? (
        <div>
          <button className={styles.btnSmall} onClick={() => { setExpandido(null); setExpandidoConvidado(null) }} style={{ marginBottom: 14 }}>← Voltar</button>
          <h3 style={{ marginBottom: 4 }}>{eventoExpandido.nome}</h3>
          <p style={{ fontSize: 12, color: '#9ca3af', marginBottom: 14 }}>{fmtData(eventoExpandido.data)}</p>

          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <div className={styles.fieldGroup}>
              <span>Lembrete (dias antes)</span>
              <input
                type="number"
                className={styles.input}
                style={{ maxWidth: 90 }}
                defaultValue={eventoExpandido.dias_lembrete}
                onBlur={(e) => atualizar.mutate({ id: eventoExpandido.id, payload: { dias_lembrete: Number(e.target.value) } })}
              />
            </div>
            <button className={styles.btnSmall} onClick={() => setMasterMsg(TEMPLATE_LEMBRETE(eventoExpandido.dias_lembrete))}>
              Usar modelo: Lembrete
            </button>
            <button className={styles.btnSmall} onClick={() => setMasterMsg(TEMPLATE_POS_EVENTO)}>
              Usar modelo: Pós-evento (agradecimento)
            </button>
          </div>

          <div className={styles.formRow}>
            <label className={styles.formLabel}>Mensagem master (placeholders: {'{primeiro}'}, {'{ultimo}'}, {'{evento}'})</label>
            <textarea
              className={cs.textarea}
              value={templateAtual}
              onChange={(e) => setMasterMsg(e.target.value)}
              onBlur={() => atualizar.mutate({ id: eventoExpandido.id, payload: { mensagem_master: templateAtual } })}
            />
            <button className={styles.btnSmall} style={{ marginTop: 6, alignSelf: 'flex-start' }} onClick={aplicarATodos}>
              Aplicar a todos os convidados
            </button>
          </div>

          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginBottom: 10 }}>
            <div className={styles.formRow} style={{ maxWidth: 420, flex: 1, marginBottom: 0 }}>
              <label className={styles.formLabel}>Adicionar convidado</label>
              <button className={styles.btnSmall} onClick={() => setShowAddModal(true)}>+ Adicionar convidado</button>
            </div>
            <button className={styles.btnSmall} onClick={exportarPresenca}>Exportar lista de presença (CSV)</button>
          </div>

          {showAddModal && (
            <AdicionarConvidadoModal
              onClose={() => setShowAddModal(false)}
              onAdded={(c) => addConvidado.mutate({ eventoId: eventoExpandido.id, contatoId: c.id })}
            />
          )}

          {eventoExpandido.convidados.length === 0 && <div className={styles.empty} style={{ marginTop: 14 }}>Nenhum convidado ainda</div>}
          <div className={cs.guestCardGrid}>
            {eventoExpandido.convidados.map((cv) => {
              const mensagemResolvida = cv.mensagem_pessoal || aplicarPlaceholders(templateAtual, cv.contato.primeiro_nome, cv.contato.sobrenome || '', eventoExpandido.nome)
              const isExpanded = expandidoConvidado === cv.id
              return (
                <div key={cv.id} className={cs.guestCard}>
                  {/* Cabeçalho do card — clicável para expandir */}
                  <div className={cs.guestCardHeader} onClick={() => setExpandidoConvidado(isExpanded ? null : cv.id)}>
                    <span className={cs.guestCardName}>{cv.contato.primeiro_nome} {cv.contato.sobrenome || ''}</span>
                    <div className={cs.guestCardBadges}>
                      {cv.presenca_confirmada && <span className={`${cs.badge} ${cs.badgeConfirmado}`}>✓ Conf.</span>}
                      {cv.recusou && <span className={`${cs.badge} ${cs.badgeRecusou}`}>✗ Recus.</span>}
                      {cv.participacao_confirmada && <span className={`${cs.badge} ${cs.badgeParticipou}`}>✓ Part.</span>}
                      {cv.pendente && <span className={`${cs.badge} ${cs.badgePendente}`}>⏳ Pend.</span>}
                    </div>
                    <div className={cs.guestCardActions} onClick={(e) => e.stopPropagation()}>
                      {cv.contato.whatsapp && (
                        <>
                          <a className={`${cs.linkBtn} ${cs.linkWhatsapp}`} style={{ padding: '3px 8px', fontSize: 11 }} target="_blank" rel="noreferrer"
                             href={`https://wa.me/${cv.contato.whatsapp.replace(/\D/g, '')}?text=${encodeWaText(mensagemResolvida)}`}>
                            WA
                          </a>
                          <button className={styles.btnSmall} style={{ padding: '3px 6px', fontSize: 11 }} title="Copiar mensagem" onClick={() => navigator.clipboard.writeText(mensagemResolvida)}>📋</button>
                        </>
                      )}
                      {cv.contato.email && (
                        <button
                          className={`${cs.linkBtn} ${cs.linkEmail}`}
                          style={{ border: 'none', cursor: 'pointer', padding: '3px 8px', fontSize: 11 }}
                          onClick={() => setEmailTarget({
                            contatoId: cv.contato.id, email: cv.contato.email!, nome: cv.contato.primeiro_nome,
                            assunto: eventoExpandido.nome, corpo: mensagemResolvida,
                            eventoId: eventoExpandido.id, eventoNome: eventoExpandido.nome,
                          })}
                        >
                          Email
                        </button>
                      )}
                      <button className={styles.btnDanger} style={{ padding: '3px 8px', fontSize: 11 }} onClick={() => removerConvidado.mutate(cv.id)}>✕</button>
                    </div>
                  </div>

                  {/* Corpo expandido */}
                  {isExpanded && (
                    <div className={cs.guestCardBody}>
                      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                        <label className={cs.checkboxLabel}>
                          <input type="checkbox" checked={cv.presenca_confirmada} onChange={(e) => {
                            const checked = e.target.checked
                            atualizarConvidado.mutate({ id: cv.id, payload: { presenca_confirmada: checked, ...(checked ? { recusou: false } : {}) } })
                          }} />
                          Confirmado
                        </label>
                        <label className={cs.checkboxLabel} style={{ color: cv.recusou ? '#ef4444' : undefined }}>
                          <input type="checkbox" checked={cv.recusou} onChange={(e) => {
                            const checked = e.target.checked
                            atualizarConvidado.mutate({ id: cv.id, payload: { recusou: checked, ...(checked ? { presenca_confirmada: false } : {}) } })
                          }} />
                          Recusou
                        </label>
                        <label className={cs.checkboxLabel}>
                          <input type="checkbox" checked={cv.participacao_confirmada} onChange={(e) => atualizarConvidado.mutate({ id: cv.id, payload: { participacao_confirmada: e.target.checked } })} />
                          Participou
                        </label>
                        <label className={cs.checkboxLabel} style={{ color: cv.pendente ? '#f59e0b' : undefined }}>
                          <input type="checkbox" checked={cv.pendente} onChange={(e) => atualizarConvidado.mutate({ id: cv.id, payload: { pendente: e.target.checked } })} />
                          ⏳ Pendente
                        </label>
                      </div>
                      {cv.pendente && (
                        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                          <input
                            className={styles.input}
                            style={{ flex: 1, minWidth: 160, fontSize: 12 }}
                            placeholder="Observação / motivo pendência"
                            defaultValue={cv.pendente_obs || ''}
                            onBlur={(e) => atualizarConvidado.mutate({ id: cv.id, payload: { pendente_obs: e.target.value } })}
                          />
                          <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap' }}>
                            Follow-up em
                            <input
                              type="date"
                              className={styles.input}
                              style={{ fontSize: 12, width: 140 }}
                              defaultValue={cv.followup_data || ''}
                              onBlur={(e) => atualizarConvidado.mutate({ id: cv.id, payload: { followup_data: e.target.value || null } })}
                            />
                          </label>
                        </div>
                      )}
                      <MensagemConvidadoPanel
                        cv={cv}
                        templateAtual={templateAtual}
                        eventoNome={eventoExpandido.nome}
                        onSave={(texto) => atualizarConvidado.mutate({ id: cv.id, payload: { mensagem_pessoal: texto } })}
                      />
                      <GuestComments contato={cv.contato} eventoId={eventoExpandido.id} onSaved={() => qc.invalidateQueries({ queryKey: ['conselho-eventos'] })} />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <button className={styles.btnDanger} style={{ marginTop: 14 }} onClick={() => { if (confirm('Excluir evento?')) { deletar.mutate(eventoExpandido.id); setExpandido(null) } }}>
            Excluir evento
          </button>

          {emailTarget && <EmailSendModal target={emailTarget} onClose={() => setEmailTarget(null)} />}
        </div>
      ) : isLoading ? <p>Carregando...</p> : (
        <div>
          <div className={cs.cardGrid}>
            {eventosProximos.map((e) => <EventCard key={e.id} evento={e} onClick={() => setExpandido(e.id)} />)}
            {eventos.length === 0 && <div className={styles.empty}>Nenhum evento cadastrado</div>}
          </div>

          {eventosPassados.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <button className={styles.btnSmall} onClick={() => setMostrarPassados((s) => !s)}>
                {mostrarPassados ? 'Ocultar' : 'Mostrar'} eventos passados ({eventosPassados.length})
              </button>
              {mostrarPassados && (
                <div className={cs.cardGrid} style={{ marginTop: 12 }}>
                  {eventosPassados.map((e) => <EventCard key={e.id} evento={e} onClick={() => setExpandido(e.id)} />)}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ContatoExpandPanel({ contato, onSaved }: { contato: Contato; onSaved: () => void }) {
  const [empresa, setEmpresa] = useState(contato.empresa || '')
  const [email, setEmail] = useState(contato.email || '')
  const [whatsapp, setWhatsapp] = useState(contato.whatsapp || '')
  const [mensagem, setMensagem] = useState(contato.mensagem_global || '')

  const salvar = useMutation({
    mutationFn: () => conselhoApi.atualizarContato(contato.id, {
      empresa: empresa || undefined, email: email || undefined, whatsapp: whatsapp || undefined, mensagem_global: mensagem || undefined,
    }),
    onSuccess: onSaved,
  })

  return (
    <div style={{ padding: '10px 18px 16px', background: '#fafafa' }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <input className={styles.input} style={{ maxWidth: 200 }} value={empresa} onChange={(e) => setEmpresa(e.target.value)} placeholder="Empresa" />
        <input className={styles.input} style={{ maxWidth: 200 }} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="E-mail" />
        <input className={styles.input} style={{ maxWidth: 200 }} value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} placeholder="WhatsApp" />
      </div>
      <textarea className={cs.textarea} value={mensagem} onChange={(e) => setMensagem(e.target.value)} placeholder="Mensagem individual padrão" />
      <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
        <button className={styles.btnPrimary} disabled={salvar.isPending} onClick={() => salvar.mutate()}>Salvar</button>
        {whatsapp && (
          <>
            <a className={`${cs.linkBtn} ${cs.linkWhatsapp}`} target="_blank" rel="noreferrer"
               href={`https://wa.me/${whatsapp.replace(/\D/g, '')}?text=${encodeWaText(mensagem)}`}>
              Enviar WhatsApp
            </a>
            <button className={styles.btnSmall} title="Copiar mensagem para área de transferência" onClick={() => navigator.clipboard.writeText(mensagem)}>📋 Copiar msg</button>
          </>
        )}
      </div>
      {contato.notas.length > 0 && (
        <div style={{ marginTop: 10 }}>
          {contato.notas.map((n) => (
            <div key={n.id} style={{ fontSize: 12.5, padding: '4px 0', borderBottom: '1px solid #eee' }}>
              <strong>{n.evento_nome || 'Geral'}</strong> ({fmtData(n.data)}): {n.texto}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ContatosSubTab() {
  const qc = useQueryClient()
  const [filtroEvento, setFiltroEvento] = useState('')
  const [filtroPresenca, setFiltroPresenca] = useState('')
  const [filtroParticipacao, setFiltroParticipacao] = useState('')
  const [expandido, setExpandido] = useState<string | null>(null)
  const [showNovo, setShowNovo] = useState(false)
  const [primeiroNome, setPrimeiroNome] = useState('')
  const [sobrenome, setSobrenome] = useState('')
  const [empresaNovo, setEmpresaNovo] = useState('')
  const [email, setEmail] = useState('')
  const [whatsapp, setWhatsapp] = useState('')
  const [emailTarget, setEmailTarget] = useState<EmailSendTarget | null>(null)

  const { data: eventos = [] } = useQuery({ queryKey: ['conselho-eventos'], queryFn: () => conselhoApi.listarEventos() })
  const { data: contatos = [], isLoading } = useQuery({
    queryKey: ['conselho-contatos', filtroEvento, filtroPresenca, filtroParticipacao],
    queryFn: () => conselhoApi.listarContatos({
      evento_id: filtroEvento || undefined,
      presenca_confirmada: filtroPresenca ? filtroPresenca === 'sim' : undefined,
      participacao_confirmada: filtroParticipacao ? filtroParticipacao === 'sim' : undefined,
    }),
  })

  const criar = useMutation({
    mutationFn: conselhoApi.criarContato,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conselho-contatos'] })
      setShowNovo(false); setPrimeiroNome(''); setSobrenome(''); setEmpresaNovo(''); setEmail(''); setWhatsapp('')
    },
  })
  const deletar = useMutation({
    mutationFn: conselhoApi.deletarContato,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-contatos'] }),
  })

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <button className={styles.btnPrimary} onClick={() => setShowNovo((s) => !s)}>
          {showNovo ? 'Cancelar' : '+ Novo contato'}
        </button>
        <button
          className={styles.btnSmall}
          onClick={() => exportarCSV(
            'contatos.csv',
            ['Nome', 'E-mail', 'WhatsApp', 'Eventos'],
            contatos.map((c) => [`${c.primeiro_nome} ${c.sobrenome || ''}`.trim(), c.email || '', c.whatsapp || '', c.eventos.join(', ')]),
          )}
        >
          Exportar CSV
        </button>
        <div className={styles.fieldGroup}>
          <span>Evento</span>
          <select value={filtroEvento} onChange={(e) => setFiltroEvento(e.target.value)}>
            <option value="">Todos</option>
            {eventos.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
          </select>
        </div>
        <div className={styles.fieldGroup}>
          <span>Presença</span>
          <select value={filtroPresenca} onChange={(e) => setFiltroPresenca(e.target.value)}>
            <option value="">Todos</option><option value="sim">Confirmada</option><option value="nao">Não confirmada</option>
          </select>
        </div>
        <div className={styles.fieldGroup}>
          <span>Participação</span>
          <select value={filtroParticipacao} onChange={(e) => setFiltroParticipacao(e.target.value)}>
            <option value="">Todos</option><option value="sim">Confirmada</option><option value="nao">Não confirmada</option>
          </select>
        </div>
      </div>

      {showNovo && (
        <div className={styles.form}>
          <div className={styles.formRow}><label className={styles.formLabel}>Primeiro nome</label><input className={styles.input} value={primeiroNome} onChange={(e) => setPrimeiroNome(e.target.value)} /></div>
          <div className={styles.formRow}><label className={styles.formLabel}>Sobrenome</label><input className={styles.input} value={sobrenome} onChange={(e) => setSobrenome(e.target.value)} /></div>
          <div className={styles.formRow}><label className={styles.formLabel}>Empresa</label><input className={styles.input} value={empresaNovo} onChange={(e) => setEmpresaNovo(e.target.value)} /></div>
          <div className={styles.formRow}><label className={styles.formLabel}>E-mail</label><input className={styles.input} value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div className={styles.formRow}><label className={styles.formLabel}>WhatsApp</label><input className={styles.input} value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} /></div>
          <button className={styles.btnPrimary} disabled={!primeiroNome} onClick={() => criar.mutate({ primeiro_nome: primeiroNome, sobrenome: sobrenome || undefined, empresa: empresaNovo || undefined, email: email || undefined, whatsapp: whatsapp || undefined })}>
            Criar contato
          </button>
        </div>
      )}

      {isLoading ? <p>Carregando...</p> : (
        <div className={styles.tableCard}>
          {contatos.map((c) => (
            <div key={c.id}>
              <div className={cs.guestRow} style={{ cursor: 'pointer' }} onClick={() => setExpandido(expandido === c.id ? null : c.id)}>
                <span className={cs.guestName}>{c.primeiro_nome} {c.sobrenome || ''}</span>
                {c.empresa && <span style={{ fontSize: 12, color: '#9ca3af' }}>{c.empresa}</span>}
                <span style={{ fontSize: 12, color: '#9ca3af' }}>{c.eventos.join(', ') || 'Sem evento'}</span>
                {c.whatsapp && <a className={`${cs.linkBtn} ${cs.linkWhatsapp}`} onClick={(e) => e.stopPropagation()} target="_blank" rel="noreferrer" href={`https://wa.me/${c.whatsapp.replace(/\D/g, '')}`}>WhatsApp</a>}
                {c.email && (
                  <button
                    className={`${cs.linkBtn} ${cs.linkEmail}`}
                    style={{ border: 'none', cursor: 'pointer' }}
                    onClick={(e) => { e.stopPropagation(); setEmailTarget({ contatoId: c.id, email: c.email!, nome: c.primeiro_nome, assunto: '', corpo: c.mensagem_global || '' }) }}
                  >
                    E-mail
                  </button>
                )}
                <button className={styles.btnDanger} onClick={(e) => { e.stopPropagation(); if (confirm('Excluir contato?')) deletar.mutate(c.id) }}>Excluir</button>
              </div>
              {expandido === c.id && (
                <ContatoExpandPanel contato={c} onSaved={() => qc.invalidateQueries({ queryKey: ['conselho-contatos'] })} />
              )}
            </div>
          ))}
          {contatos.length === 0 && <div className={styles.empty}>Nenhum contato encontrado</div>}
        </div>
      )}
      {emailTarget && <EmailSendModal target={emailTarget} onClose={() => setEmailTarget(null)} />}
    </div>
  )
}

type FiltroConvidados = 'todos' | 'presenca' | 'participacao'

function DisparadorSubTab() {
  const { data: eventos = [] } = useQuery({ queryKey: ['conselho-eventos'], queryFn: () => conselhoApi.listarEventos() })
  const [contatosSelecionados, setContatosSelecionados] = useState<Set<string>>(new Set())
  const [filtroPorEvento, setFiltroPorEvento] = useState<Record<string, FiltroConvidados>>({})
  const [busca, setBusca] = useState('')
  const [msgWhatsapp, setMsgWhatsapp] = useState('Olá {primeiro}, tudo bem? Te convido para o {evento}!')
  const [msgEmail, setMsgEmail] = useState('Olá {primeiro},\n\nTe convido para o {evento}.\n\nAbraço.')
  const [assuntoEmail, setAssuntoEmail] = useState('Convite')
  const [modoEnvio, setModoEnvio] = useState<'individual' | 'bcc_unico'>('individual')
  const [anexoId, setAnexoId] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [resultados, setResultados] = useState<{ nome: string; sucesso: boolean; erro?: string | null }[] | null>(null)

  const todosContatos = useMemo(() => {
    const seen = new Map<string, Contato & { eventoNome: string }>()
    for (const e of eventos) {
      for (const cv of e.convidados) {
        if (!seen.has(cv.contato.id)) seen.set(cv.contato.id, { ...cv.contato, eventoNome: e.nome })
      }
    }
    return Array.from(seen.values())
  }, [eventos])

  const contatosFiltrados = todosContatos
    .filter((c) => `${c.primeiro_nome} ${c.sobrenome || ''}`.toLowerCase().includes(busca.toLowerCase()))
    .sort((a, b) => a.primeiro_nome.localeCompare(b.primeiro_nome))

  function contatosDoEvento(eventoId: string, filtro: FiltroConvidados): Contato[] {
    const evento = eventos.find((e) => e.id === eventoId)
    if (!evento) return []
    return evento.convidados
      .filter((cv) => filtro === 'todos' || (filtro === 'presenca' && cv.presenca_confirmada) || (filtro === 'participacao' && cv.participacao_confirmada))
      .map((cv) => cv.contato)
  }

  function adicionarDoEvento(eventoId: string) {
    const filtro = filtroPorEvento[eventoId] || 'todos'
    const ids = contatosDoEvento(eventoId, filtro).map((c) => c.id)
    setContatosSelecionados((prev) => new Set([...prev, ...ids]))
  }

  function removerDoEvento(eventoId: string) {
    const ids = new Set(contatosDoEvento(eventoId, 'todos').map((c) => c.id))
    setContatosSelecionados((prev) => new Set([...prev].filter((id) => !ids.has(id))))
  }

  function toggleContato(id: string) {
    const next = new Set(contatosSelecionados)
    if (next.has(id)) next.delete(id); else next.add(id)
    setContatosSelecionados(next)
  }

  const selecionados = todosContatos.filter((c) => contatosSelecionados.has(c.id))

  async function disparar() {
    setEnviando(true)
    setResultados(null)
    try {
      const destinatarios = selecionados
        .filter((c) => c.email)
        .map((c) => ({ contato_id: c.id, evento_id: undefined }))
      const r = await conselhoApi.dispararEmail({
        destinatarios,
        assunto: assuntoEmail,
        corpo_template: msgEmail,
        modo: modoEnvio,
        evento_nome: selecionados[0] ? (selecionados[0] as Contato & { eventoNome?: string }).eventoNome : undefined,
        anexo_id: anexoId || undefined,
      })
      setResultados(r.resultados.map((res) => ({ nome: res.nome, sucesso: res.sucesso, erro: res.erro })))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div>
      <h4 style={{ marginBottom: 8 }}>1. Selecione eventos</h4>
      <div className={cs.dispatchList}>
        {eventos.map((e) => {
          const filtro = filtroPorEvento[e.id] || 'todos'
          const qtd = contatosDoEvento(e.id, filtro).length
          return (
            <div key={e.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '4px 0', flexWrap: 'wrap' }}>
              <span style={{ minWidth: 160 }}>{e.nome} ({e.convidados.length} convidados)</span>
              <select
                className={styles.input}
                style={{ padding: '4px 6px', fontSize: 12, maxWidth: 200 }}
                value={filtro}
                onChange={(ev) => setFiltroPorEvento((prev) => ({ ...prev, [e.id]: ev.target.value as FiltroConvidados }))}
              >
                <option value="todos">Todos os convidados</option>
                <option value="presenca">Apenas presença confirmada</option>
                <option value="participacao">Apenas participação confirmada</option>
              </select>
              <button className={styles.btnSmall} onClick={() => adicionarDoEvento(e.id)}>+ Adicionar ({qtd})</button>
              <button className={styles.btnSmall} onClick={() => removerDoEvento(e.id)}>Remover deste evento</button>
            </div>
          )
        })}
      </div>

      <h4 style={{ marginBottom: 8 }}>2. Mensagens (placeholders: {'{primeiro}'}, {'{ultimo}'}, {'{evento}'})</h4>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>WhatsApp</label>
        <textarea className={cs.textarea} value={msgWhatsapp} onChange={(e) => setMsgWhatsapp(e.target.value)} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Assunto do e-mail</label>
        <input className={styles.input} value={assuntoEmail} onChange={(e) => setAssuntoEmail(e.target.value)} />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>E-mail</label>
        <textarea className={cs.textarea} value={msgEmail} onChange={(e) => setMsgEmail(e.target.value)} />
      </div>

      <h4 style={{ marginBottom: 8 }}>3. Contatos ({selecionados.length} selecionados)</h4>
      <input className={styles.input} style={{ maxWidth: 320, marginBottom: 10 }} placeholder="Buscar..." value={busca} onChange={(e) => setBusca(e.target.value)} />
      <div className={cs.dispatchList}>
        {contatosFiltrados.map((c) => (
          <label key={c.id} className={cs.checkboxLabel} style={{ fontSize: 13 }}>
            <input type="checkbox" checked={contatosSelecionados.has(c.id)} onChange={() => toggleContato(c.id)} />
            {c.primeiro_nome} {c.sobrenome || ''} <span style={{ color: '#9ca3af' }}>({c.eventoNome})</span>
          </label>
        ))}
      </div>

      <h4 style={{ marginBottom: 8 }}>4. Disparar</h4>
      {selecionados.length === 0 ? (
        <div className={styles.empty}>Selecione ao menos um contato</div>
      ) : (
        <div>
          <div style={{ display: 'flex', gap: 16, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <label className={cs.checkboxLabel}>
              <input type="radio" checked={modoEnvio === 'individual'} onChange={() => setModoEnvio('individual')} />
              Envio individual (personalizado por pessoa)
            </label>
            <label className={cs.checkboxLabel}>
              <input type="radio" checked={modoEnvio === 'bcc_unico'} onChange={() => setModoEnvio('bcc_unico')} />
              E-mail único em BCC (não personaliza o nome)
            </label>
          </div>
          <div className={styles.formRow} style={{ maxWidth: 420 }}>
            <label className={styles.formLabel}>Anexo (PDF, opcional — vale para qualquer disparo deste menu)</label>
            <AnexoPicker anexoId={anexoId} onChange={setAnexoId} />
          </div>
          <button className={styles.btnPrimary} disabled={enviando} onClick={disparar} style={{ marginBottom: 14 }}>
            {enviando ? 'Enviando...' : `Enviar e-mail real para ${selecionados.filter((c) => c.email).length} destinatário(s)`}
          </button>
          {resultados && (
            <div className={styles.tableCard} style={{ marginBottom: 14, padding: '8px 14px' }}>
              {resultados.map((r, i) => (
                <div key={i} style={{ fontSize: 12.5, padding: '3px 0', color: r.sucesso ? '#15803d' : '#b91c1c' }}>
                  {r.sucesso ? '✓' : '✗'} {r.nome}{!r.sucesso && r.erro ? ` — ${r.erro}` : ''}
                </div>
              ))}
            </div>
          )}
          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 6 }}>WhatsApp individual (link manual):</div>
          <div>
            {selecionados.filter((c) => c.whatsapp).map((c) => {
              const msgResolvida = aplicarPlaceholders(msgWhatsapp, c.primeiro_nome, c.sobrenome || '', (c as Contato & { eventoNome?: string }).eventoNome || '')
              return (
                <span key={c.id} style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                  <a className={`${cs.linkBtn} ${cs.linkWhatsapp}`} target="_blank" rel="noreferrer"
                     href={`https://wa.me/${c.whatsapp!.replace(/\D/g, '')}?text=${encodeWaText(msgResolvida)}`}>
                    {c.primeiro_nome}
                  </a>
                  <button className={styles.btnSmall} title="Copiar mensagem" onClick={() => navigator.clipboard.writeText(msgResolvida)}>📋</button>
                </span>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ───────────────────────────── Parcerias ─────────────────────────────

function ParceriasTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [nome, setNome] = useState('')
  const [tipo, setTipo] = useState<TipoParceiro>('Advogado')

  const { data: parceiros = [], isLoading } = useQuery({ queryKey: ['conselho-parceiros'], queryFn: () => conselhoApi.listarParceiros() })

  const criar = useMutation({
    mutationFn: conselhoApi.criarParceiro,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['conselho-parceiros'] }); setShowForm(false); setNome('') },
  })
  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Parceiro> }) => conselhoApi.atualizarParceiro(id, data as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-parceiros'] }),
  })
  const deletar = useMutation({
    mutationFn: conselhoApi.deletarParceiro,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conselho-parceiros'] }),
  })

  return (
    <div>
      <button className={styles.btnPrimary} onClick={() => setShowForm((s) => !s)} style={{ marginBottom: 16 }}>
        {showForm ? 'Cancelar' : '+ Nova parceria'}
      </button>
      {showForm && (
        <div className={styles.form}>
          <div className={styles.formRow}><label className={styles.formLabel}>Nome</label><input className={styles.input} value={nome} onChange={(e) => setNome(e.target.value)} /></div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Tipo</label>
            <select className={styles.input} value={tipo} onChange={(e) => setTipo(e.target.value as TipoParceiro)}>
              {TIPOS_PARCEIRO.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <button className={styles.btnPrimary} disabled={!nome} onClick={() => criar.mutate({ nome, tipo })}>Criar</button>
        </div>
      )}
      {isLoading ? <p>Carregando...</p> : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead><tr><th>Nome</th><th>Tipo</th><th>Status</th><th>Último encaminhamento</th><th>Plano</th><th></th></tr></thead>
            <tbody>
              {parceiros.map((p) => (
                <tr key={p.id}>
                  <td>{p.nome}</td>
                  <td>{p.tipo}</td>
                  <td>
                    <select className={styles.input} style={{ padding: '4px 6px', fontSize: 12 }} value={p.status}
                      onChange={(e) => atualizar.mutate({ id: p.id, data: { status: e.target.value as StatusParceiro } })}>
                      {STATUS_PARCEIRO.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td>{fmtData(p.ultimo_encaminhamento)}</td>
                  <td>{p.plano || '—'}</td>
                  <td><button className={styles.btnDanger} onClick={() => deletar.mutate(p.id)}>Excluir</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {parceiros.length === 0 && <div className={styles.empty}>Nenhuma parceria cadastrada</div>}
        </div>
      )}
    </div>
  )
}

// ───────────────────────────── Métricas ─────────────────────────────

function MetricasTab() {
  const qc = useQueryClient()
  const [numero, setNumero] = useState('')
  const [nota, setNota] = useState('')

  const { data: metricas } = useQuery({ queryKey: ['conselho-metricas'], queryFn: () => conselhoApi.obterMetricas() })
  const { data: logs = [] } = useQuery({ queryKey: ['conselho-logs'], queryFn: () => conselhoApi.listarLogs() })

  const criarLog = useMutation({
    mutationFn: conselhoApi.criarLog,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conselho-logs'] })
      qc.invalidateQueries({ queryKey: ['conselho-metricas'] })
      setNumero(''); setNota('')
    },
  })

  return (
    <div>
      <div className={cs.metricGrid}>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.media_logs_7d.toFixed(1) ?? '—'}</div><div className={cs.metricLabel}>Média 7 dias</div></div>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.total_contatos ?? '—'}</div><div className={cs.metricLabel}>Total contatos</div></div>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.contatos_participaram_ao_menos_uma_vez ?? '—'}</div><div className={cs.metricLabel}>Participaram 1x+</div></div>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.contatos_reconvidados ?? '—'}</div><div className={cs.metricLabel}>Reconvidados</div></div>
        <div className={cs.metricCard}><div className={cs.metricValue}>{metricas?.contatos_reiterados ?? '—'}</div><div className={cs.metricLabel}>Reiterados (2x+)</div></div>
      </div>

      <h4 style={{ marginBottom: 4 }}>Registro diário</h4>
      <p style={{ fontSize: 12, color: '#9ca3af', marginBottom: 12, maxWidth: 560 }}>
        Escolha uma métrica única para acompanhar todo dia (ex.: nº de follow-ups feitos, reuniões qualificadas ou horas em atividade comercial)
        e registre esse número diariamente — o hábito importa mais que o valor em si. A "nota" é um comentário livre opcional do dia.
      </p>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, alignItems: 'flex-end' }}>
        <input className={styles.input} style={{ maxWidth: 140 }} type="number" placeholder="Número" value={numero} onChange={(e) => setNumero(e.target.value)} />
        <input className={styles.input} style={{ maxWidth: 240 }} placeholder="Nota (opcional)" value={nota} onChange={(e) => setNota(e.target.value)} />
        <button
          className={styles.btnPrimary}
          disabled={!numero}
          onClick={() => criarLog.mutate({ data: new Date().toISOString().slice(0, 10), numero: Number(numero), nota: nota || undefined })}
        >
          Registrar
        </button>
      </div>

      <div className={styles.tableCard}>
        <table className={styles.table}>
          <thead><tr><th>Data</th><th>Número</th><th>Nota</th></tr></thead>
          <tbody>
            {logs.map((l: LogDiario) => (
              <tr key={l.id}><td>{fmtData(l.data)}</td><td>{l.numero}</td><td>{l.nota || '—'}</td></tr>
            ))}
          </tbody>
        </table>
        {logs.length === 0 && <div className={styles.empty}>Nenhum registro ainda</div>}
      </div>
    </div>
  )
}
