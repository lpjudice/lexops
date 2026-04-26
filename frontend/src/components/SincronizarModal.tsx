import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { andamentosApi } from '../api/andamentos'
import type { JusbrSessionStatus, SincronizacaoResult } from '../api/andamentos'
import type { Processo } from '../api/processos'
import InstrucoesJusBRModal from './InstrucoesJusBRModal'
import styles from './SincronizarModal.module.css'
import {
  clearStoredJusbrToken,
  saveStoredJusbrToken,
} from '../utils/jusbrToken'
import { inferTribunalFromCnj } from '../utils/cnj'

interface Props {
  processos: Processo[]
  onClose: () => void
}

type Fonte = 'datajud' | 'jusbr'

// All tribunals covered by DataJud
const DATAJUD_SUPORTADOS = new Set([
  'TJES', 'TJSP', 'TJAM', 'TRF2', 'TJRJ', 'TJMG', 'TJRS', 'TJPR', 'TJSC', 'TJDFT',
  'TJBA', 'TJGO', 'TJPE', 'TJCE', 'TJMA', 'TJPA', 'TJPB', 'TJPI', 'TJAL',
  'TJSE', 'TJRN', 'TJMT', 'TJMS', 'TJRO', 'TJTO', 'TJAC', 'TJAP', 'TJRR',
  'TRF1', 'TRF3', 'TRF4', 'TRF5', 'TRF6', 'STJ', 'TST', 'TSE', 'STM',
])

function suportaDataJud(p: Processo) {
  const tribunal = (p.tribunal || inferTribunalFromCnj(p.numero_cnj) || '').toUpperCase()
  return !!tribunal && DATAJUD_SUPORTADOS.has(tribunal)
}

// Any tribunal with a CNJ number can theoretically be found in jus.br
function suportaJusBR(p: Processo) {
  return !!p.numero_cnj && !!p.tribunal
}

export default function SincronizarModal({ processos, onClose }: Props) {
  const qc = useQueryClient()
  const [fonte, setFonte] = useState<Fonte>('datajud')
  const [showInstrucoes, setShowInstrucoes] = useState(false)
  const [resultados, setResultados] = useState<SincronizacaoResult[] | null>(null)
  const { data: jusbrSession, refetch: refetchJusbrSession } = useQuery<JusbrSessionStatus>({
    queryKey: ['jusbr-session'],
    queryFn: () => andamentosApi.obterSessaoJusBR(),
    staleTime: 30_000,
  })
  const tokenExpiry = jusbrSession?.expires_at
    ? new Date(jusbrSession.expires_at).toLocaleString('pt-BR', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    : null
  const jusbrAtivo = !!jusbrSession?.active

  const disponiveis = processos.filter(fonte === 'datajud' ? suportaDataJud : suportaJusBR)
  const [selecionados, setSelecionados] = useState<Set<string>>(
    new Set(disponiveis.map((p) => p.id))
  )

  const syncDataJud = useMutation({
    mutationFn: () => andamentosApi.sincronizarBatch(Array.from(selecionados)),
    onSuccess: (data) => {
      setResultados(data)
      qc.invalidateQueries({ queryKey: ['processos'] })
      qc.invalidateQueries({ queryKey: ['andamentos'] })
      qc.invalidateQueries({ queryKey: ['andamentos-count'] })
    },
  })

  const syncJusBR = useMutation({
    mutationFn: () =>
      andamentosApi.sincronizarBatchJusBR(Array.from(selecionados)),
    onSuccess: (data) => {
      setResultados(data)
      qc.invalidateQueries({ queryKey: ['processos'] })
      qc.invalidateQueries({ queryKey: ['andamentos'] })
      qc.invalidateQueries({ queryKey: ['andamentos-count'] })
    },
  })

  const isSyncing = syncDataJud.isPending || syncJusBR.isPending

  const toggle = (id: string) => {
    setSelecionados((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selecionados.size === disponiveis.length) setSelecionados(new Set())
    else setSelecionados(new Set(disponiveis.map((p) => p.id)))
  }

  function handleSync() {
    if (fonte === 'datajud') {
      syncDataJud.mutate()
    } else {
      if (!jusbrAtivo) {
        setShowInstrucoes(true)
      } else {
        syncJusBR.mutate()
      }
    }
  }

  const configurarSessao = useMutation({
    mutationFn: (capture: string) => andamentosApi.configurarSessaoJusBR(capture),
    onSuccess: async (_, capture) => {
      saveStoredJusbrToken(capture)
      await refetchJusbrSession()
      syncJusBR.mutate()
    },
  })

  function handleJusBRToken(capture: string) {
    configurarSessao.mutate(capture)
  }

  // When switching fonte, reset selection to new available list
  function handleFonteChange(f: Fonte) {
    setFonte(f)
    const novosDisponiveis = processos.filter(f === 'datajud' ? suportaDataJud : suportaJusBR)
    setSelecionados(new Set(novosDisponiveis.map((p) => p.id)))
    setResultados(null)
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>Sincronizar Andamentos</h2>
          <button className={styles.btnClose} onClick={onClose}>×</button>
        </div>

        {/* Fonte toggle */}
        <div className={styles.fonteRow}>
          <span className={styles.fonteLabel}>Fonte:</span>
          <div className={styles.fonteToggle}>
            <button
              className={`${styles.fonteBtn} ${fonte === 'datajud' ? styles.fonteBtnActive : ''}`}
              onClick={() => handleFonteChange('datajud')}
              title="DataJud — CNJ (automático, sem login)"
            >
              DataJud v1
            </button>
            <button
              className={`${styles.fonteBtn} ${fonte === 'jusbr' ? styles.fonteBtnActive : ''}`}
              onClick={() => handleFonteChange('jusbr')}
              title="jus.br — dados completos com nomes reais dos documentos (requer token de sessão)"
            >
              jus.br v1
            </button>
          </div>
          {fonte === 'jusbr' && jusbrAtivo && (
            <button
              className={styles.btnTokenSet}
              onClick={() => setShowInstrucoes(true)}
              title="Clique para renovar a sessão"
            >
              🔑 sessão ativa
            </button>
          )}
        </div>

        {/* JusBR info */}
        {fonte === 'jusbr' && (
          <div className={styles.avisoJusBR}>
            <strong>jus.br</strong> retorna nomes reais dos documentos e dados completos via PDPJ,
            mas agora pode reutilizar uma <strong>sessão compartilhada</strong> do app inteiro.
            {jusbrAtivo
              ? ` Sessão ativa no backend.${tokenExpiry ? ` Expira em ${tokenExpiry}.` : ''}`
              : ' Clique em "Sincronizar" para conectar uma vez e reutilizar nos outros processos.'}
            {jusbrAtivo && (
              <>
                {' '}
                <button
                  className={styles.btnToggleAll}
                  onClick={async () => {
                    await andamentosApi.limparSessaoJusBR()
                    clearStoredJusbrToken()
                    await refetchJusbrSession()
                  }}
                >
                  Limpar sessão
                </button>
              </>
            )}
          </div>
        )}

        <div className={styles.aviso}>
          <strong>Boas práticas:</strong> Use com moderação.
          Evite sincronizar processos com muita frequência para não sobrecarregar os portais.
          O sistema faz sync automático diário às 03h.
        </div>

        {!resultados ? (
          <>
            <div className={styles.selectHeader}>
              <span className={styles.selectLabel}>
                Processos disponíveis ({disponiveis.length})
              </span>
              {disponiveis.length > 0 && (
                <button className={styles.btnToggleAll} onClick={toggleAll}>
                  {selecionados.size === disponiveis.length ? 'Desmarcar todos' : 'Marcar todos'}
                </button>
              )}
            </div>

            {disponiveis.length === 0 ? (
              <p className={styles.empty}>
                {fonte === 'datajud'
                  ? 'Nenhum processo com tribunal mapeado no DataJud.'
                  : 'Nenhum processo com número CNJ e tribunal informados.'}
              </p>
            ) : (
              <div className={styles.lista}>
                {disponiveis.map((p) => (
                  <label key={p.id} className={styles.processoItem}>
                    <input
                      type="checkbox"
                      checked={selecionados.has(p.id)}
                      onChange={() => toggle(p.id)}
                    />
                    <code className={styles.cnj}>{p.numero_cnj}</code>
                    {p.tribunal && <span className={styles.tribunal}>{p.tribunal}</span>}
                  </label>
                ))}
              </div>
            )}

            {processos.length > disponiveis.length && (
              <p className={styles.semSupporte}>
                {processos.length - disponiveis.length} processo(s) sem dados suficientes (ignorados).
              </p>
            )}

            <div className={styles.modalFooter}>
              <button className={styles.btnCancel} onClick={onClose}>
                Cancelar
              </button>
              <button
                className={styles.btnSync}
                disabled={selecionados.size === 0 || isSyncing}
                onClick={handleSync}
              >
                {isSyncing
                  ? `Sincronizando ${selecionados.size}...`
                  : fonte === 'jusbr' && !jusbrAtivo
                  ? `🔑 Conectar jus.br e sincronizar ${selecionados.size}`
                  : `Sincronizar ${selecionados.size} processo(s)`}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className={styles.resultados}>
              {resultados.map((r) => (
                <div
                  key={r.processo_id}
                  className={`${styles.resultado} ${r.status === 'erro' ? styles.resultadoErro : r.novos_andamentos > 0 ? styles.resultadoNovo : ''}`}
                >
                  <span className={styles.resultadoCnj}>
                    {processos.find((p) => p.id === r.processo_id)?.numero_cnj ?? r.processo_id}
                  </span>
                  <span className={styles.resultadoStatus}>
                    {r.status === 'ok' && r.novos_andamentos > 0
                      ? `+${r.novos_andamentos} novo(s)`
                      : r.status === 'ok'
                      ? 'Atualizado'
                      : r.status === 'nenhum'
                      ? 'Nenhum encontrado'
                      : `Erro: ${r.mensagem}`}
                  </span>
                </div>
              ))}
            </div>
            <div className={styles.modalFooter}>
              <button className={styles.btnPrimary} onClick={onClose}>
                Fechar
              </button>
            </div>
          </>
        )}
      </div>

      {showInstrucoes && (
        <InstrucoesJusBRModal
          onClose={() => setShowInstrucoes(false)}
          onToken={handleJusBRToken}
          initialToken=""
        />
      )}
    </div>
  )
}
