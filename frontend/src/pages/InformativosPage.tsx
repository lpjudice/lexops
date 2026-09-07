import { Fragment, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { erroApi, informativosApi } from '../api/informativos'
import type { Citacao, Informativo, StatusInformativo } from '../api/informativos'
import { instagramApi } from '../api/instagram'
import { conselhoApi } from '../api/conselho'
import ResponsavelComboBox from '../components/ResponsavelComboBox'
import type { ResponsavelValue } from '../components/ResponsavelComboBox'
import Modal from '../components/Modal'
import styles from './Page.module.css'

const STATUS_LABEL: Record<StatusInformativo, string> = {
  rascunho: 'Rascunho',
  primeiro_draft: '1º draft',
  revisado: 'Revisado',
  publicado: 'Publicado',
}

// Fundo escuro + texto branco em todos — contraste garantido independente do tema da página.
const STATUS_COR: Record<StatusInformativo, string> = {
  rascunho: '#6b7280',
  primeiro_draft: '#b45309',
  revisado: '#1d4ed8',
  publicado: '#15803d',
}

function StatusBadge({ status }: { status: StatusInformativo }) {
  return (
    <span
      className={styles.badge}
      style={{ background: STATUS_COR[status], color: '#fff' }}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}

function fmtMes(iso: string) {
  const [ano, mes] = iso.split('-')
  return new Date(Number(ano), Number(mes) - 1, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
}

function fmtData(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR')
}

function proximoMesReferencia(): string {
  const hoje = new Date()
  const proximo = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 1)
  return `${proximo.getFullYear()}-${String(proximo.getMonth() + 1).padStart(2, '0')}-01`
}

type Periodo = 'mes_atual' | 'proximo_mes' | '3m' | '6m' | '12m' | 'todos'

const PERIODO_LABEL: Record<Periodo, string> = {
  mes_atual: 'Mês atual',
  proximo_mes: 'Próximo mês',
  '3m': 'Últimos 3 meses',
  '6m': 'Últimos 6 meses',
  '12m': 'Últimos 12 meses',
  todos: 'Todos',
}

// diffMeses = quantos meses o mes_referencia está à frente do mês atual
// (0 = mês atual, 1 = próximo mês, -1 = mês passado...).
function diffMesesDeHoje(mesRefIso: string): number {
  const hoje = new Date()
  const [ano, mes] = mesRefIso.split('-').map(Number)
  return (ano - hoje.getFullYear()) * 12 + (mes - 1 - hoje.getMonth())
}

function dentroDoPeriodo(mesRefIso: string, periodo: Periodo): boolean {
  const diff = diffMesesDeHoje(mesRefIso)
  switch (periodo) {
    case 'mes_atual': return diff === 0
    case 'proximo_mes': return diff === 1
    case '3m': return diff <= 1 && diff >= -2
    case '6m': return diff <= 1 && diff >= -5
    case '12m': return diff <= 1 && diff >= -11
    case 'todos': return true
  }
}

export default function InformativosPage() {
  const qc = useQueryClient()
  const { data: informativos = [], isLoading } = useQuery({
    queryKey: ['informativos'],
    queryFn: () => informativosApi.listar(),
  })
  const { data: padrao } = useQuery({
    queryKey: ['informativos', 'responsavel-padrao'],
    queryFn: () => informativosApi.responsavelPadrao(),
  })
  const { data: template } = useQuery({
    queryKey: ['informativos', 'template'],
    queryFn: () => informativosApi.obterTemplate(),
  })

  const [modalCriar, setModalCriar] = useState(false)
  const [sugestaoParaCriar, setSugestaoParaCriar] = useState<string | null>(null)
  const [recusadas, setRecusadas] = useState<string[]>([])
  const [sugestoesExpandido, setSugestoesExpandido] = useState(false)
  const [selecionadoId, setSelecionadoId] = useState<string | null>(null)
  const [expandidoId, setExpandidoId] = useState<string | null>(null)
  const [periodo, setPeriodo] = useState<Periodo>('3m')
  const selecionado = informativos.find((i) => i.id === selecionadoId) ?? null

  const informativosFiltrados = informativos
    .filter((i) => dentroDoPeriodo(i.mes_referencia, periodo))
    .sort((a, b) => (b.numero ?? -1) - (a.numero ?? -1))

  const usedSugestaoIds = new Set(informativos.map((i) => i.tema_sugestao_id).filter(Boolean) as string[])

  const { data: sugestoesInstagramBrutas = [] } = useQuery({
    queryKey: ['instagram', 'sugestoes-tema', 'sugerido'],
    queryFn: () => instagramApi.listar('sugerido'),
    staleTime: 30_000,
  })
  // Mais recentes primeiro, sem as já usadas em algum informativo, sem
  // duplicatas de título (o Instagram às vezes repete o mesmo tema) e
  // limitado a 100 — igual usado no combobox de criação.
  const sugestoesInstagram = (() => {
    const vistos = new Set<string>()
    return [...sugestoesInstagramBrutas]
      .filter((s) => !usedSugestaoIds.has(s.id))
      .sort((a, b) => (b.data_geracao || '').localeCompare(a.data_geracao || ''))
      .filter((s) => {
        const chave = s.titulo.trim().toLowerCase()
        if (vistos.has(chave)) return false
        vistos.add(chave)
        return true
      })
      .slice(0, 100)
  })()
  const sugestoesVisiveis = sugestoesInstagram.filter((s) => !recusadas.includes(s.id)).slice(0, 10)

  const criarMutation = useMutation({
    mutationFn: informativosApi.criar,
    onSuccess: (informativo) => {
      qc.invalidateQueries({ queryKey: ['informativos'] })
      setModalCriar(false)
      setSugestaoParaCriar(null)
      setSelecionadoId(informativo.id)
    },
  })

  const abrirCriarComSugestao = (sugestaoId: string) => {
    setSugestaoParaCriar(sugestaoId)
    setModalCriar(true)
  }

  const responsavelPadraoMutation = useMutation({
    mutationFn: (id: string | null) => informativosApi.definirResponsavelPadrao(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativos', 'responsavel-padrao'] }),
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Informativos</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12.5, color: '#6b7280' }}>Responsável padrão:</span>
            <div style={{ width: 190 }}>
              <ResponsavelComboBox
                value={{ id: padrao?.id ?? null, nome: padrao?.nome ?? '', email: padrao?.email ?? '' }}
                onChange={(v) => responsavelPadraoMutation.mutate(v.id ?? null)}
              />
            </div>
          </div>
          {template?.template_doc_link && (
            <a href={template.template_doc_link} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
              Editar modelo padrão
            </a>
          )}
          <button className={styles.btnPrimary} onClick={() => { setSugestaoParaCriar(null); setModalCriar(true) }}>
            + Novo informativo
          </button>
        </div>
      </div>

      {sugestoesInstagram.length > 0 && (
        <div style={{ marginBottom: 16, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fafafa' }}>
          <button
            onClick={() => setSugestoesExpandido((v) => !v)}
            style={{
              width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer',
              padding: '10px 14px', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase',
              letterSpacing: 0.4, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}
          >
            <span>Sugestões de tema (do Instagram) — {sugestoesVisiveis.length}</span>
            <span>{sugestoesExpandido ? '▲' : '▼'}</span>
          </button>
          {sugestoesExpandido && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '0 14px 12px' }}>
              {sugestoesVisiveis.map((s) => (
                <div
                  key={s.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, border: '1px solid #e5e7eb', borderRadius: 6,
                    padding: '8px 10px', background: '#fff',
                  }}
                >
                  <span style={{ flex: 1, fontSize: 13 }}>{s.titulo}</span>
                  <button className={styles.btnTable} style={{ fontSize: 11.5, flexShrink: 0 }} onClick={() => abrirCriarComSugestao(s.id)}>
                    Usar este tema
                  </button>
                  <button
                    className={styles.btnTable}
                    style={{ fontSize: 11.5, color: '#9ca3af', flexShrink: 0 }}
                    title="Recusar sugestão"
                    onClick={() => setRecusadas((r) => [...r, s.id])}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 12.5, color: '#6b7280' }}>Período:</span>
        <select className={styles.input} style={{ width: 'auto', padding: '4px 8px', fontSize: 12.5 }} value={periodo} onChange={(e) => setPeriodo(e.target.value as Periodo)}>
          {(Object.keys(PERIODO_LABEL) as Periodo[]).map((p) => (
            <option key={p} value={p}>{PERIODO_LABEL[p]}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <p>Carregando...</p>
      ) : informativos.length === 0 ? (
        <p className={styles.empty}>Nenhum informativo criado ainda.</p>
      ) : informativosFiltrados.length === 0 ? (
        <p className={styles.empty}>Nenhum informativo neste período.</p>
      ) : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Nº</th>
                <th>Mês</th>
                <th>Título</th>
                <th>Status</th>
                <th>Prazo 1º draft</th>
                <th>Prazo final</th>
                <th>Páginas</th>
                <th></th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {informativosFiltrados.map((i) => (
                <Fragment key={i.id}>
                  <tr onClick={() => setSelecionadoId(i.id)} style={{ cursor: 'pointer' }}>
                    <td>{i.numero ?? '—'}</td>
                    <td style={{ textTransform: 'capitalize' }}>{fmtMes(i.mes_referencia)}</td>
                    <td>{i.titulo}</td>
                    <td><StatusBadge status={i.status} /></td>
                    <td>{fmtData(i.data_prazo_draft)}</td>
                    <td>{fmtData(i.data_prazo_final)}</td>
                    <td>{i.paginas_estimadas ?? '—'}</td>
                    <td>
                      <button className={styles.btnTable} onClick={(e) => { e.stopPropagation(); setSelecionadoId(i.id) }}>
                        Abrir
                      </button>
                    </td>
                    <td>
                      {i.status === 'publicado' && (
                        <button
                          className={styles.btnTable}
                          onClick={(e) => { e.stopPropagation(); setExpandidoId(expandidoId === i.id ? null : i.id) }}
                          title="Distribuição"
                        >
                          {expandidoId === i.id ? '▲ Distribuir' : '▼ Distribuir'}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandidoId === i.id && (
                    <tr>
                      <td colSpan={9} style={{ background: '#fafafa', padding: 0 }}>
                        <DistribuicaoPanel informativo={i} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalCriar && (
        <ModalCriar
          responsavelPadrao={padrao ?? null}
          sugestaoInicialId={sugestaoParaCriar}
          usedSugestaoIds={usedSugestaoIds}
          onFechar={() => { setModalCriar(false); setSugestaoParaCriar(null) }}
          onCriar={(dados) => criarMutation.mutate(dados)}
          salvando={criarMutation.isPending}
        />
      )}

      {selecionado && (
        <DetalheInformativo
          informativo={selecionado}
          onFechar={() => setSelecionadoId(null)}
        />
      )}
    </div>
  )
}

function TemaSugestaoComboBox({
  sugestoes,
  value,
  onSelect,
}: {
  sugestoes: { id: string; titulo: string }[]
  value: string
  onSelect: (s: { id: string; titulo: string } | null) => void
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const selecionado = sugestoes.find((s) => s.id === value)
  const filtrados = query
    ? sugestoes.filter((s) => s.titulo.toLowerCase().includes(query.toLowerCase()))
    : sugestoes

  return (
    <div style={{ position: 'relative' }}>
      <input
        className={styles.input}
        placeholder="— Nenhum, título livre — (digite pra pesquisar)"
        value={open ? query : (selecionado?.titulo ?? '')}
        onFocus={() => { setOpen(true); setQuery('') }}
        onChange={(e) => setQuery(e.target.value)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (
        <div style={{
          position: 'absolute', left: 0, right: 0, top: '100%', zIndex: 50, background: '#fff',
          border: '1px solid #e5e7eb', borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,.1)',
          maxHeight: 240, overflowY: 'auto', marginTop: 2,
        }}>
          <div
            style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13, color: '#6b7280', fontStyle: 'italic' }}
            onMouseDown={() => { onSelect(null); setOpen(false) }}
          >
            — Nenhum, título livre —
          </div>
          {filtrados.length === 0 && (
            <div style={{ padding: '8px 12px', fontSize: 13, color: '#9ca3af' }}>Nenhuma sugestão encontrada</div>
          )}
          {filtrados.map((s) => (
            <div
              key={s.id}
              style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13, borderTop: '1px solid #f9fafb' }}
              onMouseDown={() => { onSelect(s); setOpen(false) }}
            >
              {s.titulo}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ModalCriar({
  responsavelPadrao,
  sugestaoInicialId,
  usedSugestaoIds,
  onFechar,
  onCriar,
  salvando,
}: {
  responsavelPadrao: { id: string; nome: string; email: string | null } | null
  sugestaoInicialId?: string | null
  usedSugestaoIds: Set<string>
  onFechar: () => void
  onCriar: (dados: {
    mes_referencia: string
    titulo: string
    responsavel_id: string | null
    tema_resumido?: string | null
    tema_sugestao_id?: string | null
  }) => void
  salvando: boolean
}) {
  const [mesReferencia, setMesReferencia] = useState(proximoMesReferencia())
  const [temaSugestaoId, setTemaSugestaoId] = useState(sugestaoInicialId ?? '')

  const { data: sugestoesBrutas = [] } = useQuery({
    queryKey: ['instagram', 'sugestoes-tema'],
    queryFn: () => instagramApi.listar(),
    staleTime: 30_000,
  })
  const sugestoesInstagram = [...sugestoesBrutas]
    .filter((s) => !usedSugestaoIds.has(s.id))
    .sort((a, b) => (b.data_geracao || '').localeCompare(a.data_geracao || ''))
    .slice(0, 100)

  const [titulo, setTitulo] = useState('')
  const [responsavel, setResponsavel] = useState<ResponsavelValue>({
    id: responsavelPadrao?.id ?? null,
    nome: responsavelPadrao?.nome ?? '',
    email: responsavelPadrao?.email ?? '',
  })

  const sugestaoSelecionada = sugestoesInstagram.find((s) => s.id === temaSugestaoId)

  useEffect(() => {
    if (sugestaoInicialId && !titulo && sugestaoSelecionada) setTitulo(sugestaoSelecionada.titulo)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sugestaoSelecionada])

  return (
    <Modal onClose={onFechar} title="Novo informativo">
      <div className={styles.form}>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 0 }}>
          Isso cria a pasta do mês no Drive e um Google Doc já com o modelo do escritório
          (cabeçalho, número, mês) preenchido. O texto você escreve depois, na tela seguinte.
        </p>
        <div className={styles.fieldGroup}>
          <label className={styles.formLabel}>Mês de referência</label>
          <input
            className={styles.input}
            type="month"
            value={mesReferencia.slice(0, 7)}
            onChange={(e) => setMesReferencia(`${e.target.value}-01`)}
          />
        </div>
        {sugestoesInstagram.length > 0 && (
          <div className={styles.fieldGroup}>
            <label className={styles.formLabel}>Partir de um tema já sugerido no Instagram (opcional)</label>
            <TemaSugestaoComboBox
              sugestoes={sugestoesInstagram}
              value={temaSugestaoId}
              onSelect={(s) => {
                setTemaSugestaoId(s?.id ?? '')
                if (s && !titulo.trim()) setTitulo(s.titulo)
              }}
            />
          </div>
        )}
        <div className={styles.fieldGroup}>
          <label className={styles.formLabel}>Título</label>
          <input
            className={styles.input}
            placeholder="Ex.: IVA Dual nas Empresas de Locação"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
          />
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.formLabel}>Responsável</label>
          <ResponsavelComboBox value={responsavel} onChange={setResponsavel} />
        </div>
        <button
          className={styles.btnPrimary}
          disabled={salvando || !titulo.trim()}
          onClick={() =>
            onCriar({
              mes_referencia: mesReferencia,
              titulo: titulo.trim(),
              responsavel_id: responsavel.id ?? null,
              tema_resumido: sugestaoSelecionada?.tema || titulo.trim(),
              tema_sugestao_id: temaSugestaoId || null,
            })
          }
        >
          {salvando ? 'Criando...' : 'Criar informativo'}
        </button>
      </div>
    </Modal>
  )
}

function Passo({
  numero,
  titulo,
  descricao,
  children,
}: {
  numero: number
  titulo: string
  descricao?: string
  children: React.ReactNode
}) {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '14px 0', borderBottom: '1px solid #f1f1f1' }}>
      <div style={{
        flexShrink: 0, width: 24, height: 24, borderRadius: '50%', background: '#f3f4f6',
        color: '#374151', fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center',
        justifyContent: 'center',
      }}>
        {numero}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>{titulo}</div>
        {descricao && <div style={{ fontSize: 12.5, color: '#6b7280', marginBottom: 8 }}>{descricao}</div>}
        {children}
      </div>
    </div>
  )
}

const CITACAO_STATUS_LABEL: Record<string, string> = {
  confirmado: '✓ Confirmado',
  divergente: '⚠ Divergente',
  nao_encontrado: '? Não encontrado',
}
const CITACAO_STATUS_COR: Record<string, string> = {
  confirmado: '#15803d',
  divergente: '#b45309',
  nao_encontrado: '#6b7280',
}

function CitacaoCard({ citacao }: { citacao: Citacao }) {
  const ref = citacao.referencia_original || {}
  const rotulo = ref.trecho_citado || [ref.tribunal, ref.numero].filter(Boolean).join(' ') || 'Citação'
  const cor = CITACAO_STATUS_COR[citacao.status_geral] || '#6b7280'
  return (
    <div style={{ border: '1px solid #e5e7eb', borderLeft: `4px solid ${cor}`, borderRadius: 6, padding: '10px 12px', marginTop: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, fontSize: 13 }}>{rotulo}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: cor }}>
          {CITACAO_STATUS_LABEL[citacao.status_geral] || citacao.status_geral}
        </span>
      </div>
      {citacao.observacao && (
        <p style={{ fontSize: 12.5, color: '#374151', margin: '6px 0 0', lineHeight: 1.5 }}>{citacao.observacao}</p>
      )}
      {citacao.texto_integral && (
        <div style={{ marginTop: 8, background: '#f9fafb', borderRadius: 4, padding: '8px 10px' }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 4, textTransform: 'uppercase' }}>
            Texto oficial do dispositivo
          </div>
          <p style={{ fontSize: 12.5, color: '#1f2937', margin: 0, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
            {citacao.texto_integral}
          </p>
          {citacao.url_oficial && (
            <a href={citacao.url_oficial} target="_blank" rel="noreferrer" style={{ fontSize: 12, display: 'inline-block', marginTop: 6 }}>
              Ver no Planalto →
            </a>
          )}
        </div>
      )}
      {typeof citacao.custo_usd === 'number' && citacao.custo_usd > 0 && (
        <div style={{ fontSize: 10.5, color: '#9ca3af', marginTop: 6 }}>custo: ${citacao.custo_usd.toFixed(4)}</div>
      )}
    </div>
  )
}

function ResultadoCitacoes({ citacoes }: { citacoes: Citacao[] }) {
  if (citacoes.length === 0) {
    return <p style={{ fontSize: 13, color: '#6b7280', marginTop: 8 }}>Não há citações de lei ou julgado no texto.</p>
  }
  return (
    <div>
      {citacoes.map((c, idx) => (
        <CitacaoCard key={idx} citacao={c} />
      ))}
    </div>
  )
}

function fmtDataHora(iso?: string | null) {
  if (!iso) return null
  return new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// Mesma técnica do módulo Eventos (Expansão): encodeURIComponent trata bem a maioria dos
// casos, mas emojis fora do plano básico (4 bytes) o WhatsApp Desktop não decodifica —
// manter esses como caracteres crus resolve.
function encodeWaText(text: string): string {
  return encodeURIComponent(text).replace(
    /%[Ff][0-4](?:%[89ABab][0-9A-Fa-f]){3}/g,
    (m) => decodeURIComponent(m),
  )
}

function linkPublicoInformativo(id: string): string {
  return `https://www.pimentajudice.com.br/informativos/ler/${id}`
}

function textoWhatsappPadrao(informativo: Informativo, resumo: string | null): string {
  const numero = informativo.numero ? `Nº ${informativo.numero} / ` : ''
  const link = linkPublicoInformativo(informativo.id)
  return [
    '*Informativo Pimenta Judice Advogados:*',
    '',
    `📌 ${numero}${fmtMes(informativo.mes_referencia)}`,
    '',
    `*${informativo.titulo}*`,
    `📝 Resumo: ${resumo || '(resumo ainda não disponível — confira no link abaixo)'}`,
    '',
    `🔗 ${link}`,
  ].join('\n')
}

function DistribuicaoPanel({ informativo }: { informativo: Informativo }) {
  const [enviarResultado, setEnviarResultado] = useState<{ enviados: number; total: number; erros: number } | null>(null)
  const [emailTeste, setEmailTeste] = useState('')
  const [testeResultado, setTesteResultado] = useState<string | null>(null)
  const [telefoneTeste, setTelefoneTeste] = useState('')

  const chaveTexto = `informativos:whatsapp-texto:${informativo.id}`
  const chaveTextoAuto = `informativos:whatsapp-texto-auto:${informativo.id}`
  const chaveEnviados = `informativos:whatsapp-enviados:${informativo.id}`
  const [textoWhatsapp, setTextoWhatsapp] = useState(() => localStorage.getItem(chaveTexto) || '')
  const [enviadosWhatsapp, setEnviadosWhatsapp] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem(chaveEnviados) || '[]')) } catch { return new Set() }
  })

  const { data: resumoPerguntas } = useQuery({
    queryKey: ['informativos', informativo.id, 'resumo-perguntas'],
    queryFn: () => informativosApi.resumoPerguntas(informativo.id),
  })
  useEffect(() => {
    // Preenche/atualiza o padrão automaticamente enquanto o usuário não
    // editou o texto manualmente — se o texto atual ainda é igual ao último
    // gerado automaticamente (ou está vazio), acompanha o resumo assim que
    // ele fica disponível no Doc. Uma edição manual do usuário deixa de bater
    // com o "auto" salvo, então para de ser sobrescrita.
    if (resumoPerguntas === undefined) return
    const textoAtual = localStorage.getItem(chaveTexto) || ''
    const ultimoAuto = localStorage.getItem(chaveTextoAuto) || ''
    if (textoAtual && textoAtual !== ultimoAuto) return
    const novo = textoWhatsappPadrao(informativo, resumoPerguntas?.resumo ?? null)
    if (novo === textoAtual) return
    localStorage.setItem(chaveTextoAuto, novo)
    localStorage.setItem(chaveTexto, novo)
    setTextoWhatsapp(novo)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumoPerguntas])

  const { data: destinatarios } = useQuery({
    queryKey: ['informativos', informativo.id, 'newsletter-destinatarios'],
    queryFn: () => informativosApi.destinatariosNewsletter(informativo.id),
  })
  const { data: contatos = [] } = useQuery({
    queryKey: ['conselho', 'contatos', 'whatsapp'],
    queryFn: () => conselhoApi.listarContatos(),
    staleTime: 60_000,
  })
  const contatosWhatsapp = contatos.filter((c) => c.whatsapp)

  const enviarMutation = useMutation({
    mutationFn: () => informativosApi.enviarNewsletter(informativo.id),
    onSuccess: (res) => setEnviarResultado(res),
  })
  const testeMutation = useMutation({
    mutationFn: () => informativosApi.newsletterTeste(informativo.id, emailTeste),
    onSuccess: () => setTesteResultado(`Teste enviado pra ${emailTeste}.`),
  })

  const handleEnviar = () => {
    const n = destinatarios?.total ?? 0
    if (window.confirm(`Enviar a newsletter (resumo + link + PDF) para ${n} destinatário(s)? Essa ação não pode ser desfeita.`)) {
      enviarMutation.mutate()
    }
  }

  const salvarTexto = (v: string) => {
    setTextoWhatsapp(v)
    localStorage.setItem(chaveTexto, v)
  }
  const toggleEnviado = (contatoId: string) => {
    const novo = new Set(enviadosWhatsapp)
    if (novo.has(contatoId)) novo.delete(contatoId); else novo.add(contatoId)
    setEnviadosWhatsapp(novo)
    localStorage.setItem(chaveEnviados, JSON.stringify([...novo]))
  }
  const waLink = (numero: string) => `https://wa.me/${numero.replace(/\D/g, '')}?text=${encodeWaText(textoWhatsapp)}`

  return (
    <div style={{ padding: '14px 20px', display: 'flex', gap: 28, flexWrap: 'wrap' }}>
      <div style={{ flex: '1 1 280px', minWidth: 260, maxWidth: 320 }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>Newsletter por e-mail</div>
        <p style={{ fontSize: 12.5, color: '#6b7280', margin: '0 0 8px' }}>
          {destinatarios ? `${destinatarios.total} destinatário(s)` : 'Carregando destinatários...'}
          {destinatarios && destinatarios.exemplos.length > 0 && (
            <span title={destinatarios.exemplos.join(', ')}> (Clientes + Contatos + inscritos no site)</span>
          )}
        </p>
        <button className={styles.btnSmall} onClick={handleEnviar} disabled={enviarMutation.isPending || !destinatarios?.total}>
          {enviarMutation.isPending ? 'Enviando...' : 'Enviar newsletter pra todos'}
        </button>
        {enviarMutation.isError && <p style={{ color: '#b91c1c', fontSize: 12.5 }}>{erroApi(enviarMutation.error)}</p>}
        {enviarResultado && (
          <p style={{ fontSize: 12.5, color: '#15803d', marginTop: 6 }}>
            Enviado pra {enviarResultado.enviados}/{enviarResultado.total} {enviarResultado.erros > 0 && `(${enviarResultado.erros} falha(s))`}
          </p>
        )}

        <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid #e5e7eb' }}>
          <label className={styles.formLabel} style={{ display: 'block', fontSize: 11.5 }}>Testar antes de enviar pra todos</label>
          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
            <input
              className={styles.input}
              style={{ fontSize: 12.5, padding: '5px 8px' }}
              placeholder="seu@email.com"
              value={emailTeste}
              onChange={(e) => setEmailTeste(e.target.value)}
            />
            <button
              className={styles.btnTable}
              style={{ fontSize: 11.5, flexShrink: 0 }}
              onClick={() => testeMutation.mutate()}
              disabled={testeMutation.isPending || !emailTeste.includes('@')}
            >
              {testeMutation.isPending ? 'Enviando...' : 'Enviar teste'}
            </button>
          </div>
          {testeResultado && !testeMutation.isPending && <p style={{ fontSize: 11.5, color: '#15803d', marginTop: 4 }}>{testeResultado}</p>}
          {testeMutation.isError && <p style={{ fontSize: 11.5, color: '#b91c1c', marginTop: 4 }}>{erroApi(testeMutation.error)}</p>}
        </div>

        <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid #e5e7eb' }}>
          {informativo.drive_pdf_link ? (
            <a href={informativo.drive_pdf_link} target="_blank" rel="noreferrer" style={{ fontSize: 12.5 }}>
              📄 Baixar PDF (pra enviar em grupos)
            </a>
          ) : (
            <span style={{ fontSize: 12.5, color: '#9ca3af' }}>PDF indisponível</span>
          )}
        </div>
      </div>

      <div style={{ flex: '2 1 420px', minWidth: 320 }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>WhatsApp (contatos da Expansão)</div>
        <textarea
          className={styles.input}
          style={{ fontSize: 12, marginBottom: 8, fontFamily: 'inherit' }}
          rows={5}
          value={textoWhatsapp}
          onChange={(e) => salvarTexto(e.target.value)}
        />
        <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
          <input
            className={styles.input}
            style={{ fontSize: 12.5, padding: '5px 8px' }}
            placeholder="Testar: 5511999999999 (DDI+DDD)"
            value={telefoneTeste}
            onChange={(e) => setTelefoneTeste(e.target.value)}
          />
          <a
            className={styles.btnTable}
            style={{ fontSize: 11.5, flexShrink: 0, textDecoration: 'none', opacity: telefoneTeste.replace(/\D/g, '').length < 10 ? 0.5 : 1, pointerEvents: telefoneTeste.replace(/\D/g, '').length < 10 ? 'none' : 'auto' }}
            target="_blank"
            rel="noreferrer"
            href={waLink(telefoneTeste)}
          >
            Testar
          </a>
        </div>

        {contatosWhatsapp.length === 0 ? (
          <p style={{ fontSize: 12.5, color: '#9ca3af' }}>Nenhum contato com WhatsApp cadastrado.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 220, overflowY: 'auto' }}>
            {contatosWhatsapp.map((c) => {
              const enviado = enviadosWhatsapp.has(c.id)
              const nomeCompleto = [c.primeiro_nome, c.sobrenome].filter(Boolean).join(' ')
              return (
                <a
                  key={c.id}
                  target="_blank"
                  rel="noreferrer"
                  href={waLink(c.whatsapp || '')}
                  onClick={() => toggleEnviado(c.id)}
                  title={enviado ? 'Marcado como enviado — clique de novo pra desmarcar' : 'Abre o WhatsApp e marca como enviado'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', fontSize: 13,
                    padding: '6px 10px', borderRadius: 6, border: '1px solid #e5e7eb',
                    background: enviado ? '#15803d' : '#fff', color: enviado ? '#fff' : '#1d1e20',
                  }}
                >
                  <span>{enviado ? '✅' : '💬'}</span>
                  <span>{nomeCompleto}</span>
                </a>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function DetalheInformativo({ informativo, onFechar }: { informativo: Informativo; onFechar: () => void }) {
  const qc = useQueryClient()
  const [preview, setPreview] = useState<string | null>(null)
  const [previewCarregando, setPreviewCarregando] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)
  const [instrucoes, setInstrucoes] = useState(informativo.instrucoes_ia ?? '')
  const [instrucoesReescrever, setInstrucoesReescrever] = useState('')
  const [citacoes, setCitacoes] = useState<Citacao[]>(informativo.citacoes_validadas ?? [])
  const [citacoesCarregadas, setCitacoesCarregadas] = useState(informativo.citacoes_validadas.length > 0 || Boolean(informativo.rascunho_gerado_em))

  const invalidar = () => qc.invalidateQueries({ queryKey: ['informativos'] })

  const instrucoesMutation = useMutation({
    mutationFn: (texto: string) => informativosApi.atualizar(informativo.id, { instrucoes_ia: texto || null }),
    onSuccess: invalidar,
  })
  const autorizarMutation = useMutation({
    mutationFn: (autorizado: boolean) => informativosApi.atualizar(informativo.id, { autorizado }),
    onSuccess: invalidar,
  })
  const validarMutation = useMutation({
    mutationFn: () => informativosApi.validarCitacoes(informativo.id),
    onSuccess: (res) => { invalidar(); setCitacoes(res.citacoes); setCitacoesCarregadas(true) },
  })
  const rascunhoIAMutation = useMutation({
    // Checagem de citações dispara À PARTE (chamada própria) logo depois de
    // gerar — nunca dentro da mesma requisição, senão o front toma timeout
    // esperando o texto (que já ficou pronto e salvo) porque a checagem com
    // busca na web pode passar de 1-2 minutos.
    mutationFn: () => informativosApi.gerarRascunhoIA(informativo.id),
    onSuccess: () => { invalidar(); validarMutation.mutate() },
  })
  const [reescritoEm, setReescritoEm] = useState<string | null>(null)
  const reescreverMutation = useMutation({
    mutationFn: () => informativosApi.reescreverIA(informativo.id, instrucoesReescrever),
    onSuccess: () => {
      invalidar()
      setReescritoEm(new Date().toISOString())
      validarMutation.mutate()
    },
  })
  const sincronizarMutation = useMutation({
    mutationFn: () => informativosApi.sincronizarDoc(informativo.id),
    onSuccess: () => { invalidar(); validarMutation.mutate() },
  })
  const publicarMutation = useMutation({
    mutationFn: () => informativosApi.publicar(informativo.id),
    onSuccess: (res) => {
      invalidar()
      setAviso(res.aviso)
    },
  })
  const uploadMutation = useMutation({
    mutationFn: (file: File) => informativosApi.uploadArquivo(informativo.id, file),
    onSuccess: invalidar,
  })
  const excluirMutation = useMutation({
    mutationFn: () => informativosApi.excluir(informativo.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['informativos'] })
      onFechar()
    },
  })

  const abrirPreview = async () => {
    setPreviewCarregando(true)
    try {
      const html = await informativosApi.previewHtml(informativo.id)
      setPreview(html)
    } finally {
      setPreviewCarregando(false)
    }
  }

  const handleExcluir = () => {
    if (window.confirm(`Excluir o informativo "${informativo.titulo}"? Isso não apaga o Doc nem os arquivos no Drive.`)) {
      excluirMutation.mutate()
    }
  }

  const jaGerado = Boolean(informativo.rascunho_gerado_em)
  const jaPublicado = Boolean(informativo.publicado_em)
  // Há rascunho novo (gerado pela IA) depois da última publicação — vale republicar.
  const rascunhoMaisNovo =
    jaPublicado && jaGerado &&
    new Date(informativo.rascunho_gerado_em as string) > new Date(informativo.publicado_em as string)

  return (
    <Modal onClose={onFechar} title={`${informativo.numero ? `Nº ${informativo.numero} — ` : ''}${informativo.titulo}`} width={640}>
      <div className={styles.form}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
          <StatusBadge status={informativo.status} />
          <span style={{ fontSize: 13, color: '#6b7280' }}>
            {fmtMes(informativo.mes_referencia)} · 1º draft até {fmtData(informativo.data_prazo_draft)} · final até {fmtData(informativo.data_prazo_final)}
          </span>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, marginLeft: 'auto', fontSize: 12.5, color: informativo.autorizado ? '#15803d' : '#6b7280', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={informativo.autorizado}
              onChange={(e) => autorizarMutation.mutate(e.target.checked)}
            />
            {informativo.autorizado ? `Autorizado em ${fmtDataHora(informativo.autorizado_em)}` : 'Autorizado'}
          </label>
        </div>
        <p style={{ fontSize: 11.5, color: '#9ca3af', margin: '0 0 4px' }}>
          "Autorizado" é só um sinalizador pros lembretes por e-mail — não trava geração de PDF nem publicação.
        </p>

        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 13, padding: '10px 0', borderBottom: '1px solid #f1f1f1' }}>
          {informativo.google_doc_link && (
            <a href={informativo.google_doc_link} target="_blank" rel="noreferrer">📄 Abrir Google Doc</a>
          )}
          {informativo.drive_folder_link && (
            <a href={informativo.drive_folder_link} target="_blank" rel="noreferrer">📁 Pasta no Drive</a>
          )}
          {informativo.drive_pdf_link && (
            <a href={informativo.drive_pdf_link} target="_blank" rel="noreferrer">✅ Ver PDF publicado</a>
          )}
        </div>

        <Passo
          numero={1}
          titulo="Material de apoio (opcional)"
          descricao="Imagem, PDF ou vídeo com o conteúdo base do informativo deste mês. Pode selecionar vários."
        >
          <input
            type="file"
            multiple
            onChange={(e) => {
              const files = Array.from(e.target.files ?? [])
              files.forEach((file) => uploadMutation.mutate(file))
              e.target.value = ''
            }}
          />
          {informativo.arquivos_referencia.length > 0 && (
            <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
              {informativo.arquivos_referencia.map((a, idx) => (
                <li key={idx} style={{ fontSize: 13 }}>
                  <a href={a.link_drive} target="_blank" rel="noreferrer">{a.nome}</a>
                </li>
              ))}
            </ul>
          )}
          <label className={styles.formLabel} style={{ display: 'block', marginTop: 10 }}>
            Direcionamento pra IA (opcional)
          </label>
          <textarea
            className={styles.input}
            rows={2}
            placeholder='Ex.: "foque no impacto pra holdings imobiliárias" ou "cite o julgado tal"'
            value={instrucoes}
            onChange={(e) => setInstrucoes(e.target.value)}
            onBlur={() => {
              if (instrucoes !== (informativo.instrucoes_ia ?? '')) instrucoesMutation.mutate(instrucoes)
            }}
          />
        </Passo>

        <Passo
          numero={2}
          titulo="Escreva o texto"
          descricao="Gere (ou regere) um rascunho com IA a partir do material e do direcionamento acima, ou abra o Google Doc (link no topo) e escreva você mesmo."
        >
          <button className={styles.btnSmall} onClick={() => rascunhoIAMutation.mutate()} disabled={rascunhoIAMutation.isPending}>
            {rascunhoIAMutation.isPending ? 'Gerando rascunho...' : jaGerado ? 'Regerar rascunho com IA' : 'Gerar rascunho com IA'}
          </button>
          {jaGerado && !rascunhoIAMutation.isPending && (
            <span style={{ marginLeft: 8, fontSize: 12.5, color: '#15803d' }}>
              ✅ Gerado em {fmtDataHora(informativo.rascunho_gerado_em)}
            </span>
          )}
          {rascunhoIAMutation.isError && (
            <p style={{ color: '#b91c1c', fontSize: 12.5 }}>{erroApi(rascunhoIAMutation.error)}</p>
          )}
        </Passo>

        <Passo
          numero={3}
          titulo="Checagem de citações de lei/julgado"
          descricao="Automática — dispara sozinha logo depois de gerar/regerar/sincronizar (pode levar mais de um minuto, feita à parte pra não travar a geração). Use os botões abaixo pra rechecar."
        >
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className={styles.btnSmall} onClick={() => sincronizarMutation.mutate()} disabled={sincronizarMutation.isPending}>
              {sincronizarMutation.isPending ? 'Sincronizando...' : 'Sincronizar do Doc e checar'}
            </button>
            <button
              className={styles.btnSmall}
              onClick={() => validarMutation.mutate()}
              disabled={validarMutation.isPending || !informativo.conteudo_texto}
              title={!informativo.conteudo_texto ? 'Gere ou sincronize o texto primeiro' : undefined}
            >
              {validarMutation.isPending ? 'Checando...' : 'Rechecar citações'}
            </button>
          </div>
          {(sincronizarMutation.isPending || validarMutation.isPending) && (
            <p style={{ fontSize: 12.5, color: '#6b7280', marginTop: 6 }}>Checando... pode levar mais de um minuto (busca na web por citação).</p>
          )}
          {citacoesCarregadas ? <ResultadoCitacoes citacoes={citacoes} /> : (
            <p style={{ fontSize: 13, color: '#9ca3af', marginTop: 8 }}>Ainda não checado nesta sessão.</p>
          )}
        </Passo>

        <Passo numero={4} titulo="Pré-visualizar" descricao="Mostra o Doc exatamente como está agora.">
          <button className={styles.btnSmall} onClick={abrirPreview} disabled={previewCarregando}>
            {previewCarregando ? 'Carregando...' : 'Pré-visualizar'}
          </button>
          {preview && (
            <iframe
              title="Pré-visualização"
              srcDoc={preview}
              style={{ width: '100%', height: 500, border: '1px solid #e5e7eb', borderRadius: 8, marginTop: 10 }}
            />
          )}
        </Passo>

        <Passo
          numero={5}
          titulo="Reescrever considerando os apontamentos (opcional)"
          descricao="A IA reescreve o corpo corrigindo o que a checagem apontou. Dá pra somar um direcionamento extra."
        >
          <textarea
            className={styles.input}
            rows={2}
            placeholder='Ex.: "corrija a citação do art. 1.055 e cite o dispositivo certo"'
            value={instrucoesReescrever}
            onChange={(e) => setInstrucoesReescrever(e.target.value)}
          />
          <button
            className={styles.btnSmall}
            style={{ marginTop: 6 }}
            onClick={() => reescreverMutation.mutate()}
            disabled={reescreverMutation.isPending || !informativo.conteudo_texto}
            title={!informativo.conteudo_texto ? 'Gere ou sincronize o texto primeiro' : undefined}
          >
            {reescreverMutation.isPending ? 'Reescrevendo...' : 'Reescrever com IA'}
          </button>
          {reescritoEm && !reescreverMutation.isPending && (
            <span style={{ marginLeft: 8, fontSize: 12.5, color: '#15803d' }}>
              ✅ Reescrito em {fmtDataHora(reescritoEm)}
            </span>
          )}
          {reescreverMutation.isError && (
            <p style={{ color: '#b91c1c', fontSize: 12.5 }}>{erroApi(reescreverMutation.error)}</p>
          )}
        </Passo>

        <Passo numero={6} titulo="Publicar" descricao="Gera o PDF final a partir do Doc (com timbrado) e disponibiliza no site.">
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: informativo.autorizado ? '#15803d' : '#6b7280', cursor: 'pointer', marginBottom: 8 }}>
            <input
              type="checkbox"
              checked={informativo.autorizado}
              onChange={(e) => autorizarMutation.mutate(e.target.checked)}
            />
            {informativo.autorizado ? `Autorizado em ${fmtDataHora(informativo.autorizado_em)}` : 'Marcar como Autorizado antes de publicar (opcional)'}
          </label>
          <button className={styles.btnPrimary} onClick={() => publicarMutation.mutate()} disabled={publicarMutation.isPending}>
            {publicarMutation.isPending ? 'Publicando...' : jaPublicado ? 'Republicar' : 'Publicar'}
          </button>
          {jaPublicado && !publicarMutation.isPending && (
            <span style={{ marginLeft: 8, fontSize: 12.5, color: '#15803d' }}>
              ✅ Publicado em {fmtDataHora(informativo.publicado_em)}
            </span>
          )}
          {rascunhoMaisNovo && (
            <p style={{ fontSize: 12.5, color: '#b45309', marginTop: 4 }}>
              O rascunho foi regenerado depois da última publicação — republique pra atualizar o PDF.
            </p>
          )}
          {aviso && <p style={{ color: '#b45309', fontSize: 13 }}>{aviso}</p>}
          {publicarMutation.isError && (
            <p style={{ color: '#b91c1c', fontSize: 12.5 }}>{erroApi(publicarMutation.error)}</p>
          )}
          {(informativo.google_doc_link || informativo.drive_folder_link || informativo.drive_pdf_link) && (
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12.5, marginTop: 10 }}>
              {informativo.google_doc_link && (
                <a href={informativo.google_doc_link} target="_blank" rel="noreferrer">📄 Abrir Google Doc</a>
              )}
              {informativo.drive_folder_link && (
                <a href={informativo.drive_folder_link} target="_blank" rel="noreferrer">📁 Pasta no Drive</a>
              )}
              {informativo.drive_pdf_link && (
                <a href={informativo.drive_pdf_link} target="_blank" rel="noreferrer">✅ Ver PDF publicado</a>
              )}
            </div>
          )}
        </Passo>

        <div style={{ paddingTop: 14, textAlign: 'right' }}>
          <button className={styles.btnDanger} onClick={handleExcluir} disabled={excluirMutation.isPending}>
            {excluirMutation.isPending ? 'Excluindo...' : 'Excluir informativo'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
