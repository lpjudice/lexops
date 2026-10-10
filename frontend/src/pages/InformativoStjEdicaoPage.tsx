import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { informativoStjApi } from '../api/informativoStj'
import type { InformativoStjItem } from '../api/informativoStj'
import styles from './InformativoStjEdicaoPage.module.css'

function Verbete({ item }: { item: InformativoStjItem }) {
  const [aberto, setAberto] = useState(false)
  const qc = useQueryClient()

  const reprocessar = useMutation({
    mutationFn: () => informativoStjApi.reprocessarItem(item.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stj'] }),
  })

  return (
    <div className={`${styles.verbete} ${item.destacado ? styles.verbeteDestacado : ''}`}>
      <div className={styles.verbeteHead} onClick={() => setAberto((v) => !v)}>
        <div className={styles.verbeteHeadLeft}>
          <div className={styles.verbeteTitulo}>{item.titulo}</div>
          <div className={styles.verbeteDestaqueOficial}>{item.destaque_oficial}</div>
          <div className={styles.verbeteMeta}>
            <span className={`${styles.pill} ${item.destacado ? styles.pillDestacado : ''}`}>
              {item.ramo_direito}
            </span>
            {item.destacado && <span className={`${styles.pill} ${styles.pillDestacado}`}>Destacado</span>}
          </div>
          {item.processo_numero && (
            <div className={styles.processoLinha}>
              {item.processo_url ? (
                <a href={item.processo_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                  {item.processo_numero}
                </a>
              ) : (
                item.processo_numero
              )}
              {item.relator && ` · Rel. ${item.relator}`}
            </div>
          )}
        </div>
        {aberto ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
      </div>

      {aberto && (
        <div className={styles.verbeteBody}>
          {item.destacado && item.status_ia === 'ok' && (
            <div className={styles.resumoBloco}>
              <span className={styles.resumoLabel}>Tema central</span>
              <p className={styles.resumoTexto}>{item.resumo_tema_central}</p>
              <span className={styles.resumoLabel} style={{ marginTop: 10, display: 'block' }}>
                Ratio decidendi
              </span>
              <p className={styles.resumoTexto}>{item.resumo_ratio_decidendi}</p>
            </div>
          )}

          {item.destacado && item.status_ia !== 'ok' && (
            <div className={styles.statusIa}>
              {item.status_ia === 'processando' && (
                <>
                  <Loader2 size={14} className="spin" /> Gerando resumo estruturado…
                </>
              )}
              {item.status_ia === 'pendente' && <>Resumo estruturado ainda não processado.</>}
              {item.status_ia === 'erro' && <>Erro ao gerar resumo: {item.erro_ia}</>}
              <button className={styles.btnReprocessar} onClick={() => reprocessar.mutate()} disabled={reprocessar.isPending}>
                {reprocessar.isPending ? 'Processando…' : 'Reprocessar'}
              </button>
            </div>
          )}

          {item.texto_explicativo && (
            <div>
              <span className={styles.resumoLabel} style={{ color: 'var(--gray-mid)' }}>
                Informações do inteiro teor (STJ)
              </span>
              <p className={styles.resumoTexto} style={{ color: 'var(--gray-mid)' }}>
                {item.texto_explicativo}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function InformativoStjEdicaoPage() {
  const { edicaoId } = useParams<{ edicaoId: string }>()
  const navigate = useNavigate()

  const { data: edicao, isLoading } = useQuery({
    queryKey: ['informativo-stj', 'edicoes', edicaoId],
    queryFn: () => informativoStjApi.getEdicao(edicaoId!),
    enabled: !!edicaoId,
  })

  if (isLoading || !edicao) return <p>Carregando…</p>

  const porOrgao = edicao.itens.reduce<Record<string, typeof edicao.itens>>((acc, item) => {
    const key = item.orgao_julgador || 'Outros'
    acc[key] = acc[key] || []
    acc[key].push(item)
    return acc
  }, {})

  return (
    <div>
      <button className={styles.voltar} onClick={() => navigate('/informativo-stj')}>
        <ArrowLeft size={14} /> Voltar às edições
      </button>
      <div className={styles.titulo}>
        Informativo nº {edicao.numero}
        {edicao.data_publicacao && ` — ${new Date(edicao.data_publicacao + 'T00:00:00').toLocaleDateString('pt-BR')}`}
      </div>

      {Object.entries(porOrgao).map(([orgao, itens]) => (
        <div key={orgao}>
          <div className={styles.orgao}>{orgao}</div>
          {itens.map((item) => (
            <Verbete key={item.id} item={item} />
          ))}
        </div>
      ))}
    </div>
  )
}
