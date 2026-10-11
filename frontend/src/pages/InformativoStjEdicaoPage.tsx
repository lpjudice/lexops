import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ChevronDown, ChevronRight, Loader2, Star, Camera, CheckCircle2 } from 'lucide-react'
import { informativoStjApi } from '../api/informativoStj'
import type { InformativoStjItem } from '../api/informativoStj'
import { ramoCor } from '../utils/ramoColor'
import styles from './InformativoStjEdicaoPage.module.css'

function Verbete({ item }: { item: InformativoStjItem }) {
  const [aberto, setAberto] = useState(false)
  const [verTextoOriginal, setVerTextoOriginal] = useState(false)
  const qc = useQueryClient()
  const cor = ramoCor(item.ramo_direito)

  const reprocessar = useMutation({
    mutationFn: () => informativoStjApi.reprocessarItem(item.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stj'] }),
  })

  const favoritar = useMutation({
    mutationFn: () => informativoStjApi.favoritar(item.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stj'] }),
  })

  const forcarInstagram = useMutation({
    mutationFn: () => informativoStjApi.forcarInstagram(item.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['informativo-stj'] }),
  })

  const [verLeigo, setVerLeigo] = useState(false)
  const jaGerouInstagram = !!item.instagram_gerado_em

  const temResumoIa = item.destacado && item.status_ia === 'ok' && !!item.resumo_tema_central
  const headline = temResumoIa ? item.resumo_tema_central : item.destaque_oficial

  return (
    <div className={`${styles.verbete} ${item.destacado ? styles.verbeteDestacado : ''}`} style={{ borderLeftColor: cor.fg }}>
      <div className={styles.verbeteHead} onClick={() => setAberto((v) => !v)}>
        <div className={styles.verbeteHeadLeft}>
          <div className={styles.verbeteMeta}>
            <span className={styles.pill} style={{ background: cor.bg, color: cor.fg }}>
              {item.ramo_direito}
            </span>
            {item.destacado && <span className={`${styles.pill} ${styles.pillDestacado}`}>Destacado</span>}
            {jaGerouInstagram && (
              <span className={`${styles.pill} ${styles.pillInstagram}`}>
                <Camera size={10} /> Gerado no Instagram
              </span>
            )}
          </div>
          <div className={styles.verbeteHeadline}>{headline}</div>
          <div className={styles.verbeteTitulo}>{item.titulo}</div>
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
              <span className={styles.resumoLabel}>Ratio decidendi — por que o STJ decidiu assim</span>
              <p className={styles.resumoTexto}>{item.resumo_ratio_decidendi}</p>

              {item.resumo_leigo && (
                <>
                  <button className={styles.btnLeigo} onClick={() => setVerLeigo((v) => !v)}>
                    {verLeigo ? 'Ocultar' : 'Explicar para um leigo'}
                  </button>
                  {verLeigo && <p className={styles.resumoTextoLeigo}>{item.resumo_leigo}</p>}
                </>
              )}
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

          <div className={styles.actionsRow}>
            <button
              className={styles.starBtn}
              onClick={() => favoritar.mutate()}
              disabled={favoritar.isPending}
              title={item.favorito ? 'Remover dos favoritos' : 'Favoritar'}
            >
              <Star size={18} className={item.favorito ? styles.starBtnAtivo : ''} fill={item.favorito ? 'currentColor' : 'none'} />
            </button>
            <button className={styles.btnInstagram} onClick={() => forcarInstagram.mutate()} disabled={forcarInstagram.isPending}>
              <Camera size={13} />
              {forcarInstagram.isPending ? 'Gerando…' : jaGerouInstagram ? 'Gerar novamente' : 'Gerar post no Instagram'}
            </button>
            {jaGerouInstagram && !forcarInstagram.isPending && (
              <span style={{ fontSize: 12, color: 'var(--teal)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <CheckCircle2 size={13} /> Já gerado
              </span>
            )}
            {forcarInstagram.isError && <span style={{ fontSize: 12, color: '#c0392b' }}>Falha ao gerar</span>}
          </div>

          {item.texto_explicativo && (
            <div style={{ marginTop: 12 }}>
              <button
                className={styles.btnReprocessar}
                onClick={() => setVerTextoOriginal((v) => !v)}
              >
                {verTextoOriginal ? 'Ocultar' : 'Ver'} texto original do STJ
              </button>
              {verTextoOriginal && (
                <p className={styles.resumoTexto} style={{ color: 'var(--gray-mid)', fontWeight: 400, fontSize: 12.5, marginTop: 8 }}>
                  {item.texto_explicativo}
                </p>
              )}
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
      {edicao.resumo_edicao && (
        <p style={{ fontSize: 14, color: 'var(--dark)', marginTop: -8, marginBottom: 20, lineHeight: 1.6 }}>
          {edicao.resumo_edicao}
        </p>
      )}

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
