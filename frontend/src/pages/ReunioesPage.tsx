import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Video, RefreshCw, Plus, Trash2 } from 'lucide-react'
import { reunioesApi } from '../api/reunioes'
import type { Reuniao, ReuniaoCreate } from '../api/reunioes'
import RevisaoReuniaoModal from '../components/RevisaoReuniaoModal'
import styles from './Page.module.css'

const STATUS_LABEL: Record<string, string> = {
  pendente: 'Pendente',
  em_revisao: 'Em revisão',
  processada: 'Processada',
}

const STATUS_CSS: Record<string, string> = {
  pendente: styles.status_suspenso,
  em_revisao: styles.status_ativo,
  processada: styles.status_arquivado,
}

function formatDateTime(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

interface NovaReuniaoForm {
  titulo: string
  data_reuniao: string
  transcricao_texto: string
  google_meet_url: string
}

const EMPTY_FORM: NovaReuniaoForm = {
  titulo: '',
  data_reuniao: '',
  transcricao_texto: '',
  google_meet_url: '',
}

export default function ReunioesPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<NovaReuniaoForm>(EMPTY_FORM)
  const [revisando, setRevisando] = useState<Reuniao | null>(null)

  const { data: reunioes = [], isLoading } = useQuery({
    queryKey: ['reunioes'],
    queryFn: () => reunioesApi.listar(),
  })

  const syncMut = useMutation({
    mutationFn: reunioesApi.syncDrive,
    onSuccess: (novas) => {
      qc.invalidateQueries({ queryKey: ['reunioes'] })
      if (novas.length === 0) {
        alert('Nenhuma transcrição nova encontrada no Google Drive.')
      } else {
        alert(`${novas.length} nova(s) reunião(ões) importada(s) do Drive.`)
      }
    },
    onError: () => alert('Erro ao verificar o Google Drive.'),
  })

  const criarMut = useMutation({
    mutationFn: (data: ReuniaoCreate) => reunioesApi.criar(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reunioes'] })
      setShowForm(false)
      setForm(EMPTY_FORM)
    },
    onError: () => alert('Erro ao criar reunião.'),
  })

  const deletarMut = useMutation({
    mutationFn: (id: string) => reunioesApi.deletar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reunioes'] }),
    onError: () => alert('Erro ao excluir reunião.'),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.titulo.trim()) return
    criarMut.mutate({
      titulo: form.titulo.trim(),
      data_reuniao: form.data_reuniao || null,
      transcricao_texto: form.transcricao_texto || null,
      google_meet_url: form.google_meet_url || null,
      fonte: 'manual',
    })
  }

  function abrirRevisao(r: Reuniao) {
    setRevisando(r)
  }

  function fecharRevisao() {
    setRevisando(null)
    qc.invalidateQueries({ queryKey: ['reunioes'] })
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          <strong>Reuniões</strong> Google Meet
        </h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className={styles.btnPrimary}
            onClick={() => syncMut.mutate()}
            disabled={syncMut.isPending}
            style={{ background: '#0f766e' }}
          >
            <RefreshCw size={14} />
            {syncMut.isPending ? 'Verificando...' : 'Verificar Drive'}
          </button>
          <button
            className={styles.btnPrimary}
            onClick={() => setShowForm((v) => !v)}
          >
            <Plus size={14} />
            Nova Reunião
          </button>
        </div>
      </div>

      {showForm && (
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Título da Reunião *</label>
            <input
              className={styles.input}
              value={form.titulo}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
              placeholder="Ex: Reunião João Silva — Processo Trabalhista"
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Data / Hora</label>
            <input
              className={styles.input}
              type="datetime-local"
              value={form.data_reuniao}
              onChange={(e) => setForm({ ...form, data_reuniao: e.target.value })}
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Link do Meet</label>
            <input
              className={styles.input}
              value={form.google_meet_url}
              onChange={(e) => setForm({ ...form, google_meet_url: e.target.value })}
              placeholder="https://meet.google.com/..."
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Transcrição (cole aqui o texto)</label>
            <textarea
              className={styles.input}
              rows={6}
              value={form.transcricao_texto}
              onChange={(e) => setForm({ ...form, transcricao_texto: e.target.value })}
              placeholder="Cole aqui o texto da transcrição do Google Meet..."
              style={{ resize: 'vertical' }}
            />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className={styles.btnPrimary} type="submit" disabled={criarMut.isPending}>
              {criarMut.isPending ? 'Salvando...' : 'Criar Reunião'}
            </button>
            <button
              type="button"
              className={styles.btnTable}
              onClick={() => { setShowForm(false); setForm(EMPTY_FORM) }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      <div className={styles.tableCard}>
        {isLoading ? (
          <div className={styles.empty}>Carregando...</div>
        ) : reunioes.length === 0 ? (
          <div className={styles.empty}>
            <Video size={28} />
            Nenhuma reunião ainda. Importe do Drive ou cole uma transcrição.
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Reunião</th>
                <th>Cliente</th>
                <th>Data</th>
                <th>Origem</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {reunioes.map((r) => (
                <tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => abrirRevisao(r)}>
                  <td style={{ fontWeight: 600, maxWidth: 280 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Video size={14} style={{ color: '#0f766e', flexShrink: 0 }} />
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.titulo}
                      </span>
                    </div>
                  </td>
                  <td>{r.cliente_nome ?? <span style={{ color: '#aaa' }}>Não vinculado</span>}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatDateTime(r.data_reuniao)}</td>
                  <td>
                    <span className={styles.badge} style={{ background: r.fonte === 'drive_auto' ? '#e0f2fe' : '#f3f4f6', color: r.fonte === 'drive_auto' ? '#0369a1' : '#6b7280' }}>
                      {r.fonte === 'drive_auto' ? 'Drive' : 'Manual'}
                    </span>
                  </td>
                  <td>
                    <span className={`${styles.badge} ${STATUS_CSS[r.status] ?? ''}`}>
                      {STATUS_LABEL[r.status] ?? r.status}
                    </span>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button
                      className={styles.btnDanger}
                      onClick={() => {
                        if (confirm('Excluir esta reunião?')) deletarMut.mutate(r.id)
                      }}
                      style={{ padding: '4px 8px' }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {revisando && (
        <RevisaoReuniaoModal
          reuniao={revisando}
          onClose={fecharRevisao}
        />
      )}
    </div>
  )
}
