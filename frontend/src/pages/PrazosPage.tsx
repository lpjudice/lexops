import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { prazosApi } from '../api/prazos'
import type { Prazo, PrazoCreate, PrazoEdit, TipoPrazo, TipoContagem, StatusPrazo } from '../api/prazos'
import { processosApi } from '../api/processos'
import type { EstadoProcesso, RitoProcesso } from '../api/processos'
import { clientesApi } from '../api/clientes'
import { andamentosApi } from '../api/andamentos'
import ResponsavelComboBox from '../components/ResponsavelComboBox'
import ProcessoCombobox from '../components/ProcessoCombobox'
import PecaCombobox from '../components/PecaCombobox'
import LegendaPrazos from '../components/LegendaPrazos'
import {
  useCatalogoPrazos, sugestaoDaPeca, divergeDaLei, textoConfirmacaoDivergencia,
} from '../api/prazosLegais'
import { RITO_OPTS, pecasPara } from '../constants/pecas'
import { useFiltroMes } from '../components/useFiltroMes'
import styles from './Page.module.css'
import prazosStyles from './PrazosPage.module.css'

const TIPOS: TipoPrazo[] = [
  'contestacao', 'recurso', 'contrarrazoes', 'manifestacao',
  'audiencia', 'pericia', 'outro',
]

const EMPTY: PrazoCreate = {
  processo_id: '', tipo: 'contestacao', descricao: '',
  peca_necessaria: '', responsavel: '', data_publicacao: '', dias_prazo: 15,
  tipo_contagem: 'uteis', status: 'pendente',
}

function diasRestantes(data?: string): number | null {
  if (!data) return null
  const diff = new Date(data).getTime() - new Date().setHours(0, 0, 0, 0)
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

/** Um prazo só deixa de cobrar atenção quando recebe tratamento. Vencido e
 * ainda "pendente" é o caso mais grave que existe aqui — vai de vermelho.
 *
 * O cinza/opaco de "tratado" só faz sentido na aba "Todas", onde ele distingue
 * o que ainda está em aberto do que já foi resolvido. Dentro de uma aba que já
 * filtrou por um status tratado específico (Perdido, Cumprido...) TODO card
 * teria essa classe — o cinza vira ruído, e a opacidade reduzida passa a
 * impressão de card desabilitado/não clicável, quando ele continua
 * interativo normalmente (o Lucas relatou exatamente essa confusão).
 */
function urgenciaClass(dias: number | null, status: StatusPrazo, tab: TabStatus): string {
  if (status !== 'pendente') return tab === 'todas' ? prazosStyles.tratado : ''
  if (dias === null) return ''
  if (dias < 0) return prazosStyles.vencido
  if (dias <= 2) return prazosStyles.urgente
  if (dias <= 5) return prazosStyles.atencao
  return prazosStyles.ok
}

function formatDate(d?: string) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

const STATUS_OPCOES: { valor: StatusPrazo; label: string }[] = [
  { valor: 'pendente', label: 'pendente' },
  { valor: 'cumprido', label: 'cumprido' },
  { valor: 'perdido', label: 'perdido' },
  { valor: 'ignorado', label: 'ignorado' },
  { valor: 'nada_a_fazer', label: 'nada a fazer' },
]

type TabStatus = 'todas' | 'ativo' | 'pendente' | 'cumprido' | 'perdido' | 'ignorado' | 'nada_a_fazer'

const TAB_LABEL: Record<TabStatus, string> = {
  todas: 'Todas',
  ativo: 'Ativo',
  pendente: 'Pendente',
  cumprido: 'Cumprido',
  perdido: 'Perdido',
  ignorado: 'Ignorado',
  nada_a_fazer: 'Nada a fazer',
}

const TABS: TabStatus[] = ['todas', 'ativo', 'pendente', 'cumprido', 'perdido', 'ignorado', 'nada_a_fazer']

/** Estado do editor completo do card (não só peça/responsável, como antes). */
type EditForm = {
  processo_id: string
  tipo: TipoPrazo
  peca_necessaria: string
  data_publicacao: string
  dias_prazo: number
  tipo_contagem: TipoContagem
  descricao: string
  responsavel: { nome: string; email: string; id?: string | null }
}

function editFormDe(p: Prazo): EditForm {
  return {
    processo_id: p.processo_id,
    tipo: p.tipo,
    peca_necessaria: p.peca_necessaria ?? '',
    data_publicacao: p.data_publicacao,
    dias_prazo: p.dias_prazo,
    tipo_contagem: p.tipo_contagem,
    descricao: p.descricao ?? '',
    responsavel: { nome: p.responsavel ?? '', email: '', id: p.responsavel_id ?? null },
  }
}

function pedirMotivoPerda(): string | null {
  const motivo = window.prompt('O que aconteceu? (fica salvo no prazo, pra referência futura)')
  return motivo
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

/** 2ª etapa de "anotar um prazo": a qual andamento do processo este
 * comentário se refere. "Não vinculado" vem pré-selecionado — confirmar sem
 * mexer em nada ainda salva (resolve o caso de "o sistema não achou o
 * andamento certo", sem travar quem só quer registrar a anotação rápido). */
function AndamentoPicker({
  processoId, selecionado, onSelecionar, semVinculo,
}: {
  processoId: string
  selecionado: string
  onSelecionar: (v: string) => void
  semVinculo: string
}) {
  const { data: andamentos = [], isLoading } = useQuery({
    queryKey: ['andamentos', processoId, 0, undefined],
    queryFn: () => andamentosApi.listar(processoId, 8, 0),
  })

  return (
    <div className={prazosStyles.picker}>
      <p className={prazosStyles.pickerTitulo}>A qual andamento este comentário se refere?</p>
      {isLoading ? (
        <p className={prazosStyles.pickerVazio}>Carregando andamentos do processo...</p>
      ) : andamentos.length === 0 ? (
        <p className={prazosStyles.pickerVazio}>Nenhum andamento sincronizado ainda para este processo.</p>
      ) : (
        <div className={prazosStyles.pickerLista}>
          {andamentos.map((a) => (
            <label key={a.id} className={`${prazosStyles.pickerOpcao} ${selecionado === a.id ? prazosStyles.pickerOpcaoSel : ''}`}>
              <input type="radio" name={`andamento-${processoId}`} checked={selecionado === a.id}
                onChange={() => onSelecionar(a.id)} />
              <span>
                <span className={prazosStyles.pickerOpcaoTitulo}>
                  {a.tipo || 'Andamento'}{a.descricao ? ` — "${a.descricao.slice(0, 70)}${a.descricao.length > 70 ? '…' : ''}"` : ''}
                </span>
                <span className={prazosStyles.pickerOpcaoMeta}>{formatDate(a.data_andamento ?? undefined)}</span>
              </span>
            </label>
          ))}
        </div>
      )}
      <label className={`${prazosStyles.pickerOpcao} ${prazosStyles.pickerOpcaoVazia} ${selecionado === semVinculo ? prazosStyles.pickerOpcaoSel : ''}`}>
        <input type="radio" name={`andamento-${processoId}`} checked={selecionado === semVinculo}
          onChange={() => onSelecionar(semVinculo)} />
        <span>
          <span className={prazosStyles.pickerOpcaoTitulo}>◻ Não vinculado a andamento</span>
          <span className={prazosStyles.pickerOpcaoMeta}>o comentário é salvo normalmente</span>
        </span>
      </label>
    </div>
  )
}

export default function PrazosPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<PrazoCreate>(EMPTY)
  const [editando, setEditando] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm | null>(null)
  // Comentários: painel independente do editor (pode ficar aberto junto),
  // e mais de um card pode estar com o painel aberto ao mesmo tempo — por
  // isso um Set em vez de um único id como o `editando`.
  const [comentandoIds, setComentandoIds] = useState<Set<string>>(new Set())
  const [novoComentario, setNovoComentario] = useState<Record<string, string>>({})
  // 2ª etapa do comentário: depois de escrever, confirma a qual andamento do
  // processo ele se refere (ou "não vinculado") antes de salvar de verdade —
  // é o que faz o mesmo comentário aparecer tanto em Prazos quanto, já
  // vinculado ou não, no Processo (Andamentos / Anotações de Prazos).
  const [vinculandoIds, setVinculandoIds] = useState<Set<string>>(new Set())
  const SEM_VINCULO = '__sem_vinculo__'
  const [andamentoEscolhido, setAndamentoEscolhido] = useState<Record<string, string>>({})
  const [ritoForm, setRitoForm] = useState<RitoProcesso>('comum')
  const [ritoEdit, setRitoEdit] = useState<RitoProcesso>('comum')
  const [searchParams] = useSearchParams()
  const tabInicial = searchParams.get('tab')
  const [tabStatus, setTabStatus] = useState<TabStatus>(
    TABS.includes(tabInicial as TabStatus) ? (tabInicial as TabStatus) : 'ativo',
  )
  const destaqueId = searchParams.get('destaque')
  const destaqueRef = useRef<HTMLDivElement | null>(null)
  const [jaFocou, setJaFocou] = useState(false)

  const { data: catalogoLegal } = useCatalogoPrazos()

  // Escolher a peça já traz o prazo da lei — é o caminho normal; digitar outro
  // número continua permitido, só passa por confirmação na hora de salvar.
  const aplicarPecaNoForm = (peca: string) => {
    const sug = sugestaoDaPeca(catalogoLegal, peca)
    setForm((f) => ({
      ...f,
      peca_necessaria: peca,
      ...(sug?.dias != null
        ? { dias_prazo: sug.dias, tipo_contagem: (sug.contagem ?? 'uteis') as 'uteis' | 'corridos' }
        : {}),
    }))
  }

  /** Deixa passar se o prazo bate com a lei; senão pede confirmação explícita. */
  const confirmaSeDiverge = (peca: string | undefined, dias: number, contagem: string): boolean => {
    const sug = sugestaoDaPeca(catalogoLegal, peca)
    if (!sug || !divergeDaLei(sug, dias, contagem)) return true
    return confirm(textoConfirmacaoDivergencia(sug, dias, contagem))
  }

  const filtroMes = useFiltroMes()  // filtra por data do prazo (cumpridos/perdidos/ignorados)
  const { data: prazos = [], isLoading } = useQuery({
    queryKey: ['prazos'],
    queryFn: () => prazosApi.listar(),
  })

  // Veio de um link (ex: chip "🔗 prazo" em Tarefas) — pula pra aba certa e
  // rola até o card, em vez de deixar o usuário procurar.
  useEffect(() => {
    if (!destaqueId || jaFocou || prazos.length === 0) return
    const alvo = prazos.find((p) => p.id === destaqueId)
    if (alvo) {
      setTabStatus(alvo.status === 'pendente' ? 'ativo' : (alvo.status as TabStatus))
      setJaFocou(true)
      setTimeout(() => destaqueRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100)
    }
  }, [destaqueId, jaFocou, prazos])
  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })
  const criar = useMutation({
    mutationFn: prazosApi.criar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prazos'] })
      setShowForm(false)
      setForm(EMPTY)
    },
  })

  const atualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: PrazoEdit }) => prazosApi.atualizar(id, data),
    onSuccess: () => {
      // O prazo é a mesma linha vista no Diário Oficial e no Recorte Digital —
      // invalida os dois pra edição feita aqui aparecer lá na hora.
      qc.invalidateQueries({ queryKey: ['prazos'] })
      qc.invalidateQueries({ queryKey: ['diario'] })
      qc.invalidateQueries({ queryKey: ['diario2'] })
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      setEditando(null)
      setEditForm(null)
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      alert(e.response?.data?.detail ?? 'Não foi possível salvar as alterações do prazo.'),
  })

  const lembretes = useMutation({
    mutationFn: () => prazosApi.enviarLembretes(true),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['prazos'] })
      alert(
        `Lembretes disparados.\n\n` +
        `${r.prazos_ativos} prazo(s) em aberto · ${r.emails_enviados} e-mail(s) enviado(s)\n` +
        `Telegram: ${r.telegram_enviado ? 'enviado' : 'não enviado (bot/chat não configurado)'}` +
        (r.erros ? `\n${r.erros} falha(s) — veja os logs.` : ''),
      )
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      alert(e.response?.data?.detail ?? 'Não foi possível disparar os lembretes agora.'),
  })

  const abrirEditor = (p: Prazo) => {
    setEditando(p.id)
    setEditForm(editFormDe(p))
    setRitoEdit(getProcesso(p.processo_id)?.rito ?? 'comum')
  }

  const salvarEdicao = (id: string) => {
    if (!editForm) return
    if (!confirmaSeDiverge(editForm.peca_necessaria, editForm.dias_prazo, editForm.tipo_contagem)) return
    atualizar.mutate({
      id,
      data: {
        processo_id: editForm.processo_id,
        tipo: editForm.tipo,
        peca_necessaria: editForm.peca_necessaria || undefined,
        data_publicacao: editForm.data_publicacao,
        dias_prazo: editForm.dias_prazo,
        tipo_contagem: editForm.tipo_contagem,
        descricao: editForm.descricao || undefined,
        responsavel: editForm.responsavel.nome || undefined,
        responsavel_id: editForm.responsavel.id ?? undefined,
      },
    })
  }

  const deletar = useMutation({
    mutationFn: (id: string) => prazosApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['prazos'] }),
    onError: () => alert('Não foi possível remover este prazo.'),
  })

  const criarComentario = useMutation({
    mutationFn: ({ prazoId, texto, andamentoId, processoId }: {
      prazoId: string; texto: string; andamentoId: string | null; processoId: string
    }) => prazosApi.criarComentario(prazoId, texto, andamentoId),
    onSuccess: (_r, { prazoId, processoId }) => {
      qc.invalidateQueries({ queryKey: ['prazos'] })
      // Mesmo dado que alimenta Andamentos/Anotações de Prazos em Processos —
      // sem isso, só reabrindo o processo pra ver o comentário novo lá.
      qc.invalidateQueries({ queryKey: ['comentarios-prazo-processo', processoId] })
      setNovoComentario((m) => ({ ...m, [prazoId]: '' }))
      setVinculandoIds((atual) => { const n = new Set(atual); n.delete(prazoId); return n })
    },
    onError: () => alert('Não foi possível salvar o comentário.'),
  })

  const deletarComentario = useMutation({
    mutationFn: ({ prazoId, comentarioId }: { prazoId: string; comentarioId: string; processoId: string }) =>
      prazosApi.deletarComentario(prazoId, comentarioId),
    onSuccess: (_r, { processoId }) => {
      qc.invalidateQueries({ queryKey: ['prazos'] })
      qc.invalidateQueries({ queryKey: ['comentarios-prazo-processo', processoId] })
    },
    onError: () => alert('Não foi possível remover o comentário.'),
  })

  const toggleComentarios = (id: string) => {
    setComentandoIds((atual) => {
      const novo = new Set(atual)
      if (novo.has(id)) novo.delete(id)
      else novo.add(id)
      return novo
    })
  }

  /** Fim da etapa 1 (escrever): abre a escolha de andamento, com "não
   * vinculado" pré-selecionado — confirmar sem mexer em nada ainda salva. */
  const irParaVincular = (prazoId: string) => {
    setVinculandoIds((atual) => new Set(atual).add(prazoId))
    setAndamentoEscolhido((m) => ({ ...m, [prazoId]: SEM_VINCULO }))
  }

  const confirmarComentario = (p: Prazo) => {
    const texto = (novoComentario[p.id] ?? '').trim()
    if (!texto) return
    const escolha = andamentoEscolhido[p.id]
    criarComentario.mutate({
      prazoId: p.id,
      texto,
      andamentoId: !escolha || escolha === SEM_VINCULO ? null : escolha,
      processoId: p.processo_id,
    })
  }

  const criarProcesso = async (data: { numero_cnj: string; cliente_id: string; estado: EstadoProcesso }): Promise<string> => {
    const p = await processosApi.criar(data)
    qc.invalidateQueries({ queryKey: ['processos'] })
    return p.id
  }

  const getProcesso = (id: string) => processos.find((p) => p.id === id)
  const getCliente = (processoId: string) => {
    const proc = getProcesso(processoId)
    return proc ? clientes.find((c) => c.id === proc.cliente_id) : undefined
  }

  const hoje = new Date(); hoje.setHours(0, 0, 0, 0)

  const estaVencido = (p: typeof prazos[number]) =>
    p.status === 'pendente' && !!p.data_limite && new Date(p.data_limite + 'T00:00:00') < hoje

  // "Ativo" = tudo que ainda não recebeu tratamento, VENCIDO INCLUSIVE. Antes o
  // vencido caía fora daqui e só sobrava em "Pendente", que é justamente onde
  // ninguém olha — prazo estourado sumia da tela em que devia gritar.
  const ehAtivo = (p: typeof prazos[number]) => p.status === 'pendente'

  const tabCounts: Record<TabStatus, number> = {
    todas: prazos.length,
    ativo: prazos.filter(ehAtivo).length,
    pendente: prazos.filter(p => p.status === 'pendente').length,
    cumprido: prazos.filter(p => p.status === 'cumprido').length,
    perdido: prazos.filter(p => p.status === 'perdido').length,
    ignorado: prazos.filter(p => p.status === 'ignorado').length,
    nada_a_fazer: prazos.filter(p => p.status === 'nada_a_fazer').length,
  }

  const vencidosSemTratamento = prazos.filter(estaVencido).length

  // Possível duplicata: o Diário Oficial (DJEN) e o Recorte Digital leem a mesma
  // comunicação e cada um gera seu prazo. Não unificamos nada automaticamente —
  // só sinalizamos, porque dois prazos no mesmo processo em dias próximos também
  // podem ser publicações realmente distintas (ex.: despacho + decisão).
  //
  // A primeira versão exigia data_limite IDÊNTICA e falhava justo nos piores
  // casos: quando uma das fontes está com a data errada, os limites divergem e
  // o par passava batido — que é exatamente quando avisar mais importa.
  // Agora o critério é o mesmo PROCESSO com publicações próximas: a mesma
  // comunicação chega às duas fontes com 0–3 dias de diferença (a do DJEN sai
  // na disponibilização, a do Recorte no dia útil seguinte, que atravessa fim
  // de semana). 5 dias dá folga para feriado emendado.
  const JANELA_DUPLICATA_DIAS = 5
  const diasEntre = (a?: string, b?: string) => {
    if (!a || !b) return Infinity
    return Math.abs(
      (new Date(a + 'T00:00:00').getTime() - new Date(b + 'T00:00:00').getTime())
      / (1000 * 60 * 60 * 24),
    )
  }
  const pendentes = prazos.filter((p) => p.status === 'pendente')
  const paresDuplicata = new Map<string, string>()  // id do prazo -> id do grupo
  for (const p of pendentes) {
    for (const o of pendentes) {
      if (o.id === p.id || o.processo_id !== p.processo_id) continue
      const proximos =
        diasEntre(p.data_publicacao, o.data_publicacao) <= JANELA_DUPLICATA_DIAS ||
        diasEntre(p.data_limite, o.data_limite) <= JANELA_DUPLICATA_DIAS
      if (!proximos) continue
      // Grupo identificado pelo menor id do par, para os dois cards caírem no
      // mesmo grupo independentemente da ordem em que foram varridos.
      const grupo = paresDuplicata.get(o.id) ?? (p.id < o.id ? p.id : o.id)
      paresDuplicata.set(p.id, grupo)
      paresDuplicata.set(o.id, grupo)
    }
  }
  const ehPossivelDuplicata = (p: typeof prazos[number]) => paresDuplicata.has(p.id)
  const chaveDuplicata = (p: typeof prazos[number]) =>
    paresDuplicata.get(p.id) ?? `${p.processo_id}|${p.data_limite ?? ''}`

  // Data de ordenação de cada grupo = a menor data limite entre seus membros,
  // para o grupo inteiro aterrissar junto na posição do mais urgente.
  // Dois mapas separados de propósito: o id do grupo É o id de um dos prazos,
  // então reaproveitar um único mapa misturaria as duas chaves.
  const dataDoGrupo = new Map<string, string>()
  for (const p of pendentes) {
    const grupo = paresDuplicata.get(p.id)
    if (!grupo || !p.data_limite) continue
    const atual = dataDoGrupo.get(grupo)
    if (!atual || p.data_limite < atual) dataDoGrupo.set(grupo, p.data_limite)
  }
  const ordemDuplicata = new Map<string, string>()
  for (const p of pendentes) {
    const grupo = paresDuplicata.get(p.id)
    const data = grupo ? dataDoGrupo.get(grupo) : undefined
    if (data) ordemDuplicata.set(p.id, data)
  }

  const prazosVisiveis = prazos
    .filter(p => {
      if (filtroMes.aplicar && !filtroMes.dentro(p.data_limite)) return false
      if (tabStatus === 'todas') return true
      if (tabStatus === 'ativo') return ehAtivo(p)
      if (tabStatus === 'pendente') return p.status === 'pendente'
      return p.status === tabStatus
    })
    .sort((a, b) => {
      if (tabStatus === 'ativo') {
        // Vencido primeiro: é o que precisa de decisão hoje.
        const v = Number(estaVencido(b)) - Number(estaVencido(a))
        if (v !== 0) return v
      }
      // Os membros de um grupo de duplicata ordenam pela MENOR data limite do
      // grupo, e não pela própria. Sem isso, um par com limites diferentes
      // (18/09 e 21/09 — o caso que motivou a mudança) voltaria a ficar
      // separado por todos os prazos que vencem no meio.
      const da = ordemDuplicata.get(a.id) ?? a.data_limite ?? '9999-12-31'
      const db = ordemDuplicata.get(b.id) ?? b.data_limite ?? '9999-12-31'
      if (da !== db) return da < db ? -1 : 1
      // Dentro do grupo, mantém a ordem cronológica real.
      const la = a.data_limite ?? '9999-12-31'
      const lb = b.data_limite ?? '9999-12-31'
      if (la !== lb) return la < lb ? -1 : 1
      return a.processo_id < b.processo_id ? -1 : a.processo_id > b.processo_id ? 1 : 0
    })

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Prazos</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <LegendaPrazos />
          <button
            className={prazosStyles.btnEditar}
            style={{ padding: '8px 12px', fontSize: 12 }}
            disabled={lembretes.isPending}
            title="Dispara agora o e-mail + Telegram de todos os prazos em aberto (a rotina automática roda às 07h30 todo dia)"
            onClick={() => { if (confirm('Enviar agora o lembrete de TODOS os prazos em aberto, por e-mail e Telegram?')) lembretes.mutate() }}
          >
            {lembretes.isPending ? 'Enviando...' : '🔔 Enviar lembretes agora'}
          </button>
          <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancelar' : '+ Novo Prazo'}
          </button>
        </div>
      </div>

      {vencidosSemTratamento > 0 && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', borderLeft: '4px solid #dc2626',
          borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 13, color: '#7f1d1d',
        }}>
          <strong>{vencidosSemTratamento} prazo(s) vencido(s) sem tratamento.</strong>{' '}
          Eles seguem na aba <em>Ativo</em>, em vermelho, e continuam gerando lembrete diário
          até serem marcados como cumprido, perdido, ignorado ou nada a fazer.
        </div>
      )}

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (!confirmaSeDiverge(form.peca_necessaria, form.dias_prazo, form.tipo_contagem ?? 'uteis')) return
            criar.mutate(form)
          }}
          className={styles.form}
        >
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Processo *</label>
            <ProcessoCombobox
              value={form.processo_id}
              onChange={(id) => {
                setForm({ ...form, processo_id: id })
                setRitoForm(getProcesso(id)?.rito ?? 'comum')
              }}
              processos={processos}
              clientes={clientes}
              onCreateProcesso={criarProcesso}
            />
          </div>
          <div className={prazosStyles.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Tipo *</label>
              <select className={styles.input} value={form.tipo}
                onChange={(e) => setForm({ ...form, tipo: e.target.value as TipoPrazo })}>
                {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Rito</label>
              <select className={styles.input} value={ritoForm}
                title="Juizados têm prazos e peças próprios — confirme ou troque se o cadastro do processo ainda não tiver o rito certo."
                onChange={(e) => setRitoForm(e.target.value as RitoProcesso)}>
                {RITO_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Peça necessária</label>
            <PecaCombobox
              value={form.peca_necessaria ?? ''}
              onChange={aplicarPecaNoForm}
              baseOptions={pecasPara(ritoForm)}
              onApplyDefault={(dias, tipoContagem) =>
                setForm((f) => ({ ...f, dias_prazo: dias, tipo_contagem: tipoContagem }))
              }
            />
          </div>

          {(() => {
            const sug = sugestaoDaPeca(catalogoLegal, form.peca_necessaria)
            if (!sug) return null
            const diverge = divergeDaLei(sug, form.dias_prazo, form.tipo_contagem ?? 'uteis')
            return (
              <div className={diverge ? prazosStyles.avisoDiverge : prazosStyles.avisoLegal}>
                <strong>
                  {sug.dias == null
                    ? `${sug.rotulo}: sem prazo em dias`
                    : `${sug.rotulo}: ${sug.dias} dia(s) ${sug.contagem === 'corridos' ? 'corridos' : 'úteis'}`}
                </strong>{' '}
                · {sug.fundamento}
                {diverge && <> — <strong>você lançou {form.dias_prazo} dia(s) {form.tipo_contagem === 'corridos' ? 'corridos' : 'úteis'}</strong>; será pedida confirmação ao salvar.</>}
                {sug.observacao && <div className={prazosStyles.avisoObs}>{sug.observacao}</div>}
              </div>
            )
          })()}
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data da Publicação *</label>
            <input type="date" className={styles.input} value={form.data_publicacao}
              onChange={(e) => setForm({ ...form, data_publicacao: e.target.value })} required />
          </div>
          <div className={prazosStyles.twoCol}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Dias do prazo *</label>
              <input type="number" className={styles.input} value={form.dias_prazo} min={1}
                onChange={(e) => setForm({ ...form, dias_prazo: Number(e.target.value) })} required />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>Contagem</label>
              <select className={styles.input} value={form.tipo_contagem}
                onChange={(e) => setForm({ ...form, tipo_contagem: e.target.value as 'uteis' | 'corridos' })}>
                <option value="uteis">Dias úteis</option>
                <option value="corridos">Dias corridos</option>
              </select>
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Responsável</label>
            <ResponsavelComboBox
              value={{ nome: form.responsavel ?? '', email: '', id: form.responsavel_id ?? null }}
              onChange={(v) => setForm({ ...form, responsavel: v.nome || undefined, responsavel_id: v.id ?? undefined })}
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição</label>
            <textarea className={styles.input} rows={2} value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
          </div>
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Calculando e salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {/* Status tabs */}
      {!isLoading && prazos.length > 0 && (
        <div className={prazosStyles.tabs}>
          {TABS.map((tab) => (
            <button
              key={tab}
              className={`${prazosStyles.tab} ${tabStatus === tab ? prazosStyles.tabActive : ''}`}
              onClick={() => setTabStatus(tab)}
            >
              {TAB_LABEL[tab]}
              <span className={prazosStyles.tabCount}>{tabCounts[tab]}</span>
            </button>
          ))}
        </div>
      )}

      {filtroMes.node}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : prazos.length === 0 ? (
        <p className={styles.empty}>Nenhum prazo cadastrado.</p>
      ) : prazosVisiveis.length === 0 ? (
        <p className={styles.empty}>Nenhum prazo nesta categoria.</p>
      ) : (
        <div className={prazosStyles.lista}>
          {prazosVisiveis.map((p, idx) => {
            const dias = diasRestantes(p.data_limite)
            const proc = getProcesso(p.processo_id)
            const cliente = getCliente(p.processo_id)
            const urg = urgenciaClass(dias, p.status, tabStatus)
            const vencido = estaVencido(p)
            const origem = p.publicacao_origem
            // Marca de agrupamento: como a lista está ordenada por data limite,
            // as duplicatas ficam vizinhas — a faixa lateral só precisa saber se
            // o card anterior/seguinte é do mesmo par pra desenhar o "colchete".
            const dup = ehPossivelDuplicata(p)
            const mesmaChave = (o?: typeof p) => !!o && ehPossivelDuplicata(o) && chaveDuplicata(o) === chaveDuplicata(p)
            const dupPrimeiro = dup && !mesmaChave(prazosVisiveis[idx - 1])
            const dupUltimo = dup && !mesmaChave(prazosVisiveis[idx + 1])
            return (
              <div key={p.id} ref={p.id === destaqueId ? destaqueRef : undefined}
                className={[
                  prazosStyles.card, urg,
                  dup ? prazosStyles.cardDup : '',
                  dupPrimeiro ? prazosStyles.cardDupTopo : '',
                  dupUltimo ? prazosStyles.cardDupBase : '',
                ].filter(Boolean).join(' ')}
                style={p.id === destaqueId ? { outline: '2px solid var(--teal)', outlineOffset: 2 } : undefined}>
                <div className={prazosStyles.cardHeader}>
                  <div className={prazosStyles.cardInfo}>
                    <div className={prazosStyles.cardTop}>
                      {vencido && <span className={prazosStyles.chipVencido}>⚠ Vencido</span>}
                      {ehPossivelDuplicata(p) && (
                        <span
                          className={prazosStyles.chipDuplicata}
                          title="Outro prazo pendente deste mesmo processo tem a mesma data limite — provavelmente a mesma publicação capturada pelo Diário Oficial e pelo Recorte Digital. Confira e trate um dos dois (ex.: 'ignorado')."
                        >
                          ⧉ Possível duplicata
                        </span>
                      )}
                      {p.status === 'nada_a_fazer' && (
                        <span className={prazosStyles.chipNadaAFazer}>🚫 Nada a fazer</span>
                      )}
                      {cliente && <span className={prazosStyles.clienteNome}>{cliente.nome}</span>}
                      <code className={prazosStyles.cnj}>{proc?.numero_cnj ?? p.processo_id.slice(0,8)}</code>
                      {proc?.materia && <span className={prazosStyles.materia}>{proc.materia}</span>}
                      {origem ? (
                        <a
                          className={prazosStyles.origemLink}
                          href={origem.origem_menu === 'recorte' ? '/diario2' : '/diario'}
                          title={origem.texto_resumo ?? undefined}
                        >
                          {origem.origem_menu === 'recorte' ? '📰 Recorte Digital' : '📰 Diário Oficial'}
                          {' · '}{formatDate(origem.data_publicacao)}
                        </a>
                      ) : (
                        /* Sem publicação vinculada: foi lançado à mão. Antes o card
                           simplesmente não trazia chip nenhum, e não dava pra saber
                           se era manual ou se o vínculo tinha se perdido. */
                        <span
                          className={prazosStyles.origemManual}
                          title="Prazo lançado manualmente — não veio de publicação do Diário Oficial nem do Recorte Digital"
                        >
                          ✍️ Manual · {formatDate(p.created_at.slice(0, 10))}
                        </span>
                      )}
                    </div>
                    <div className={prazosStyles.cardBottom}>
                      <span className={`${styles.badge} ${prazosStyles[`tipo_${p.tipo}`]}`}>{p.tipo}</span>
                      {p.criado_automaticamente && (
                        <span title="Criado automaticamente pelo gestor jurídico (Despacho)"
                          style={{ fontSize: 11, fontWeight: 700, color: '#7c3aed', background: '#f3e8ff', padding: '2px 8px', borderRadius: 999 }}>
                          🤖 Automático
                        </span>
                      )}
                      {(p.tarefas_vinculadas?.length ?? 0) > 0 && (
                        <a href="/tarefas" title={p.tarefas_vinculadas!.map(t => t.titulo).join('; ')}
                          style={{ fontSize: 11, fontWeight: 700, color: '#1d4ed8', background: '#dbeafe', padding: '2px 8px', borderRadius: 999, textDecoration: 'none' }}>
                          🔗 {p.tarefas_vinculadas!.length} tarefa(s)
                        </a>
                      )}
                      {p.peca_doc_url && (
                        <a href={p.peca_doc_url} target="_blank" rel="noreferrer"
                          style={{ fontSize: 11, fontWeight: 700, color: '#15803d', background: '#dcfce7', padding: '2px 8px', borderRadius: 999, textDecoration: 'none' }}>
                          📄 peça
                        </a>
                      )}
                      {p.peca_necessaria && editando !== p.id && (
                        <span className={prazosStyles.pecaChip}>
                          {p.peca_necessaria}
                          <button
                            className={prazosStyles.pecaChipEdit}
                            title="Alterar prazo"
                            onClick={() => abrirEditor(p)}
                          >✎</button>
                        </span>
                      )}
                      {editando !== p.id && (
                        <button className={prazosStyles.btnEditar} onClick={() => abrirEditor(p)}>
                          ✎ Alterar prazo
                        </button>
                      )}
                    </div>

                    {/* Linha própria e SEMPRE na mesma ordem: Disp. · Publicado ·
                        Limite · restantes · Resp. · lembrete. Antes as datas
                        dividiam a linha com os chips e, num card com mais chips
                        (Automático, tarefas), eram empurradas pra baixo — dois
                        cards vizinhos ficavam impossíveis de comparar a olho.
                        Cada campo ocupa a posição mesmo quando vazio ("—"). */}
                    <div className={prazosStyles.cardDatas}>
                      <span className={prazosStyles.dataItem} title="Data de disponibilização no diário">
                        <span className={prazosStyles.dataRotulo}>Disp.</span>
                        {origem?.data_disponibilizacao ? formatDate(origem.data_disponibilizacao) : '—'}
                      </span>
                      <span className={prazosStyles.dataItem} title="Data da publicação — base da contagem do prazo">
                        <span className={prazosStyles.dataRotulo}>Publicado</span>
                        {formatDate(p.data_publicacao)}
                      </span>
                      <span className={`${prazosStyles.dataItem} ${urg}`} title="Data limite do prazo">
                        <span className={prazosStyles.dataRotulo}>Limite</span>
                        <strong>{formatDate(p.data_limite)}</strong>
                      </span>
                      <span className={`${prazosStyles.dataItem} ${prazosStyles.restam} ${urg}`}>
                        {dias === null ? '—' : dias < 0 ? `${Math.abs(dias)}d atrás` : `${dias}d restantes`}
                      </span>
                      <span className={prazosStyles.dataItem} title="Responsável pelo prazo">
                        <span className={prazosStyles.dataRotulo}>Resp.</span>
                        {p.responsavel || '—'}
                      </span>
                      <span className={prazosStyles.dataItem} title="Último lembrete enviado por e-mail e Telegram">
                        <span className={prazosStyles.dataRotulo}>🔔</span>
                        {p.status === 'pendente' && p.ultimo_lembrete_em
                          ? formatDate(p.ultimo_lembrete_em.slice(0, 10))
                          : '—'}
                      </span>
                    </div>

                    {/* Motivo da perda: bloco próprio e por extenso — antes
                        vivia espremido na barra de ações, cortado em 30
                        caracteres com "..." (só o title/hover mostrava o
                        resto). Sempre visível por completo, em qualquer aba. */}
                    {p.status === 'perdido' && p.motivo_perda && (
                      <div className={prazosStyles.motivoPerda}>
                        <strong>Motivo da perda:</strong> {p.motivo_perda}
                      </div>
                    )}

                    {comentandoIds.has(p.id) && (
                      <div className={prazosStyles.comentPainel}>
                        {(p.comentarios?.length ?? 0) > 0 && (
                          <div className={prazosStyles.comentLista}>
                            {p.comentarios!.map((c) => (
                              <div key={c.id} className={prazosStyles.comentItem}>
                                <div className={prazosStyles.comentCabecalho}>
                                  <span className={prazosStyles.comentMeta}>
                                    {c.autor_nome || 'usuário'} · {formatDateTime(c.created_at)}
                                  </span>
                                  <button
                                    className={prazosStyles.comentRemover}
                                    title="Remover comentário"
                                    onClick={() => {
                                      if (confirm('Remover este comentário?')) {
                                        deletarComentario.mutate({ prazoId: p.id, comentarioId: c.id, processoId: p.processo_id })
                                      }
                                    }}
                                  >×</button>
                                </div>
                                <div className={prazosStyles.comentTexto}>{c.texto}</div>
                                {c.andamento_id ? (
                                  <div className={prazosStyles.comentVinculo}>⧉ vinculado a um andamento do processo</div>
                                ) : (
                                  <div className={prazosStyles.comentSemVinculo}>◻ não vinculado a andamento</div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}

                        {vinculandoIds.has(p.id) ? (
                          <div className={prazosStyles.comentNovo}>
                            <div className={prazosStyles.comentPreview}>"{novoComentario[p.id]}"</div>
                            <AndamentoPicker
                              processoId={p.processo_id}
                              selecionado={andamentoEscolhido[p.id] ?? SEM_VINCULO}
                              onSelecionar={(v) => setAndamentoEscolhido((m) => ({ ...m, [p.id]: v }))}
                              semVinculo={SEM_VINCULO}
                            />
                            <div className={prazosStyles.editorActions}>
                              <button className={styles.btnPrimary} style={{ fontSize: 12, padding: '6px 12px' }}
                                disabled={criarComentario.isPending}
                                onClick={() => confirmarComentario(p)}>
                                {criarComentario.isPending ? 'Salvando...' : 'Confirmar comentário'}
                              </button>
                              <button className={styles.btnDanger}
                                onClick={() => setVinculandoIds((atual) => { const n = new Set(atual); n.delete(p.id); return n })}>
                                Voltar
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className={prazosStyles.comentNovo}>
                            <textarea
                              className={styles.input}
                              rows={2}
                              placeholder="Anotar algo sobre este prazo (ex.: por que não recorremos, o que o cliente decidiu...)"
                              value={novoComentario[p.id] ?? ''}
                              onChange={(e) => setNovoComentario((m) => ({ ...m, [p.id]: e.target.value }))}
                            />
                            <button
                              className={styles.btnPrimary}
                              style={{ fontSize: 12, padding: '6px 12px', alignSelf: 'flex-start' }}
                              disabled={!(novoComentario[p.id] ?? '').trim()}
                              onClick={() => irParaVincular(p.id)}
                            >
                              Salvar comentário
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {editando === p.id && editForm && (
                      <div className={prazosStyles.editor}>
                        <div className={prazosStyles.editorField}>
                          <span className={prazosStyles.editorLabel}>Processo</span>
                          <ProcessoCombobox
                            value={editForm.processo_id}
                            onChange={(id) => {
                              setEditForm({ ...editForm, processo_id: id })
                              setRitoEdit(getProcesso(id)?.rito ?? 'comum')
                            }}
                            processos={processos}
                            clientes={clientes}
                            onCreateProcesso={criarProcesso}
                          />
                        </div>
                        <div className={prazosStyles.editorGrid}>
                          <div className={prazosStyles.editorField}>
                            <span className={prazosStyles.editorLabel}>Tipo</span>
                            <select className={styles.input} value={editForm.tipo}
                              onChange={(e) => setEditForm({ ...editForm, tipo: e.target.value as TipoPrazo })}>
                              {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
                            </select>
                          </div>
                          <div className={prazosStyles.editorField}>
                            <span className={prazosStyles.editorLabel}>Rito</span>
                            <select className={styles.input} value={ritoEdit}
                              title="Juizados têm prazos e peças próprios."
                              onChange={(e) => setRitoEdit(e.target.value as RitoProcesso)}>
                              {RITO_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                            </select>
                          </div>
                          <div className={prazosStyles.editorField}>
                            <span className={prazosStyles.editorLabel}>Peça necessária</span>
                            <PecaCombobox
                              value={editForm.peca_necessaria}
                              onChange={(peca) => {
                                const sug = sugestaoDaPeca(catalogoLegal, peca)
                                setEditForm({
                                  ...editForm,
                                  peca_necessaria: peca,
                                  ...(sug?.dias != null
                                    ? { dias_prazo: sug.dias, tipo_contagem: (sug.contagem ?? 'uteis') as TipoContagem }
                                    : {}),
                                })
                              }}
                              baseOptions={pecasPara(ritoEdit)}
                              onApplyDefault={(dias, tipoContagem) =>
                                setEditForm((f) => f ? { ...f, dias_prazo: dias, tipo_contagem: tipoContagem } : f)
                              }
                            />
                          </div>
                          <div className={prazosStyles.editorField}>
                            <span className={prazosStyles.editorLabel}>Data da publicação</span>
                            <input type="date" className={styles.input} value={editForm.data_publicacao}
                              onChange={(e) => setEditForm({ ...editForm, data_publicacao: e.target.value })} />
                          </div>
                          <div className={prazosStyles.editorField}>
                            <span className={prazosStyles.editorLabel}>Dias do prazo</span>
                            <input type="number" min={0} className={styles.input} value={editForm.dias_prazo}
                              onChange={(e) => setEditForm({ ...editForm, dias_prazo: Number(e.target.value) })} />
                          </div>
                          <div className={prazosStyles.editorField}>
                            <span className={prazosStyles.editorLabel}>Contagem</span>
                            <select className={styles.input} value={editForm.tipo_contagem}
                              onChange={(e) => setEditForm({ ...editForm, tipo_contagem: e.target.value as TipoContagem })}>
                              <option value="uteis">Dias úteis</option>
                              <option value="corridos">Dias corridos</option>
                            </select>
                          </div>
                          <div className={prazosStyles.editorField}>
                            <span className={prazosStyles.editorLabel}>Responsável</span>
                            <ResponsavelComboBox
                              value={editForm.responsavel}
                              onChange={(v) => setEditForm({ ...editForm, responsavel: v })}
                            />
                          </div>
                        </div>
                        <div className={prazosStyles.editorField}>
                          <span className={prazosStyles.editorLabel}>Descrição</span>
                          <textarea className={styles.input} rows={2} value={editForm.descricao}
                            onChange={(e) => setEditForm({ ...editForm, descricao: e.target.value })} />
                        </div>
                        {(() => {
                          const sug = sugestaoDaPeca(catalogoLegal, editForm.peca_necessaria)
                          if (!sug) return null
                          const diverge = divergeDaLei(sug, editForm.dias_prazo, editForm.tipo_contagem)
                          return (
                            <div className={diverge ? prazosStyles.avisoDiverge : prazosStyles.avisoLegal}>
                              <strong>
                                {sug.dias == null
                                  ? `${sug.rotulo}: sem prazo em dias`
                                  : `${sug.rotulo}: ${sug.dias} dia(s) ${sug.contagem === 'corridos' ? 'corridos' : 'úteis'}`}
                              </strong>{' '}· {sug.fundamento}
                              {diverge && <> — <strong>fora do prazo legal</strong>; será pedida confirmação.</>}
                            </div>
                          )
                        })()}
                        <div className={prazosStyles.editorActions}>
                          <button className={styles.btnPrimary} style={{ fontSize: 12, padding: '6px 12px' }}
                            disabled={atualizar.isPending}
                            onClick={() => salvarEdicao(p.id)}>
                            {atualizar.isPending ? 'Recalculando...' : 'Salvar'}
                          </button>
                          <button className={styles.btnDanger}
                            onClick={() => { setEditando(null); setEditForm(null) }}>Cancelar</button>
                          <span className={prazosStyles.editorHint}>
                            A data limite é recalculada com os feriados do estado do processo.
                            {origem && ' A alteração aparece também no menu de origem da publicação.'}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className={prazosStyles.cardActions}>
                    <select className={prazosStyles.statusSelect} value={p.status}
                      onChange={(e) => {
                        const novo = e.target.value as StatusPrazo
                        if (novo === 'nada_a_fazer' && !confirm(
                          'Marcar como "Nada a fazer"?\n\nA publicação de origem é encerrada e as tarefas automáticas ' +
                          'ligadas a este prazo são canceladas.',
                        )) return
                        if (novo === 'perdido') {
                          const motivo = pedirMotivoPerda()
                          if (motivo === null) return
                          atualizar.mutate({ id: p.id, data: { status: novo, motivo_perda: motivo } })
                          return
                        }
                        atualizar.mutate({ id: p.id, data: { status: novo } })
                      }}>
                      {STATUS_OPCOES.map((s) => (
                        <option key={s.valor} value={s.valor}>{s.label}</option>
                      ))}
                    </select>
                    <button
                      className={`${prazosStyles.btnEditar} ${comentandoIds.has(p.id) ? prazosStyles.btnComentarioAtivo : ''}`}
                      title="Anotar algo sobre este prazo — a anotação fica guardada aqui pra explicar depois por que um ato foi ou não praticado"
                      onClick={() => toggleComentarios(p.id)}
                    >
                      💬{(p.comentarios?.length ?? 0) > 0 ? ` ${p.comentarios!.length}` : ''}
                    </button>
                    <button className={styles.btnDanger}
                      onClick={() => { if (confirm('Remover prazo?')) deletar.mutate(p.id) }}>
                      ×
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
