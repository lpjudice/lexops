import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Camera,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Check,
  X,
  Send,
  Trash2,
  RotateCcw,
  Mail,
  Lightbulb,
} from 'lucide-react'
import { instagramApi } from '../api/instagram'
import type { SlideBlock, StatusSugestao, Sugestao } from '../api/instagram'
import page from './Page.module.css'
import s from './InstagramPage.module.css'

const CAPA_LABEL: Record<string, string> = {
  A: 'Dark Teal', B: 'White Bold', C: 'Cream', D: 'Split',
}
const FONTE_LABEL: Record<string, string> = {
  insight: 'Insight do site',
  publicacao: 'Publicação da semana',
  andamento: 'Andamento',
  peca: 'Peça produzida',
  tese: 'Tese IA',
  evergreen: 'Tema recorrente',
}

function pad2(n: number) {
  return String(n).padStart(2, '0')
}

// ─────────────────── Slide renderizado no padrão Pimenta Judice ───────────────────
function SlidePreview({ slide, index, total }: { slide: SlideBlock; index: number; total: number }) {
  const variante = slide.variante || 'light'
  const isCapa = slide.tipo === 'capa'
  const isCta = slide.tipo === 'cta'

  return (
    <div className={`${s.slide} ${s[variante]}`}>
      <div className={s.topBar} />
      {variante === 'light' && <div className={s.leftBar} />}
      <div className={s.geo} style={{ width: 460, height: 460, top: -150, right: -150, opacity: 0.6 }} />

      {!isCapa && total > 1 && <span className={s.slideNum}>{pad2(index + 1)}</span>}

      {isCapa ? (
        <div className={s.coverSafe}>
          {slide.tag && <span className={s.sTag} style={{ fontSize: 20, letterSpacing: 4 }}>{slide.tag}</span>}
          <div className={s.coverTitle}>{slide.titulo}</div>
          <div className={`${s.divider} ${s.dividerCenter}`} />
          {slide.subtitulo && <div className={s.coverSub}>{slide.subtitulo}</div>}
        </div>
      ) : (
        <div className={s.contentArea}>
          {slide.tag && <span className={s.sTag} style={{ marginBottom: 12 }}>{slide.tag}</span>}
          {slide.titulo && <div className={s.tTitulo}>{slide.titulo}</div>}
          <div className={s.divider} />
          {slide.subtitulo && <div className={s.tSub}>{slide.subtitulo}</div>}
          {slide.corpo && <div className={s.tCorpo}>{slide.corpo}</div>}
          {slide.bullets?.length > 0 && (
            <ul className={s.bulletList}>
              {slide.bullets.map((b, i) => <li key={i}>{b}</li>)}
            </ul>
          )}
          {slide.cards?.length > 0 && (
            <div className={s.sCards}>
              {slide.cards.map((c, i) => (
                <div key={i} className={s.sCard}>
                  {c.destaque && <b>{c.destaque}</b>}{c.texto}
                </div>
              ))}
            </div>
          )}
          {isCta && slide.cta && <div className={s.ctaBox}>{slide.cta}</div>}
        </div>
      )}

      <div className={s.sFooter}>
        <span className={s.sHandle}>@dr.lucasjudice</span>
        <span className={s.sTagline}>Advogado Patrimonialista</span>
      </div>
    </div>
  )
}

function Carousel({ slides, size = 380 }: { slides: SlideBlock[]; size?: number }) {
  const [i, setI] = useState(0)
  const scale = size / 1080
  const cur = Math.min(i, slides.length - 1)
  return (
    <div className={s.viewerWrap}>
      <div className={s.viewport} style={{ width: size, height: size }}>
        <div className={s.slideScaler} style={{ transform: `scale(${scale})` }}>
          <SlidePreview slide={slides[cur]} index={cur} total={slides.length} />
        </div>
      </div>
      {slides.length > 1 && (
        <>
          <div className={s.dots}>
            {slides.map((_, k) => (
              <span key={k} className={`${s.dot} ${k === cur ? s.dotActive : ''}`} />
            ))}
          </div>
          <div className={s.navBtns}>
            <button className={s.navBtn} disabled={cur === 0} onClick={() => setI(cur - 1)} aria-label="Anterior">
              <ChevronLeft size={16} />
            </button>
            <button
              className={s.navBtn}
              disabled={cur >= slides.length - 1}
              onClick={() => setI(cur + 1)}
              aria-label="Próximo"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ─────────────────── Card de sugestão ───────────────────
function SugestaoCard({ sug }: { sug: Sugestao }) {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: ['instagram-sugestoes'] })

  const patch = useMutation({
    mutationFn: (p: Parameters<typeof instagramApi.atualizar>[1]) => instagramApi.atualizar(sug.id, p),
    onSuccess: invalidate,
  })
  const excluir = useMutation({
    mutationFn: () => instagramApi.excluir(sug.id),
    onSuccess: invalidate,
  })
  const enviar = useMutation({
    mutationFn: () => instagramApi.enviarAssessoria(sug.id),
    onSuccess: invalidate,
  })

  return (
    <div className={s.card}>
      <Carousel slides={sug.slides} />
      <div className={s.cardBody}>
        <div className={s.cardTitle}>{sug.titulo}</div>
        <div className={s.metaRow}>
          <span className={s.chip}>{sug.formato === 'carrossel' ? 'Carrossel' : 'Estático'}</span>
          <span className={s.chip}>Capa {sug.tema_capa} · {CAPA_LABEL[sug.tema_capa]}</span>
          <span className={`${s.chip} ${s.chipFonte}`}>{FONTE_LABEL[sug.fonte_tipo] ?? sug.fonte_tipo}</span>
        </div>
        {sug.motivo_ia && <div className={s.motivo}>“{sug.motivo_ia}”</div>}
        {sug.legenda && <div className={s.legenda}>{sug.legenda}</div>}
        {sug.hashtags && <div className={s.hashtags}>{sug.hashtags}</div>}

        <div className={s.actions}>
          {sug.status === 'sugerido' && (
            <>
              <button className={`${s.btn} ${s.btnApprove}`} onClick={() => patch.mutate({ status: 'aprovado' })}>
                <Check size={14} /> Aprovar
              </button>
              <button className={`${s.btn} ${s.btnReject}`} onClick={() => patch.mutate({ status: 'rejeitado' })}>
                <X size={14} /> Rejeitar
              </button>
            </>
          )}

          {sug.status === 'aprovado' && (
            <>
              <label style={{ fontSize: 12, color: '#667' }}>Data:</label>
              <input
                type="date"
                className={s.dateInput}
                value={sug.data_sugerida ?? ''}
                onChange={(e) => patch.mutate({ data_sugerida: e.target.value || null })}
              />
              <button
                className={`${s.btn} ${s.btnSend}`}
                disabled={enviar.isPending}
                onClick={() => enviar.mutate()}
              >
                <Send size={14} /> {enviar.isPending ? 'Enviando…' : 'Enviar à assessoria'}
              </button>
              <button className={s.btn} onClick={() => patch.mutate({ status: 'sugerido' })}>
                <RotateCcw size={14} /> Voltar
              </button>
            </>
          )}

          {sug.status === 'rejeitado' && (
            <button className={s.btn} onClick={() => patch.mutate({ status: 'sugerido' })}>
              <RotateCcw size={14} /> Restaurar
            </button>
          )}

          <button
            className={s.btn}
            title="Excluir"
            onClick={() => { if (confirm('Excluir esta sugestão?')) excluir.mutate() }}
          >
            <Trash2 size={14} />
          </button>
        </div>

        {sug.enviado_assessoria_em && (
          <div className={s.sentBadge}>
            ✓ Enviado à assessoria em {new Date(sug.enviado_assessoria_em).toLocaleDateString('pt-BR')}
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────── Página ───────────────────
type Aba = 'sugeridas' | 'agenda' | 'rejeitadas'

export default function InstagramPage() {
  const qc = useQueryClient()
  const [aba, setAba] = useState<Aba>('sugeridas')
  const [quantidade, setQuantidade] = useState(3)

  const { data: sugestoes = [], isLoading } = useQuery({
    queryKey: ['instagram-sugestoes'],
    queryFn: () => instagramApi.listar(),
  })

  // Config de e-mail da assessoria (default moni@ vem do backend)
  const { data: config } = useQuery({
    queryKey: ['instagram-config'],
    queryFn: () => instagramApi.obterConfig(),
  })
  const [emailsEdit, setEmailsEdit] = useState<string | null>(null)
  const emailsValue = emailsEdit ?? config?.assessoria_emails ?? ''
  const salvarConfig = useMutation({
    mutationFn: (v: string) => instagramApi.salvarConfig(v),
    onSuccess: (c) => {
      qc.setQueryData(['instagram-config'], c)
      setEmailsEdit(null)
    },
  })

  const gerar = useMutation({
    mutationFn: () => instagramApi.gerar(quantidade),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['instagram-sugestoes'] })
      if (res.aviso) alert(res.aviso)
      setAba('sugeridas')
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      alert(msg ?? 'Falha ao gerar sugestões.')
    },
  })

  const grupos = useMemo(() => {
    const g: Record<Aba, Sugestao[]> = { sugeridas: [], agenda: [], rejeitadas: [] }
    for (const su of sugestoes) {
      if (su.status === 'sugerido') g.sugeridas.push(su)
      else if (su.status === 'rejeitado') g.rejeitadas.push(su)
      else g.agenda.push(su) // aprovado + publicado
    }
    return g
  }, [sugestoes])

  // Dica proativa de formato: analisa a sequência recente de posts agendados/publicados.
  const dicaFormato = useMemo(() => {
    const agendados = [...grupos.agenda]
      .filter((x) => x.data_sugerida)
      .sort((a, b) => (b.data_sugerida! < a.data_sugerida! ? -1 : 1))
    let streak = 0
    for (const p of agendados) {
      if (p.formato === 'carrossel') streak++
      else break
    }
    if (streak >= 3) {
      return `Já são ${streak} carrosséis seguidos na agenda. Que tal variar hoje com um Reels ou Stories para movimentar o alcance?`
    }
    return null
  }, [grupos.agenda])

  const lista = grupos[aba]
  const statusEsperado: StatusSugestao = aba === 'sugeridas' ? 'sugerido' : aba === 'rejeitadas' ? 'rejeitado' : 'aprovado'

  return (
    <div>
      <div className={page.pageHeader}>
        <h1 className={page.pageTitle}>
          <Camera size={22} style={{ verticalAlign: '-4px', marginRight: 8 }} />
          Instagram · @dr.lucasjudice
        </h1>
      </div>

      <div className={s.toolbar}>
        <p style={{ margin: 0, color: '#667', fontSize: 14 }} className={s.grow}>
          O Agente master varre a semana (publicações, andamentos, peças, teses, insights) e propõe posts no
          padrão visual do escritório. Valide, agende e envie para a assessoria.
        </p>
        <input
          type="number"
          min={1}
          max={8}
          className={s.qtyInput}
          value={quantidade}
          onChange={(e) => setQuantidade(Math.max(1, Math.min(8, Number(e.target.value) || 1)))}
        />
        <button className={s.genBtn} disabled={gerar.isPending} onClick={() => gerar.mutate()}>
          <Sparkles size={16} />
          {gerar.isPending ? 'Gerando sugestões…' : 'Gerar sugestões'}
        </button>
      </div>

      <div className={s.configRow}>
        <Mail size={16} color="#4a6a6a" />
        <span className={s.configLabel}>E-mails da assessoria:</span>
        <input
          className={s.configInput}
          placeholder="moni@pimentajudice.com.br"
          value={emailsValue}
          onChange={(e) => setEmailsEdit(e.target.value)}
        />
        <button
          className={s.configSave}
          disabled={salvarConfig.isPending || emailsEdit === null || emailsEdit === config?.assessoria_emails}
          onClick={() => salvarConfig.mutate(emailsValue)}
        >
          {salvarConfig.isPending ? 'Salvando…' : 'Salvar'}
        </button>
      </div>

      {dicaFormato && (
        <div className={s.dica}>
          <Lightbulb size={18} />
          <span>{dicaFormato}</span>
        </div>
      )}

      <div className={s.tabs}>
        {([
          ['sugeridas', 'Sugestões'],
          ['agenda', 'Aprovados / Agenda'],
          ['rejeitadas', 'Rejeitados'],
        ] as [Aba, string][]).map(([key, label]) => (
          <button
            key={key}
            className={`${s.tab} ${aba === key ? s.tabActive : ''}`}
            onClick={() => setAba(key)}
          >
            {label}
            <span className={s.tabCount}>{grupos[key].length}</span>
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className={page.empty}>Carregando…</p>
      ) : lista.length === 0 ? (
        <p className={page.empty}>
          {statusEsperado === 'sugerido'
            ? 'Nenhuma sugestão pendente. Clique em “Gerar sugestões”.'
            : 'Nada por aqui ainda.'}
        </p>
      ) : (
        <div className={s.grid}>
          {lista.map((su) => <SugestaoCard key={su.id} sug={su} />)}
        </div>
      )}
    </div>
  )
}
