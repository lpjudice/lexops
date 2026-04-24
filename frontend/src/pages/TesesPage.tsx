import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tesesApi } from '../api/teses'
import type { ModeloIA, Tese, TeseCreate } from '../api/teses'
import { processosApi } from '../api/processos'
import { clientesApi } from '../api/clientes'
import { prazosApi } from '../api/prazos'
import ProcessoChat from '../components/ProcessoChat'
import styles from './Page.module.css'
import cs from './TesesPage.module.css'

const MODELOS: { key: ModeloIA; label: string }[] = [
  { key: 'claude', label: 'Claude' },
  { key: 'gpt', label: 'GPT-4o' },
  { key: 'gemini', label: 'Gemini' },
]

const EMPTY: TeseCreate = { titulo: '', texto_input: '', modelo_ativo: 'claude' }

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('pt-BR')
}

function resposta(tese: Tese, modelo: ModeloIA): string | undefined {
  if (modelo === 'claude') return tese.resposta_claude
  if (modelo === 'gpt') return tese.resposta_gpt
  return tese.resposta_gemini
}

export default function TesesPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<TeseCreate>(EMPTY)
  const [expandido, setExpandido] = useState<string | null>(null)
  const [modeloAtivo, setModeloAtivo] = useState<Record<string, ModeloIA>>({})

  const { data: teses = [], isLoading } = useQuery({
    queryKey: ['teses'],
    queryFn: () => tesesApi.listar(),
  })
  const { data: processos = [] } = useQuery({
    queryKey: ['processos'],
    queryFn: () => processosApi.listar(),
  })
  const { data: clientes = [] } = useQuery({
    queryKey: ['clientes'],
    queryFn: () => clientesApi.listar(),
  })
  const { data: prazos = [] } = useQuery({
    queryKey: ['prazos'],
    queryFn: () => prazosApi.listar(),
  })

  const criar = useMutation({
    mutationFn: tesesApi.criar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teses'] })
      setShowForm(false)
      setForm(EMPTY)
    },
  })

  const deletar = useMutation({
    mutationFn: tesesApi.deletar,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teses'] }),
  })

  const gerar = useMutation({
    mutationFn: ({ id, modelo }: { id: string; modelo: ModeloIA }) =>
      tesesApi.gerar(id, modelo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teses'] }),
  })

  const getModelo = (id: string, fallback: ModeloIA) => modeloAtivo[id] ?? fallback

  const getProcesso = (id?: string) => processos.find((p) => p.id === id)
  const getCliente = (id?: string) => clientes.find((c) => c.id === id)
  const getPrazosAtivos = (processoId?: string) =>
    processoId ? prazos.filter((p) => p.processo_id === processoId && p.status === 'pendente') : []

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Teses Jurídicas</h1>
        <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Nova Tese'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); criar.mutate(form) }}
          className={styles.form}
        >
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Título *</label>
            <input
              className={styles.input}
              value={form.titulo}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Texto / Pergunta *</label>
            <textarea
              className={styles.input}
              rows={6}
              placeholder="Descreva a situação, a questão jurídica ou o texto a ser analisado..."
              value={form.texto_input}
              onChange={(e) => setForm({ ...form, texto_input: e.target.value })}
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Processo (opcional)</label>
            <select
              className={styles.input}
              value={form.processo_id ?? ''}
              onChange={(e) => setForm({ ...form, processo_id: e.target.value || undefined })}
            >
              <option value="">Nenhum</option>
              {processos.map((p) => (
                <option key={p.id} value={p.id}>{p.numero_cnj}</option>
              ))}
            </select>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Modelo inicial</label>
            <div className={cs.modeloToggle}>
              {MODELOS.map((m) => (
                <button
                  key={m.key}
                  type="button"
                  className={`${cs.btnModelo} ${form.modelo_ativo === m.key ? cs.btnModeloActive : ''}`}
                  onClick={() => setForm({ ...form, modelo_ativo: m.key })}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending}>
            {criar.isPending ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : teses.length === 0 ? (
        <p className={styles.empty}>Nenhuma tese cadastrada.</p>
      ) : (
        <div className={cs.lista}>
          {teses.map((t) => {
            const modelo = getModelo(t.id, t.modelo_ativo)
            const resp = resposta(t, modelo)
            const isGerando = gerar.isPending && gerar.variables?.id === t.id && gerar.variables?.modelo === modelo
            const processo = getProcesso(t.processo_id)
            const cliente = getCliente(processo?.cliente_id ?? t.cliente_id)
            const prazosAtivos = getPrazosAtivos(t.processo_id)
            return (
              <div key={t.id} className={cs.card}>
                <div className={cs.cardTop}>
                  <div style={{ flex: 1 }}>
                    <div className={cs.cardTitulo}>{t.titulo}</div>
                    <div className={cs.cardChips}>
                      {cliente && <span className={cs.chipCliente}>{cliente.nome}</span>}
                      {processo?.materia && <span className={cs.chipMateria}>{processo.materia}</span>}
                      {processo && (
                        <span className={`${cs.chipStatus} ${cs[`status_${processo.status}`]}`}>
                          {processo.status}
                        </span>
                      )}
                      {prazosAtivos.length > 0 && (
                        <span className={cs.chipPrazo}>
                          ⏰ {prazosAtivos.length} prazo{prazosAtivos.length > 1 ? 's' : ''} ativo{prazosAtivos.length > 1 ? 's' : ''} — vence {prazosAtivos[0].data_limite}
                        </span>
                      )}
                    </div>
                    <div className={cs.cardMeta}>{formatDate(t.created_at)}</div>
                  </div>
                  <div className={cs.cardActions}>
                    <button
                      className={cs.btnExpand}
                      onClick={() => setExpandido(expandido === t.id ? null : t.id)}
                    >
                      {expandido === t.id ? '▲' : '▼'}
                    </button>
                    <button
                      className={styles.btnDanger}
                      onClick={() => { if (confirm('Remover tese?')) deletar.mutate(t.id) }}
                    >
                      ×
                    </button>
                  </div>
                </div>

                {expandido === t.id && (
                  <div className={cs.cardBody}>
                    {/* Input */}
                    <div>
                      <div className={cs.sectionTitle}>Texto / Pergunta</div>
                      <div className={cs.textoInput}>{t.texto_input}</div>
                    </div>

                    {/* Chat Gemini com processo */}
                    {t.processo_id && (
                      <div>
                        <div className={cs.sectionTitle}>Chat com Processo — Gemini</div>
                        <ProcessoChat
                          processoId={t.processo_id}
                          clienteId={processos.find((p) => p.id === t.processo_id)?.cliente_id ?? ''}
                          processoNome={processos.find((p) => p.id === t.processo_id)?.numero_cnj}
                        />
                      </div>
                    )}

                    {/* Toggle + gerar */}
                    <div>
                      <div className={cs.sectionTitle}>Resposta da IA</div>
                      <div className={cs.modeloRow}>
                        {MODELOS.map((m) => (
                          <button
                            key={m.key}
                            className={`${cs.btnModelo} ${modelo === m.key ? cs.btnModeloActive : ''}`}
                            onClick={() => setModeloAtivo({ ...modeloAtivo, [t.id]: m.key })}
                          >
                            {m.label}
                          </button>
                        ))}
                        <button
                          className={cs.btnGerarModelo}
                          disabled={isGerando}
                          onClick={() => gerar.mutate({ id: t.id, modelo })}
                        >
                          {isGerando ? 'Gerando...' : `↻ Gerar com ${MODELOS.find(m => m.key === modelo)?.label}`}
                        </button>
                      </div>

                      <div style={{ marginTop: 12 }}>
                        {resp ? (
                          <div className={`${cs.respostaBox} ${resp.startsWith('❌') ? cs.respostaErro : ''}`}>
                            {resp}
                          </div>
                        ) : (
                          <div className={`${cs.respostaBox} ${cs.respostaVazia}`}>
                            Nenhuma resposta gerada com {MODELOS.find(m => m.key === modelo)?.label} ainda.
                            Clique em "Gerar" para consultar.
                          </div>
                        )}
                      </div>
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
