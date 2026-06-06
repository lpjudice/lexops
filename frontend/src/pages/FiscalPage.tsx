import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fiscalApi } from '../api/fiscal'
import type { NotaFiscalResumo, NotaFiscalOut, EmitirNFSeIn, StatusNF } from '../api/fiscal'
import styles from './Page.module.css'
import cs from './FiscalPage.module.css'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtValor(v: number) {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function fmtCompetencia(c: string) {
  const [ano, mes] = c.split('-')
  const meses = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
  return `${meses[parseInt(mes) - 1]}/${ano}`
}

function fmtData(d?: string) {
  if (!d) return '—'
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

function mesAtual() {
  return new Date().toISOString().slice(0, 7)
}

const STATUS_LABEL: Record<StatusNF, string> = {
  rascunho: 'Rascunho',
  emitida: 'Emitida',
  cancelada: 'Cancelada',
  erro: 'Erro',
}

const STATUS_CLASS: Record<StatusNF, string> = {
  emitida: cs.badgeEmitida,
  rascunho: cs.badgeRascunho,
  cancelada: cs.badgeCancelada,
  erro: cs.badgeErro,
}

// ─── Formulário de emissão ────────────────────────────────────────────────────

const EMPTY_FORM: EmitirNFSeIn = {
  competencia: mesAtual(),
  tomador_cpf_cnpj: '',
  tomador_nome: '',
  tomador_email: '',
  descricao_servico: '',
  cod_tributacao_nacional: '010900',
  valor_servicos: 0,
  retencao_ir: 0,
  retencao_inss: 0,
  retencao_csll: 0,
  retencao_cofins: 0,
  retencao_pis: 0,
  serie: '1',
}

function EmissaoModal({
  inicial,
  onClose,
  onSucesso,
}: {
  inicial?: Partial<EmitirNFSeIn>
  onClose: () => void
  onSucesso: (nf: NotaFiscalOut) => void
}) {
  const [form, setForm] = useState<EmitirNFSeIn>({ ...EMPTY_FORM, ...inicial })
  const [mostrarRetencoes, setMostrarRetencoes] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: fiscalApi.emitir,
    onSuccess: (nf) => {
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      onSucesso(nf)
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'object') {
        setErro(`[${detail.codigo ?? '?'}] ${detail.detalhe ?? detail.message}`)
      } else {
        setErro(String(detail ?? err?.message ?? 'Erro desconhecido'))
      }
    },
  })

  function set<K extends keyof EmitirNFSeIn>(k: K, v: EmitirNFSeIn[K]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  const temPrefill = !!inicial?.tomador_nome

  return (
    <div className={cs.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={cs.modal}>
        <button className={cs.closeBtn} onClick={onClose}>✕</button>
        <div className={cs.modalTitle}>🧾 Emitir NFS-e</div>

        {temPrefill && (
          <div className={cs.prefillBanner}>
            ✅ Dados pré-preenchidos a partir do honorário. Revise e confirme.
          </div>
        )}

        <div className={cs.formGrid}>
          {/* Competência */}
          <div>
            <label className={cs.formLabel}>Competência *</label>
            <input
              type="month"
              className={cs.input}
              value={form.competencia}
              onChange={(e) => set('competencia', e.target.value)}
            />
          </div>

          {/* Série */}
          <div>
            <label className={cs.formLabel}>Série</label>
            <input
              className={cs.input}
              value={form.serie}
              onChange={(e) => set('serie', e.target.value)}
            />
          </div>

          {/* Tomador CPF/CNPJ */}
          <div>
            <label className={cs.formLabel}>CPF / CNPJ do Tomador *</label>
            <input
              className={cs.input}
              placeholder="Apenas dígitos"
              value={form.tomador_cpf_cnpj}
              onChange={(e) => set('tomador_cpf_cnpj', e.target.value.replace(/\D/g, ''))}
              maxLength={14}
            />
          </div>

          {/* Tomador nome */}
          <div>
            <label className={cs.formLabel}>Nome / Razão Social *</label>
            <input
              className={cs.input}
              value={form.tomador_nome}
              onChange={(e) => set('tomador_nome', e.target.value)}
            />
          </div>

          {/* Email tomador */}
          <div>
            <label className={cs.formLabel}>E-mail do Tomador</label>
            <input
              type="email"
              className={cs.input}
              placeholder="Para envio da NF"
              value={form.tomador_email ?? ''}
              onChange={(e) => set('tomador_email', e.target.value)}
            />
          </div>

          {/* Valor */}
          <div>
            <label className={cs.formLabel}>Valor dos Serviços (R$) *</label>
            <input
              type="number"
              min="0.01"
              step="0.01"
              className={cs.input}
              value={form.valor_servicos || ''}
              onChange={(e) => set('valor_servicos', parseFloat(e.target.value) || 0)}
            />
          </div>

          {/* Código de tributação */}
          <div>
            <label className={cs.formLabel}>Cód. Tributação Nacional</label>
            <input
              className={cs.input}
              value={form.cod_tributacao_nacional ?? ''}
              onChange={(e) => set('cod_tributacao_nacional', e.target.value)}
              title="Padrão 010900 — Advocacia (LC 116/2003 item 17.14)"
            />
          </div>

          {/* Descrição */}
          <div className={cs.formGridFull}>
            <label className={cs.formLabel}>Descrição do Serviço *</label>
            <textarea
              className={cs.textarea}
              value={form.descricao_servico}
              onChange={(e) => set('descricao_servico', e.target.value)}
              placeholder="Honorários advocatícios referentes ao Processo nº ... — competência MM/AAAA"
              rows={3}
            />
          </div>

          {/* Toggle retenções */}
          <div className={cs.formGridFull}>
            <button
              type="button"
              className={cs.retencaoToggle}
              onClick={() => setMostrarRetencoes((v) => !v)}
            >
              {mostrarRetencoes ? '▲' : '▼'} Retenções na fonte (IR, INSS, CSLL, COFINS, PIS)
            </button>

            {mostrarRetencoes && (
              <div className={cs.retencaoGrid}>
                {(['ir', 'inss', 'csll', 'cofins', 'pis'] as const).map((campo) => (
                  <div key={campo}>
                    <label className={cs.formLabel}>{campo.toUpperCase()} (R$)</label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      className={cs.input}
                      value={(form[`retencao_${campo}` as keyof EmitirNFSeIn] as number) || ''}
                      onChange={(e) =>
                        set(`retencao_${campo}` as keyof EmitirNFSeIn, parseFloat(e.target.value) || 0 as any)
                      }
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {erro && <div className={cs.erroBox}>⚠️ {erro}</div>}

        <div className={cs.modalFooter}>
          <button className={cs.btnSecondary} onClick={onClose}>
            Cancelar
          </button>
          <button
            className={styles.btnPrimary}
            disabled={mutation.isPending || !form.tomador_cpf_cnpj || !form.tomador_nome || !form.valor_servicos || !form.descricao_servico}
            onClick={() => { setErro(null); mutation.mutate(form) }}
          >
            {mutation.isPending ? 'Emitindo…' : '📤 Emitir NFS-e'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Modal detalhe/cancelamento ───────────────────────────────────────────────

function DetalheModal({ nf, onClose }: { nf: NotaFiscalOut; onClose: () => void }) {
  const [motivoCancelamento, setMotivoCancelamento] = useState('')
  const [confirmandoCancel, setConfirmandoCancel] = useState(false)
  const qc = useQueryClient()

  const cancelMutation = useMutation({
    mutationFn: (motivo: string) => fiscalApi.cancelar(nf.id, motivo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
      onClose()
    },
  })

  return (
    <div className={cs.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={cs.modal}>
        <button className={cs.closeBtn} onClick={onClose}>✕</button>
        <div className={cs.modalTitle}>
          🧾 NFS-e
          {nf.numero_nfse && <span className={cs.nfNumero}>#{nf.numero_nfse}</span>}
          <span className={`${styles.badge} ${STATUS_CLASS[nf.status]}`}>
            {STATUS_LABEL[nf.status]}
          </span>
        </div>

        <div className={cs.detailGrid}>
          <span className={cs.detailLabel}>Competência</span>
          <span className={cs.detailValue}>{fmtCompetencia(nf.competencia)}</span>

          <span className={cs.detailLabel}>Emissão</span>
          <span className={cs.detailValue}>{fmtData(nf.data_emissao)}</span>

          <span className={cs.detailLabel}>Tomador</span>
          <span className={cs.detailValue}>{nf.tomador_nome}</span>

          <span className={cs.detailLabel}>CPF/CNPJ</span>
          <span className={cs.detailValue}>{nf.tomador_cpf_cnpj}</span>

          {nf.tomador_email && <>
            <span className={cs.detailLabel}>E-mail</span>
            <span className={cs.detailValue}>{nf.tomador_email}</span>
          </>}

          <span className={cs.detailLabel}>Valor serviços</span>
          <span className={cs.detailValue}>{fmtValor(nf.valor_servicos)}</span>

          {nf.valor_liquido !== nf.valor_servicos && <>
            <span className={cs.detailLabel}>Valor líquido</span>
            <span className={cs.detailValue}>{fmtValor(nf.valor_liquido)}</span>
          </>}

          <span className={cs.detailLabel}>Descrição</span>
          <span className={cs.detailValue}>{nf.descricao_servico}</span>

          {nf.chave_acesso && <>
            <span className={cs.detailLabel}>Chave acesso</span>
            <span className={cs.detailValue} style={{ fontSize: 11, wordBreak: 'break-all' }}>
              {nf.chave_acesso}
            </span>
          </>}

          {nf.erro_mensagem && <>
            <span className={cs.detailLabel}>Erro</span>
            <span className={cs.detailValue} style={{ color: '#c2410c' }}>{nf.erro_mensagem}</span>
          </>}

          {nf.xml_nfse && <>
            <span className={cs.detailLabel}>XML</span>
            <pre className={cs.xmlBlock}>{nf.xml_nfse.slice(0, 2000)}</pre>
          </>}
        </div>

        {nf.status === 'emitida' && (
          <div style={{ marginTop: 20 }}>
            {!confirmandoCancel ? (
              <button
                className={styles.btnDanger}
                onClick={() => setConfirmandoCancel(true)}
              >
                Cancelar NFS-e
              </button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label className={cs.formLabel}>Motivo do cancelamento *</label>
                <input
                  className={cs.input}
                  placeholder="Mínimo 10 caracteres"
                  value={motivoCancelamento}
                  onChange={(e) => setMotivoCancelamento(e.target.value)}
                />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    className={styles.btnDanger}
                    disabled={motivoCancelamento.length < 10 || cancelMutation.isPending}
                    onClick={() => cancelMutation.mutate(motivoCancelamento)}
                  >
                    {cancelMutation.isPending ? 'Cancelando…' : 'Confirmar cancelamento'}
                  </button>
                  <button
                    className={cs.btnSecondary}
                    onClick={() => setConfirmandoCancel(false)}
                  >
                    Voltar
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <div className={cs.modalFooter}>
          <button className={cs.btnSecondary} onClick={onClose}>Fechar</button>
        </div>
      </div>
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

type Filtro = 'todas' | 'emitida' | 'rascunho' | 'cancelada' | 'erro'

export default function FiscalPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [filtro, setFiltro] = useState<Filtro>('todas')
  const [emitindo, setEmitindo] = useState(false)
  const [prefillInicial, setPrefillInicial] = useState<Partial<EmitirNFSeIn> | undefined>()
  const [nfSelecionada, setNfSelecionada] = useState<NotaFiscalOut | null>(null)
  const [nfEmitida, setNfEmitida] = useState<NotaFiscalOut | null>(null)

  // Abre modal pré-preenchido quando vem do Financeiro (?honorario=...&recebimento=...)
  useEffect(() => {
    const honorarioId = searchParams.get('honorario')
    const recebimentoId = searchParams.get('recebimento') ?? undefined
    if (honorarioId) {
      fiscalApi.prefillDeHonorario(honorarioId, recebimentoId).then((dados) => {
        setPrefillInicial({
          competencia: dados.competencia,
          tomador_cpf_cnpj: dados.tomador_cpf_cnpj ?? '',
          tomador_nome: dados.tomador_nome ?? '',
          tomador_email: dados.tomador_email ?? '',
          valor_servicos: dados.valor_servicos,
          descricao_servico: dados.descricao_servico,
          honorario_id: dados.honorario_id,
          recebimento_id: dados.recebimento_id,
        })
        setEmitindo(true)
        setSearchParams({})  // limpa os params da URL
      })
    }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const { data: notas = [], isLoading } = useQuery({
    queryKey: ['notas-fiscais', filtro],
    queryFn: () => fiscalApi.listar(filtro !== 'todas' ? { status: filtro } : undefined),
  })

  const qc = useQueryClient()

  function handleSucesso(nf: NotaFiscalOut) {
    setEmitindo(false)
    setNfEmitida(nf)
    qc.invalidateQueries({ queryKey: ['notas-fiscais'] })
  }

  function abrirDetalhe(resumo: NotaFiscalResumo) {
    fiscalApi.obter(resumo.id).then(setNfSelecionada)
  }

  const filtros: { key: Filtro; label: string }[] = [
    { key: 'todas', label: 'Todas' },
    { key: 'emitida', label: 'Emitidas' },
    { key: 'rascunho', label: 'Rascunho' },
    { key: 'erro', label: 'Erro' },
    { key: 'cancelada', label: 'Canceladas' },
  ]

  return (
    <div>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          Notas Fiscais <strong>NFS-e</strong>
        </h1>
        <button className={styles.btnPrimary} onClick={() => setEmitindo(true)}>
          + Emitir NFS-e
        </button>
      </div>

      {/* Filtros */}
      <div className={cs.filtros}>
        {filtros.map((f) => (
          <button
            key={f.key}
            className={`${cs.filtroBtn} ${filtro === f.key ? cs.filtroBtnActive : ''}`}
            onClick={() => setFiltro(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Tabela */}
      <div className={styles.tableCard}>
        {isLoading ? (
          <div className={styles.empty}>Carregando…</div>
        ) : notas.length === 0 ? (
          <div className={styles.empty}>
            Nenhuma nota fiscal encontrada.
            <br />
            <small>Clique em "Emitir NFS-e" para emitir a primeira.</small>
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Nº NFS-e</th>
                <th>Competência</th>
                <th>Tomador</th>
                <th>Valor</th>
                <th>Líquido</th>
                <th>Emissão</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {notas.map((nf) => (
                <tr key={nf.id}>
                  <td>
                    <strong>{nf.numero_nfse ?? '—'}</strong>
                  </td>
                  <td>{fmtCompetencia(nf.competencia)}</td>
                  <td>{nf.tomador_nome}</td>
                  <td>{fmtValor(nf.valor_servicos)}</td>
                  <td>{fmtValor(nf.valor_liquido)}</td>
                  <td>{fmtData(nf.data_emissao)}</td>
                  <td>
                    <span className={`${styles.badge} ${STATUS_CLASS[nf.status]}`}>
                      {STATUS_LABEL[nf.status]}
                    </span>
                  </td>
                  <td>
                    <button
                      className={styles.btnTable}
                      onClick={() => abrirDetalhe(nf)}
                    >
                      Ver
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modal emissão */}
      {emitindo && (
        <EmissaoModal
          inicial={prefillInicial}
          onClose={() => { setEmitindo(false); setPrefillInicial(undefined) }}
          onSucesso={handleSucesso}
        />
      )}

      {/* Modal sucesso pós-emissão */}
      {nfEmitida && (
        <DetalheModal nf={nfEmitida} onClose={() => setNfEmitida(null)} />
      )}

      {/* Modal detalhe */}
      {nfSelecionada && !nfEmitida && (
        <DetalheModal nf={nfSelecionada} onClose={() => setNfSelecionada(null)} />
      )}
    </div>
  )
}
