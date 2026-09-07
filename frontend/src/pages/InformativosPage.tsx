import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { erroApi, informativosApi } from '../api/informativos'
import type { Informativo, StatusInformativo } from '../api/informativos'
import { instagramApi } from '../api/instagram'
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
  const [selecionadoId, setSelecionadoId] = useState<string | null>(null)
  const selecionado = informativos.find((i) => i.id === selecionadoId) ?? null

  const criarMutation = useMutation({
    mutationFn: informativosApi.criar,
    onSuccess: (informativo) => {
      qc.invalidateQueries({ queryKey: ['informativos'] })
      setModalCriar(false)
      setSelecionadoId(informativo.id)
    },
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Informativos</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {template?.template_doc_link && (
            <a href={template.template_doc_link} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
              Editar modelo padrão
            </a>
          )}
          <button className={styles.btnPrimary} onClick={() => setModalCriar(true)}>
            + Novo informativo
          </button>
        </div>
      </div>

      {isLoading ? (
        <p>Carregando...</p>
      ) : informativos.length === 0 ? (
        <p className={styles.empty}>Nenhum informativo criado ainda.</p>
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
              </tr>
            </thead>
            <tbody>
              {informativos.map((i) => (
                <tr key={i.id} onClick={() => setSelecionadoId(i.id)} style={{ cursor: 'pointer' }}>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalCriar && (
        <ModalCriar
          responsavelPadrao={padrao ?? null}
          onFechar={() => setModalCriar(false)}
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

function ModalCriar({
  responsavelPadrao,
  onFechar,
  onCriar,
  salvando,
}: {
  responsavelPadrao: { id: string; nome: string; email: string | null } | null
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
  const [titulo, setTitulo] = useState('')
  const [temaSugestaoId, setTemaSugestaoId] = useState('')
  const [responsavel, setResponsavel] = useState<ResponsavelValue>({
    id: responsavelPadrao?.id ?? null,
    nome: responsavelPadrao?.nome ?? '',
    email: responsavelPadrao?.email ?? '',
  })

  const { data: sugestoesInstagram = [] } = useQuery({
    queryKey: ['instagram', 'sugestoes-tema'],
    queryFn: () => instagramApi.listar(),
    staleTime: 30_000,
  })

  const sugestaoSelecionada = sugestoesInstagram.find((s) => s.id === temaSugestaoId)

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
            <select
              className={styles.input}
              value={temaSugestaoId}
              onChange={(e) => {
                setTemaSugestaoId(e.target.value)
                const s = sugestoesInstagram.find((x) => x.id === e.target.value)
                if (s && !titulo.trim()) setTitulo(s.titulo)
              }}
            >
              <option value="">— Nenhum, título livre —</option>
              {sugestoesInstagram.map((s) => (
                <option key={s.id} value={s.id}>{s.titulo}</option>
              ))}
            </select>
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

function fmtDataHora(iso?: string | null) {
  if (!iso) return null
  return new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function DetalheInformativo({ informativo, onFechar }: { informativo: Informativo; onFechar: () => void }) {
  const qc = useQueryClient()
  const [preview, setPreview] = useState<string | null>(null)
  const [previewCarregando, setPreviewCarregando] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)
  const [instrucoes, setInstrucoes] = useState(informativo.instrucoes_ia ?? '')

  const invalidar = () => qc.invalidateQueries({ queryKey: ['informativos'] })

  const instrucoesMutation = useMutation({
    mutationFn: (texto: string) => informativosApi.atualizar(informativo.id, { instrucoes_ia: texto || null }),
    onSuccess: invalidar,
  })
  const rascunhoIAMutation = useMutation({
    mutationFn: () => informativosApi.gerarRascunhoIA(informativo.id),
    onSuccess: invalidar,
  })
  const sincronizarMutation = useMutation({
    mutationFn: () => informativosApi.sincronizarDoc(informativo.id),
    onSuccess: invalidar,
  })
  const validarMutation = useMutation({
    mutationFn: () => informativosApi.validarCitacoes(informativo.id),
    onSuccess: invalidar,
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
        </div>

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

        <Passo numero={3} titulo="Pré-visualizar" descricao="Mostra o Doc exatamente como está agora — confira o texto antes de decidir se precisa checar citações.">
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
          numero={4}
          titulo="Confira as citações de lei/julgado (opcional)"
          descricao="Só se o texto citar lei ou jurisprudência. Primeiro traz o texto do Doc pro sistema, depois confere cada citação."
        >
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className={styles.btnSmall} onClick={() => sincronizarMutation.mutate()} disabled={sincronizarMutation.isPending}>
              {sincronizarMutation.isPending ? 'Trazendo do Doc...' : 'Trazer texto do Doc'}
            </button>
            <button
              className={styles.btnSmall}
              onClick={() => validarMutation.mutate()}
              disabled={validarMutation.isPending || !informativo.conteudo_texto}
              title={!informativo.conteudo_texto ? 'Traga o texto do Doc primeiro' : undefined}
            >
              {validarMutation.isPending ? 'Validando...' : 'Validar citações'}
            </button>
          </div>
          {validarMutation.data && (
            <ul style={{ marginTop: 8, paddingLeft: 18 }}>
              {validarMutation.data.citacoes.length === 0 && <li style={{ fontSize: 13 }}>Nenhuma citação encontrada no texto.</li>}
              {validarMutation.data.citacoes.map((c, idx) => (
                <li key={idx} style={{ fontSize: 13 }}>{JSON.stringify(c)}</li>
              ))}
            </ul>
          )}
        </Passo>

        <Passo numero={5} titulo="Publicar" descricao="Gera o PDF final a partir do Doc (com timbrado) e disponibiliza no site.">
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
