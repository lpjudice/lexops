import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ChevronDown, ChevronRight, Loader2, Star, Camera, CheckCircle2, Mail, X } from 'lucide-react'
import { informativoStjApi } from '../api/informativoStj'
import type { InformativoStjItem } from '../api/informativoStj'
import { ramoCor } from '../utils/ramoColor'
import styles from './InformativoStjEdicaoPage.module.css'

const INSTAGRAM_STATUS_LABEL: Record<string, string> = {
  sugerido: 'Instagram: sugerido',
  aprovado: 'Instagram: aprovado',
  rejeitado: 'Instagram: rejeitado',
  publicado: 'Instagram: publicado',
}

function EmailPopover({ itemId, onClose }: { itemId: string; onClose: () => void }) {
  const [destinatario, setDestinatario] = useState('')
  const enviar = useMutation({
    mutationFn: (email?: string) => informativoStjApi.enviarEmailItem(itemId, email),
  })

  return (
    <div className={styles.emailPopover} onClick={(e) => e.stopPropagation()}>
      <div className={styles.emailPopoverHeader}>
        <span>Enviar por e-mail</span>
        <button className={styles.emailPopoverClose} onClick={onClose}><X size={14} /></button>
      </div>
      <button className={styles.emailPopoverBtn} onClick={() => enviar.mutate(undefined)} disabled={enviar.isPending}>
        Enviar para o meu e-mail
      </button>
      <div className={styles.emailPopoverRow}>
        <input
          className={styles.emailPopoverInput}
          placeholder="ou outro e-mail…"
          value={destinatario}
          onChange={(e) => setDestinatario(e.target.value)}
        />
        <button
          className={styles.emailPopoverBtn}
          onClick={() => destinatario.trim() && enviar.mutate(destinatario.trim())}
          disabled={enviar.isPending || !destinatario.trim()}
        >
          Enviar
        </button>
      </div>
      {enviar.isSuccess && <div className={styles.emailPopoverOk}>Enviado ✓</div>}
      {enviar.isError && <div className={styles.emailPopoverErro}>Falha ao enviar</div>}
    </div>
  )
}

function Verbete({ item, destacarItem }: { item: InformativoStjItem; destacarItem: string | null }) {
  const [aberto, setAberto] = useState(false)
  const [verTextoOriginal, setVerTextoOriginal] = useState(false)
  const [verLeigo, setVerLeigo] = useState(false)
  const [emailAberto, setEmailAberto] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const qc = useQueryClient()
  const cor = ramoCor(item.ramo_direito)

  useEffect(() => {
    if (destacarItem === item.id) {
      setAberto(true)
      setTimeout(() => ref.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 150)
    }
  }, [destacarItem, item.id])

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

  const jaGerouInstagram = !!item.instagram_gerado_em
  const instagramLabel = item.instagram_status ? INSTAGRAM_STATUS_LABEL[item.instagram_status] : null
  const instagramRejeitado = item.instagram_status === 'rejeitado'

  const temResumoIa = item.destacado && item.status_ia === 'ok' && !!item.resumo_tema_central
  const headline = temResumoIa ? item.resumo_tema_central : item.destaque_oficial

  return (
    <div
      ref={ref}
      className={`${styles.verbete} ${item.destacado ? styles.verbeteDestacado : ''} ${destacarItem === item.id ? styles.verbeteSelecionado : ''}`}
      style={{ borderLeftColor: cor.fg }}
    >
      <div className={styles.verbeteHead} onClick={() => setAberto((v) => !v)}>
        <div className={styles.verbeteHeadLeft}>
          <div className={styles.verbeteMeta}>
            <span className={styles.pill} style={{ background: cor.bg, color: cor.fg }}>
              {item.ramo_direito}
            </span>
            {item.destacado && <span className={`${styles.pill} ${styles.pillDestacado}`}>Destacado</span>}
            {temResumoIa && (
              <span className={styles.pill} title="Gerado por IA a partir do texto oficial do STJ">
                ✨ Resumo por IA
              </span>
            )}
            {instagramLabel && (
              <span className={`${styles.pill} ${instagramRejeitado ? styles.pillInstagramRejeitado : styles.pillInstagram}`}>
                <Camera size={10} /> {instagramLabel}
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

            <div style={{ position: 'relative' }}>
              <button className={styles.starBtn} onClick={() => setEmailAberto((v) => !v)} title="Enviar por e-mail">
                <Mail size={17} />
              </button>
              {emailAberto && <EmailPopover itemId={item.id} onClose={() => setEmailAberto(false)} />}
            </div>

            {item.destacado && (
              <button className={styles.btnReprocessar} onClick={() => reprocessar.mutate()} disabled={reprocessar.isPending}>
                {reprocessar.isPending ? 'Processando…' : 'Reprocessar resumo'}
              </button>
            )}

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
              <button className={styles.btnLeigo} onClick={() => setVerTextoOriginal((v) => !v)}>
                {verTextoOriginal ? 'Ocultar' : 'Ver'} texto oficial do STJ (original, sem IA)
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
  const [searchParams] = useSearchParams()
  const destacarItem = searchParams.get('item')
  const [ramosFiltro, setRamosFiltro] = useState<string[]>([])

  const { data: edicao, isLoading } = useQuery({
    queryKey: ['informativo-stj', 'edicoes', edicaoId],
    queryFn: () => informativoStjApi.getEdicao(edicaoId!),
    enabled: !!edicaoId,
  })

  if (isLoading || !edicao) return <p>Carregando…</p>

  const todosRamos = Array.from(new Set(edicao.itens.map((i) => i.ramo_direito))).sort()
  const itensFiltrados = ramosFiltro.length === 0 ? edicao.itens : edicao.itens.filter((i) => ramosFiltro.includes(i.ramo_direito))

  const porOrgao = itensFiltrados.reduce<Record<string, typeof edicao.itens>>((acc, item) => {
    const key = item.orgao_julgador || 'Outros'
    acc[key] = acc[key] || []
    acc[key].push(item)
    return acc
  }, {})

  function toggleRamo(ramo: string) {
    setRamosFiltro((atual) => (atual.includes(ramo) ? atual.filter((r) => r !== ramo) : [...atual, ramo]))
  }

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
        <p style={{ fontSize: 14, color: 'var(--dark)', marginTop: -8, marginBottom: 16, lineHeight: 1.6 }}>
          {edicao.resumo_edicao}
        </p>
      )}

      {todosRamos.length > 1 && (
        <div className={styles.filtroChips}>
          {todosRamos.map((ramo) => {
            const cor = ramoCor(ramo)
            const ativo = ramosFiltro.includes(ramo)
            return (
              <button
                key={ramo}
                className={styles.filtroChip}
                style={ativo ? { background: cor.fg, color: '#fff', borderColor: cor.fg } : { borderColor: cor.fg, color: cor.fg }}
                onClick={() => toggleRamo(ramo)}
              >
                {ramo}
              </button>
            )
          })}
          {ramosFiltro.length > 0 && (
            <button className={styles.filtroChipLimpar} onClick={() => setRamosFiltro([])}>
              Limpar filtro
            </button>
          )}
        </div>
      )}

      {Object.entries(porOrgao).map(([orgao, itens]) => (
        <div key={orgao}>
          <div className={styles.orgao}>{orgao}</div>
          {itens.map((item) => (
            <Verbete key={item.id} item={item} destacarItem={destacarItem} />
          ))}
        </div>
      ))}
    </div>
  )
}
