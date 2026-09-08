import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowLeft, Download, Eye, EyeOff, FolderOpen, Globe, Link2, Sparkles } from 'lucide-react'
import { instagramApi, brindeUrl } from '../api/instagram'
import type { Brinde } from '../api/instagram'
import page from './Page.module.css'
import s from './InstagramBrindesPage.module.css'

const FORMATO_LABEL: Record<string, string> = {
  one_pager: 'One-pager', slides: 'Guia em blocos', html: 'Material completo', manual: 'PDF próprio',
}

function fmtData(iso?: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function BrindeRow({ brinde, onChange }: { brinde: Brinde; onChange: () => void }) {
  const [copiado, setCopiado] = useState(false)
  const publicar = useMutation({ mutationFn: () => instagramApi.publicarBrinde(brinde.id), onSuccess: onChange })
  const ocultar = useMutation({ mutationFn: () => instagramApi.ocultarBrinde(brinde.id), onSuccess: onChange })
  const semHtml = brinde.formato === 'manual'

  return (
    <div className={`${s.linha} ${brinde.publicado_no_site ? s.linhaAtiva : ''}`}>
      <div className={s.linhaInfo}>
        <div className={s.linhaTopo}>
          <span className={s.formatoTag}>{FORMATO_LABEL[brinde.formato] ?? brinde.formato}</span>
          {brinde.publicado_no_site && <span className={s.tagAtivo}><Globe size={12} /> No site desde {fmtData(brinde.publicado_em)}</span>}
        </div>
        <div className={s.linhaTitulo}>{brinde.titulo}</div>
        <div className={s.linhaMeta}>
          {brinde.sugestao_titulo ? <>post: <b>{brinde.sugestao_titulo}</b> · </> : null}
          gerado em {fmtData(brinde.criado_em)}
        </div>
      </div>
      <div className={s.linhaAcoes}>
        {!semHtml && <a className={s.acao} href={brindeUrl(brinde.id, 'view')} target="_blank" rel="noreferrer"><Eye size={13} /> Ver</a>}
        <a className={s.acao} href={brindeUrl(brinde.id, 'pdf')} target="_blank" rel="noreferrer"><Download size={13} /> PDF</a>
        <button className={s.acao} onClick={() => { navigator.clipboard?.writeText(brindeUrl(brinde.id, 'view')); setCopiado(true); setTimeout(() => setCopiado(false), 2000) }}>
          <Link2 size={13} /> {copiado ? 'Copiado!' : 'Link'}
        </button>
        {brinde.drive_link && <a className={s.acao} href={brinde.drive_link} target="_blank" rel="noreferrer"><FolderOpen size={13} /> Drive</a>}
        {brinde.publicado_no_site ? (
          <button className={s.acao} disabled={ocultar.isPending} onClick={() => ocultar.mutate()}><EyeOff size={13} /> Ocultar do site</button>
        ) : (
          <button className={`${s.acao} ${s.acaoPublicar}`} disabled={publicar.isPending} onClick={() => publicar.mutate()}><Globe size={13} /> Publicar no site</button>
        )}
      </div>
    </div>
  )
}

export default function InstagramBrindesPage() {
  const qc = useQueryClient()
  const [apenasPublicados, setApenasPublicados] = useState(false)
  const { data: brindes = [], isLoading } = useQuery({
    queryKey: ['instagram-brindes-central', apenasPublicados],
    queryFn: () => instagramApi.centralDeBrindes(apenasPublicados),
  })
  const { data: exemplos = [] } = useQuery({ queryKey: ['instagram-brindes-exemplos'], queryFn: () => instagramApi.exemplosBrinde() })
  const gerarExemplos = useMutation({
    mutationFn: () => instagramApi.gerarExemplosBrinde(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['instagram-brindes-exemplos'] }),
    onError: () => alert('Falha ao gerar os exemplos.'),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['instagram-brindes-central'] })
  const publicados = useMemo(() => brindes.filter((b) => b.publicado_no_site).length, [brindes])

  return (
    <div>
      <div className={page.pageHeader}>
        <h1 className={page.pageTitle}>
          <Link to="/instagram" className={s.voltar}><ArrowLeft size={18} /></Link>
          Central de materiais (brindes)
        </h1>
      </div>
      <p className={s.subtitulo}>
        Todos os brindes já gerados, de todos os posts. {publicados} {publicados === 1 ? 'está' : 'estão'} publicado{publicados === 1 ? '' : 's'} no site agora.
      </p>

      <div className={s.exemplos}>
        <div className={s.exemplosHead}>
          <span>Exemplos de referência (1 por formato, pra entender a diferença)</span>
          <button className={s.acao} disabled={gerarExemplos.isPending} onClick={() => gerarExemplos.mutate()}>
            <Sparkles size={13} /> {gerarExemplos.isPending ? 'Gerando…' : exemplos.length ? 'Regerar exemplos' : 'Gerar exemplos'}
          </button>
        </div>
        {exemplos.length > 0 && (
          <div className={s.exemplosLista}>
            {exemplos.map((ex) => (
              <div key={ex.id} className={s.exemploItem}>
                <span className={s.formatoTag}>{FORMATO_LABEL[ex.formato] ?? ex.formato}</span>
                <a className={s.acao} href={brindeUrl(ex.id, 'view')} target="_blank" rel="noreferrer"><Eye size={13} /> Ver</a>
                <a className={s.acao} href={brindeUrl(ex.id, 'pdf')} target="_blank" rel="noreferrer"><Download size={13} /> PDF</a>
              </div>
            ))}
          </div>
        )}
      </div>

      <label className={s.filtro}>
        <input type="checkbox" checked={apenasPublicados} onChange={(e) => setApenasPublicados(e.target.checked)} />
        Mostrar só os publicados no site
      </label>

      {isLoading ? (
        <p className={page.empty}>Carregando…</p>
      ) : brindes.length === 0 ? (
        <p className={page.empty}>Nenhum brinde gerado ainda.</p>
      ) : (
        <div className={s.lista}>
          {brindes.map((b) => <BrindeRow key={b.id} brinde={b} onChange={invalidate} />)}
        </div>
      )}
    </div>
  )
}
