import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { instagramApi } from '../api/instagram'
import { InstagramSlide } from '../components/InstagramSlide'
import { baixarZip } from '../utils/instagramExport'
import s from './InstagramPage.module.css'

/** Página pública (sem login) para a assessoria abrir o post e publicar. */
export default function PostPublicoPage() {
  const { id = '' } = useParams()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['post-publico', id],
    queryFn: () => instagramApi.buscarPublico(id),
    retry: false,
  })
  const [copiado, setCopiado] = useState(false)
  const [zipBusy, setZipBusy] = useState(false)

  if (isLoading) return <div style={{ padding: 40, fontFamily: 'Archivo, sans-serif' }}>Carregando…</div>
  if (isError || !data) return <div style={{ padding: 40, fontFamily: 'Archivo, sans-serif' }}>Post não encontrado.</div>

  const copy = `${data.legenda}\n\n${data.hashtags}`.trim()
  const data_txt = data.data_sugerida ? new Date(data.data_sugerida + 'T12:00:00').toLocaleDateString('pt-BR') : null
  const onZip = async () => {
    setZipBusy(true)
    try { await baixarZip(data) } catch { alert('Falha ao gerar o ZIP.') } finally { setZipBusy(false) }
  }

  return (
    <div style={{ height: '100vh', overflowY: 'auto', WebkitOverflowScrolling: 'touch', background: '#eceae4', fontFamily: 'Archivo, system-ui, sans-serif', padding: '32px 16px 64px' }}>
      <div style={{ maxWidth: 760, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: '#3C8375', fontWeight: 700 }}>@dr.lucasjudice · Pimenta Júdice</div>
          <h1 style={{ fontSize: 26, color: '#123D34', margin: '6px 0 2px' }}>{data.titulo}</h1>
          <div style={{ fontSize: 14, color: '#63736E' }}>
            {data.formato === 'carrossel' ? 'Carrossel' : 'Post estático'}{data_txt ? ` · publicar em ${data_txt}` : ''}
          </div>
          <button
            onClick={onZip} disabled={zipBusy}
            style={{ marginTop: 14, display: 'inline-flex', alignItems: 'center', gap: 8, background: '#1C5A4E', color: '#fff', border: 'none', borderRadius: 999, padding: '12px 24px', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}
          >
            <Download size={16} /> {zipBusy ? 'Gerando imagens…' : 'Baixar imagens (ZIP)'}
          </button>
        </div>

        {/* Slides empilhados, no tamanho de publicação (escalados) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, alignItems: 'center' }}>
          {data.slides.map((slide, i) => {
            const width = Math.min(520, typeof window !== 'undefined' ? window.innerWidth - 48 : 520)
            const scale = width / 1080
            return (
              <div key={i} style={{ width, height: width * (1350 / 1080), overflow: 'hidden', borderRadius: 14, boxShadow: '0 6px 24px rgba(0,0,0,.14)' }}>
                <div className={s.slideScaler} style={{ transform: `scale(${scale})` }}>
                  <InstagramSlide slide={slide} index={i} total={data.slides.length} />
                </div>
              </div>
            )
          })}
        </div>

        {/* Copy */}
        <div style={{ background: '#fff', borderRadius: 14, padding: 20, marginTop: 28, boxShadow: '0 4px 16px rgba(0,0,0,.06)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <strong style={{ color: '#123D34' }}>Legenda</strong>
            <button
              onClick={() => { navigator.clipboard?.writeText(copy); setCopiado(true); setTimeout(() => setCopiado(false), 2000) }}
              style={{ background: '#1C5A4E', color: '#fff', border: 'none', borderRadius: 999, padding: '8px 18px', fontWeight: 700, cursor: 'pointer' }}
            >
              {copiado ? 'Copiado!' : 'Copiar legenda'}
            </button>
          </div>
          <div style={{ whiteSpace: 'pre-wrap', fontSize: 15, color: '#333', lineHeight: 1.6 }}>{data.legenda}</div>
          <div style={{ color: '#1C5A4E', fontWeight: 600, marginTop: 10 }}>{data.hashtags}</div>
        </div>
      </div>
    </div>
  )
}
