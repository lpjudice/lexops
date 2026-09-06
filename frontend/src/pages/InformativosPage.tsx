import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { informativosApi } from '../api/informativos'
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

const STATUS_COR: Record<StatusInformativo, string> = {
  rascunho: '#9ca3af',
  primeiro_draft: '#f59e0b',
  revisado: '#3b82f6',
  publicado: '#16a34a',
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

  const [modalCriar, setModalCriar] = useState(false)
  const [selecionado, setSelecionado] = useState<Informativo | null>(null)

  const criarMutation = useMutation({
    mutationFn: informativosApi.criar,
    onSuccess: (informativo) => {
      qc.invalidateQueries({ queryKey: ['informativos'] })
      setModalCriar(false)
      setSelecionado(informativo)
    },
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Informativos</h1>
        <button className={styles.btnPrimary} onClick={() => setModalCriar(true)}>
          + Novo informativo
        </button>
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
                <tr key={i.id} onClick={() => setSelecionado(i)} style={{ cursor: 'pointer' }}>
                  <td style={{ textTransform: 'capitalize' }}>{fmtMes(i.mes_referencia)}</td>
                  <td>{i.titulo}</td>
                  <td>
                    <span className={styles.badge} style={{ background: STATUS_COR[i.status] }}>
                      {STATUS_LABEL[i.status]}
                    </span>
                  </td>
                  <td>{fmtData(i.data_prazo_draft)}</td>
                  <td>{fmtData(i.data_prazo_final)}</td>
                  <td>{i.paginas_estimadas ?? '—'}</td>
                  <td>
                    <button className={styles.btnTable} onClick={(e) => { e.stopPropagation(); setSelecionado(i) }}>
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
          onFechar={() => setSelecionado(null)}
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
          {salvando ? 'Criando...' : 'Criar (Google Doc + pasta no Drive)'}
        </button>
      </div>
    </Modal>
  )
}

function DetalheInformativo({ informativo, onFechar }: { informativo: Informativo; onFechar: () => void }) {
  const qc = useQueryClient()
  const [preview, setPreview] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  const invalidar = () => qc.invalidateQueries({ queryKey: ['informativos'] })

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

  const abrirPreview = async () => {
    const html = await informativosApi.previewHtml(informativo.id)
    setPreview(html)
  }

  return (
    <Modal onClose={onFechar} title={informativo.titulo}>
      <div className={styles.form}>
        <p><strong>Status:</strong> {STATUS_LABEL[informativo.status]}</p>
        <p><strong>Mês:</strong> {fmtMes(informativo.mes_referencia)}</p>
        <p>
          <strong>Prazos internos:</strong> 1º draft até {fmtData(informativo.data_prazo_draft)} ·
          {' '}versão final até {fmtData(informativo.data_prazo_final)}
        </p>

        {informativo.google_doc_link && (
          <p><a href={informativo.google_doc_link} target="_blank" rel="noreferrer">Abrir Google Doc →</a></p>
        )}
        {informativo.drive_folder_link && (
          <p><a href={informativo.drive_folder_link} target="_blank" rel="noreferrer">Abrir pasta no Drive →</a></p>
        )}
        {informativo.drive_pdf_link && (
          <p><a href={informativo.drive_pdf_link} target="_blank" rel="noreferrer">Ver PDF publicado →</a></p>
        )}

        <div className={styles.fieldGroup}>
          <label className={styles.formLabel}>Material de apoio (imagem, vídeo, PDF) — pode selecionar vários</label>
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
            <ul>
              {informativo.arquivos_referencia.map((a, idx) => (
                <li key={idx}>
                  <a href={a.link_drive} target="_blank" rel="noreferrer">{a.nome}</a>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className={styles.btnSmall} onClick={() => rascunhoIAMutation.mutate()} disabled={rascunhoIAMutation.isPending}>
            {rascunhoIAMutation.isPending ? 'Gerando rascunho...' : 'Gerar rascunho com IA'}
          </button>
          <button className={styles.btnSmall} onClick={() => sincronizarMutation.mutate()} disabled={sincronizarMutation.isPending}>
            {sincronizarMutation.isPending ? 'Sincronizando...' : 'Sincronizar do Doc'}
          </button>
          <button className={styles.btnSmall} onClick={() => validarMutation.mutate()} disabled={validarMutation.isPending}>
            {validarMutation.isPending ? 'Validando...' : 'Validar citações'}
          </button>
          <button className={styles.btnSmall} onClick={abrirPreview}>
            Pré-visualizar
          </button>
          <button className={styles.btnPrimary} onClick={() => publicarMutation.mutate()} disabled={publicarMutation.isPending}>
            {publicarMutation.isPending ? 'Publicando...' : 'Gerar PDF e publicar'}
          </button>
        </div>

        {aviso && <p style={{ color: '#b45309' }}>{aviso}</p>}

        {validarMutation.data && (
          <div>
            <strong>Citações verificadas:</strong>
            <ul>
              {validarMutation.data.citacoes.map((c, idx) => (
                <li key={idx}>{JSON.stringify(c)}</li>
              ))}
            </ul>
          </div>
        )}

        {preview && (
          <iframe
            title="Pré-visualização"
            srcDoc={preview}
            style={{ width: '100%', height: 600, border: '1px solid #e5e7eb', borderRadius: 8, marginTop: 12 }}
          />
        )}
      </div>
    </Modal>
  )
}
