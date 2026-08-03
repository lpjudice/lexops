import { useState } from 'react'
import type { ReactElement } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { IconeNome, SlideBlock } from '../api/instagram'
import s from '../pages/InstagramPage.module.css'

const HANDLE = '@dr.lucasjudice'
const TAGLINE = 'Advogado Patrimonialista'

// remove markdown/asteriscos que a IA às vezes injeta
const clean = (t?: string | null) => (t || '').replace(/[*#`]/g, '').replace(/\s+/g, ' ').trim()

// tamanho de fonte da CAPA conforme o comprimento do hook (evita estourar margem)
function coverSize(t: string): number {
  const n = t.length
  if (n <= 16) return 118
  if (n <= 24) return 104
  if (n <= 34) return 88
  if (n <= 44) return 74
  return 62
}

const ICONS: Record<IconeNome, ReactElement> = {
  usuario: <><path d="M4 20v-2a4 4 0 0 1 4-4h0a4 4 0 0 1 4 4v2" /><circle cx="8" cy="7" r="3" /></>,
  balanca: <><path d="M12 3v18M5 21h14M7 7h10M7 7l-3 6a3 3 0 0 0 6 0zM17 7l3 6a3 3 0 0 1-6 0z" /></>,
  check: <><path d="M8 12l3 3 5-6" /><circle cx="12" cy="12" r="9" /></>,
  escudo: <><path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" /></>,
  casa: <><path d="M4 11l8-7 8 7M6 10v10h12V10" /></>,
  familia: <><circle cx="8" cy="8" r="2.5" /><circle cx="16" cy="8" r="2.5" /><path d="M3 20v-1a4 4 0 0 1 4-4h2M15 15h2a4 4 0 0 1 4 4v1" /></>,
  documento: <><path d="M7 3h7l4 4v14H7zM14 3v4h4" /></>,
  acordo: <><path d="M8 12l3 3 4-4M4 10l4-4 4 3 4-3 4 4-6 6a2 2 0 0 1-3 0z" /></>,
  grafico: <><path d="M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6" /></>,
  engrenagem: <><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2" /></>,
  cofre: <><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="12" cy="12" r="3.5" /><path d="M12 8.5v0M12 12h3" /></>,
  arvore: <><path d="M12 21v-6M12 15L7 11M12 12l5-4" /><circle cx="12" cy="6" r="3" /><circle cx="6" cy="10" r="2.5" /><circle cx="18" cy="7" r="2.5" /></>,
}
const Ico = ({ name, cls }: { name: IconeNome; cls?: string }) => (
  <svg viewBox="0 0 24 24" className={cls}>{ICONS[name] ?? ICONS.check}</svg>
)

function Header({ n, total, avatar }: { n: number; total: number; avatar?: string }) {
  return (
    <div className={s.head}>
      {avatar ? <img className={s.avatarImg} src={avatar} alt="" /> : <span />}
      <span className={s.pagenum}>{n} / {total}</span>
    </div>
  )
}

export function InstagramSlide({ slide, index, total, avatar }: {
  slide: SlideBlock; index: number; total: number; avatar?: string
}) {
  const n = index + 1
  const layout = slide.layout || 'editorial'
  const titulo = clean(slide.titulo)
  const kicker = clean(slide.kicker)
  const frase = clean(slide.frase)

  // ---------- CAPAS ----------
  if (slide.tipo === 'capa' || layout.startsWith('capa_')) {
    const size = coverSize(titulo)
    if (layout === 'capa_offwhite') {
      return (
        <div className={`${s.slide} ${s.cover} ${s.coverOff}`}>
          {kicker && <span className={s.kickerC}>{kicker}</span>}
          <div className={s.ct} style={{ fontSize: size }}>{titulo}</div>
          <div className={s.coverArr}>Arraste →</div>
          <div className={s.coverHandle}>{HANDLE}</div>
        </div>
      )
    }
    if (layout === 'capa_split') {
      return (
        <div className={`${s.slide} ${s.cover} ${s.coverSplit}`}>
          <div className={s.top}><div className={s.over}>{kicker}</div></div>
          <div className={s.bot}>
            <div className={s.ct} style={{ fontSize: Math.min(size, 96) }}>{titulo}</div>
            <div className={s.coverArr}>Arraste →</div>
          </div>
          <div className={s.coverHandle}>{HANDLE}</div>
        </div>
      )
    }
    if (layout === 'capa_cream') {
      return (
        <div className={`${s.slide} ${s.cover} ${s.coverCream}`}>
          <div className={s.frame} />
          <div className={s.over4}>Pimenta Júdice</div>
          <div className={s.ct} style={{ fontSize: Math.min(size, 100) }}>{titulo}</div>
          <div className={s.divider} />
          <div className={s.handle4}>{HANDLE} · {TAGLINE}</div>
        </div>
      )
    }
    if (layout === 'capa_keyword') {
      const kw = clean(slide.destaque)
      const parts = kw ? titulo.split(new RegExp(`(${kw})`, 'i')) : [titulo]
      return (
        <div className={`${s.slide} ${s.cover} ${s.coverKw}`}>
          <div className={s.ct} style={{ fontSize: size }}>
            {parts.map((p, i) => kw && p.toLowerCase() === kw.toLowerCase()
              ? <span key={i} className={s.hl}>{p}</span> : <span key={i}>{p}</span>)}
          </div>
          <div className={s.coverArr}>Arraste →</div>
          <div className={s.coverHandle}>{HANDLE}</div>
        </div>
      )
    }
    // capa_teal (default)
    return (
      <div className={`${s.slide} ${s.cover} ${s.coverTeal}`}>
        <div className={s.topbar} />
        {kicker && <span className={s.coverTag}>{kicker}</span>}
        <div className={s.ct} style={{ fontSize: size }}>{titulo}</div>
        <div className={s.divider} />
        <div className={s.coverArr}>Arraste →</div>
        <div className={s.coverHandle}>{HANDLE}</div>
      </div>
    )
  }

  // ---------- FECHAMENTO ----------
  if (slide.tipo === 'fechamento' || layout === 'fechamento') {
    return (
      <div className={`${s.slide} ${s.closing}`}>
        <Header n={n} total={total} avatar={avatar} />
        <div className={s.ch}>{titulo}</div>
        {frase && <div className={s.cs}>{frase}</div>}
        {slide.cta && <div className={s.pill}>{clean(slide.cta)}</div>}
      </div>
    )
  }

  // ---------- MIOLO ----------
  return (
    <div className={`${s.slide} ${s.mid}`}>
      <Header n={n} total={total} avatar={avatar} />
      <div className={s.body}>
        {layout === 'numero' && slide.numero && <div className={s.bignum}>{clean(slide.numero)}</div>}
        {kicker && layout !== 'numero' && <span className={s.kicker}>{kicker}</span>}

        {layout === 'imagem' ? (
          <div className={s.cols}>
            <div className={s.cl}>
              <div className={`${s.h} ${s.sm}`}>{titulo}</div>
              {frase && <div className={s.sentence}>{frase}</div>}
            </div>
            <div className={s.imgblk}><Ico name={(slide.icone_destaque as IconeNome) || 'escudo'} cls={s.imgIcon} /></div>
          </div>
        ) : (
          <div className={`${s.h} ${layout === 'editorial' ? '' : s.sm}`}>{titulo}</div>
        )}

        {layout === 'editorial' && frase && (
          <div className={s.barwrap}><div className={s.bar} /><div className={s.sentence} style={{ marginTop: 0 }}>{frase}</div></div>
        )}
        {layout === 'numero' && frase && <div className={s.sentence}>{frase}</div>}
        {layout === 'citacao' && slide.citacao && (
          <div className={s.qcard}><div className={s.qt}>{clean(slide.citacao)}</div></div>
        )}
        {layout === 'icones' && (slide.icones?.length ?? 0) > 0 && (
          <div className={s.icons}>
            {slide.icones!.map((it, i) => (
              <div key={i} className={s.ico}>
                <div className={s.ic}><Ico name={it.icone} /></div>
                <div className={s.lb}>{clean(it.label)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className={s.arrow}>→</div>
    </div>
  )
}

export function SlideCarousel({ slides, width = 320, avatar }: {
  slides: SlideBlock[]; width?: number; avatar?: string
}) {
  const [i, setI] = useState(0)
  if (!slides?.length) return null
  const cur = Math.min(i, slides.length - 1)
  const scale = width / 1080
  const height = width * (1350 / 1080)
  return (
    <div className={s.viewerWrap}>
      <div className={s.viewport} style={{ width, height }}>
        <div className={s.slideScaler} style={{ transform: `scale(${scale})` }}>
          <InstagramSlide slide={slides[cur]} index={cur} total={slides.length} avatar={avatar} />
        </div>
      </div>
      {slides.length > 1 && (
        <>
          <div className={s.dots}>{slides.map((_, k) => <span key={k} className={`${s.dot} ${k === cur ? s.dotActive : ''}`} />)}</div>
          <div className={s.navBtns}>
            <button className={s.navBtn} disabled={cur === 0} onClick={() => setI(cur - 1)} aria-label="Anterior"><ChevronLeft size={16} /></button>
            <button className={s.navBtn} disabled={cur >= slides.length - 1} onClick={() => setI(cur + 1)} aria-label="Próximo"><ChevronRight size={16} /></button>
          </div>
        </>
      )}
    </div>
  )
}
