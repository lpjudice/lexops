import { createRoot } from 'react-dom/client'
import * as htmlToImage from 'html-to-image'
import JSZip from 'jszip'
import { InstagramSlide } from '../components/InstagramSlide'
import type { SlideBlock, Sugestao } from '../api/instagram'
import api from '../api/client'

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** Renderiza cada slide (1080×1350) num container oculto e captura PNG. */
async function renderSlideBlobs(slides: SlideBlock[]): Promise<{ name: string; blob: Blob }[]> {
  const host = document.createElement('div')
  host.style.cssText = 'position:fixed;left:-10000px;top:0;width:1080px;height:1350px;z-index:-1;pointer-events:none;'
  document.body.appendChild(host)

  // Garante que a fonte Archivo esteja carregada antes de rasterizar
  try {
    await Promise.all([
      (document as unknown as { fonts: FontFaceSet }).fonts.load('900 100px Archivo'),
      (document as unknown as { fonts: FontFaceSet }).fonts.load('400 44px Archivo'),
    ])
    await (document as unknown as { fonts: FontFaceSet }).fonts.ready
  } catch { /* fontes já carregadas ou API indisponível */ }

  const out: { name: string; blob: Blob }[] = []
  try {
    for (let i = 0; i < slides.length; i++) {
      const mount = document.createElement('div')
      host.appendChild(mount)
      const root = createRoot(mount)
      root.render(<InstagramSlide slide={slides[i]} index={i} total={slides.length} />)
      await wait(120) // deixa o React pintar
      const node = mount.firstElementChild as HTMLElement
      const blob = await htmlToImage.toBlob(node, {
        width: 1080, height: 1350, pixelRatio: 1, cacheBust: true,
        style: { transform: 'none' },
      })
      if (blob) out.push({ name: `slide-${String(i + 1).padStart(2, '0')}.png`, blob })
      root.unmount()
      host.removeChild(mount)
    }
  } finally {
    document.body.removeChild(host)
  }
  return out
}

function copyText(sug: Sugestao): string {
  return `${sug.titulo}\n\n${sug.legenda || ''}\n\n${sug.hashtags || ''}`.trim() + '\n'
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const slugify = (t: string) =>
  (t || 'post').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 50) || 'post'

/** Baixa um ZIP com os PNGs dos slides + copy.txt. */
export async function baixarZip(sug: Sugestao): Promise<void> {
  const blobs = await renderSlideBlobs(sug.slides)
  const zip = new JSZip()
  for (const b of blobs) zip.file(b.name, b.blob)
  zip.file('copy.txt', copyText(sug))
  const content = await zip.generateAsync({ type: 'blob' })
  download(content, `${slugify(sug.titulo)}.zip`)
}

/** Renderiza os PNGs e envia para o Drive (backend faz o upload). Retorna o link da pasta. */
export async function salvarNoDrive(sug: Sugestao): Promise<string> {
  const blobs = await renderSlideBlobs(sug.slides)
  const fd = new FormData()
  for (const b of blobs) fd.append('files', b.blob, b.name)
  fd.append('files', new Blob([copyText(sug)], { type: 'text/plain' }), 'copy.txt')
  const r = await api.post<{ enviados: number; pasta: string }>(
    `/instagram/sugestoes/${sug.id}/drive`, fd, { timeout: 120000 },
  )
  return r.data.pasta
}
