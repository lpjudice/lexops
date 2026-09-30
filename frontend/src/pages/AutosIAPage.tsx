import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../api/autosIa'
import type { CasoResumo } from '../api/autosIa'
import ProcessoCombobox from '../components/autosIa/ProcessoCombobox'
import Modal from '../components/Modal'
import styles from './Page.module.css'

const CONFIRMACAO_EXCLUSAO = 'DELETAR'

export default function AutosIAPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [nome, setNome] = useState('')
  const [numeroProcesso, setNumeroProcesso] = useState('')
  const [descricao, setDescricao] = useState('')
  const [processoId, setProcessoId] = useState('')
  const [syncAtivo, setSyncAtivo] = useState(false)
  const [importarExistentes, setImportarExistentes] = useState(true)
  const [casoParaExcluir, setCasoParaExcluir] = useState<CasoResumo | null>(null)

  const { data: casos = [], isLoading } = useQuery({
    queryKey: ['autos-ia', 'casos'],
    queryFn: () => autosIa.listarCasos(),
  })

  const deletar = useMutation({
    mutationFn: (casoId: string) => autosIa.deletarCaso(casoId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['autos-ia', 'casos'] })
      setCasoParaExcluir(null)
    },
    onError: (e: any) => {
      setCasoParaExcluir(null)
      alert(`Erro ao excluir: ${e?.response?.data?.detail || e?.message}`)
    },
  })

  const criar = useMutation({
    mutationFn: () => autosIa.criarCaso({
      nome,
      numero_processo: numeroProcesso || undefined,
      descricao: descricao || undefined,
      processo_id: processoId || undefined,
      sync_jusbr_ativo: !!processoId && syncAtivo,
    }),
    onSuccess: async (caso) => {
      qc.invalidateQueries({ queryKey: ['autos-ia', 'casos'] })
      if (processoId && importarExistentes) {
        try { await autosIa.importarExistentes(caso.id) } catch { /* segue pro caso mesmo assim */ }
      }
      setShowForm(false)
      setNome('')
      setNumeroProcesso('')
      setDescricao('')
      setProcessoId('')
      setSyncAtivo(false)
      setImportarExistentes(true)
      navigate(`/autos-ia/${caso.id}`)
    },
  })

  return (
    <div>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Autos IA</h1>
          <p style={{ fontSize: 13, color: 'var(--gray-mid)', marginTop: 4 }}>
            Leitura incremental de processos volumosos: suba os autos em blocos e o sistema
            organiza, resume e indexa cada peça automaticamente. Independente do restante do gestor.
          </p>
        </div>
        <button className={styles.btnPrimary} onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : '+ Novo caso'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); criar.mutate() }}
          className={styles.form}
        >
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Nome do caso *</label>
            <input
              className={styles.input}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Ação de Cobrança — Fulano x Beltrano"
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Número do processo (opcional)</label>
            <input
              className={styles.input}
              value={numeroProcesso}
              onChange={(e) => setNumeroProcesso(e.target.value)}
              placeholder="0000000-00.0000.0.00.0000"
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Descrição (opcional)</label>
            <textarea
              className={styles.input}
              rows={3}
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Vincular a um processo do gestor (opcional)</label>
            <ProcessoCombobox
              value={processoId}
              onChange={(id) => { setProcessoId(id); if (!id) setSyncAtivo(false) }}
            />
          </div>
          {processoId && (
            <>
              <div className={styles.formRow}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={importarExistentes}
                    onChange={(e) => setImportarExistentes(e.target.checked)}
                  />
                  Importar agora os documentos que o jus.br já baixou para esse processo
                  (indexa tudo que já existe, sem precisar subir PDF manualmente).
                </label>
              </div>
              <div className={styles.formRow}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
                  <input type="checkbox" checked={syncAtivo} onChange={(e) => setSyncAtivo(e.target.checked)} />
                  Sincronizar automaticamente com o jus.br (3x/dia) — importa os andamentos e
                  documentos novos, à medida que forem sendo baixados.
                </label>
              </div>
            </>
          )}
          <button type="submit" className={styles.btnPrimary} disabled={criar.isPending || !nome.trim()}>
            {criar.isPending ? 'Criando...' : 'Criar caso'}
          </button>
        </form>
      )}

      {isLoading ? (
        <p className={styles.empty}>Carregando...</p>
      ) : casos.length === 0 ? (
        <p className={styles.empty}>Nenhum caso cadastrado ainda.</p>
      ) : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Caso</th>
                <th>Processo</th>
                <th>Páginas</th>
                <th>Peças</th>
                <th>FAQ</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {casos.map((c) => (
                <tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/autos-ia/${c.id}`)}>
                  <td>
                    <strong>{c.nome}</strong>
                    {c.tem_peca_pendente_continuacao && (
                      <span className={styles.badge} style={{ marginLeft: 8, background: '#fef9c3', color: '#a16207' }}>
                        peça em aberto
                      </span>
                    )}
                  </td>
                  <td>
                    {c.numero_processo || '—'}
                    {c.processo_id && (
                      <span className={styles.badge} style={{ marginLeft: 8 }}>
                        {c.sync_jusbr_ativo ? 'jus.br 3x/dia' : 'vinculado'}
                      </span>
                    )}
                  </td>
                  <td>{c.total_paginas}</td>
                  <td>{c.total_pecas}</td>
                  <td>{c.total_perguntas_faq}</td>
                  <td>
                    <span className={`${styles.badge} ${styles[`status_${c.status}`]}`}>{c.status}</span>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button
                      className={styles.btnDanger}
                      disabled={deletar.isPending || c.ultimo_sync_status === 'processando'}
                      title={c.ultimo_sync_status === 'processando' ? 'Cancele a sincronização em andamento antes de excluir' : undefined}
                      onClick={() => setCasoParaExcluir(c)}
                    >
                      Excluir
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {casoParaExcluir && (
        <ModalConfirmarExclusao
          nomeCaso={casoParaExcluir.nome}
          isPending={deletar.isPending}
          onConfirmar={() => deletar.mutate(casoParaExcluir.id)}
          onClose={() => setCasoParaExcluir(null)}
        />
      )}
    </div>
  )
}

function ModalConfirmarExclusao({
  nomeCaso, isPending, onConfirmar, onClose,
}: { nomeCaso: string; isPending: boolean; onConfirmar: () => void; onClose: () => void }) {
  const [texto, setTexto] = useState('')
  const confirmado = texto.trim() === CONFIRMACAO_EXCLUSAO

  return (
    <Modal title="Excluir caso" onClose={onClose}>
      <p style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 12 }}>
        Excluir <strong>"{nomeCaso}"</strong>? Apaga todas as peças, o grafo e as perguntas já
        indexadas — todo o custo e tempo de leitura já gastos nesse caso se perdem, e não pode ser desfeito.
      </p>
      <p style={{ fontSize: 12.5, marginBottom: 6 }}>
        Digite <strong>{CONFIRMACAO_EXCLUSAO}</strong> para confirmar:
      </p>
      <input
        className={styles.input}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder={CONFIRMACAO_EXCLUSAO}
        autoFocus
      />
      <div style={{ display: 'flex', gap: 8, marginTop: 14, justifyContent: 'flex-end' }}>
        <button className={styles.btnSmall} onClick={onClose}>Cancelar</button>
        <button
          className={styles.btnDanger}
          disabled={!confirmado || isPending}
          onClick={onConfirmar}
        >
          {isPending ? 'Excluindo...' : 'Excluir definitivamente'}
        </button>
      </div>
    </Modal>
  )
}
