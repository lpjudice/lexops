import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Camera, Sparkles, Check, X, Send, Trash2, RotateCcw, Mail, Lightbulb, Wand2, Plus, CheckCircle2,
  Download, HardDrive, ChevronDown, ChevronUp, FolderOpen, History, DollarSign, Gift, Link2, FileText, Upload, Film,
} from 'lucide-react'
import { instagramApi, brindeUrl } from '../api/instagram'
import type { FonteColeta, Sugestao } from '../api/instagram'
import { SlideCarousel } from '../components/InstagramSlide'
import { baixarZip, salvarNoDrive } from '../utils/instagramExport'
import page from './Page.module.css'
import s from './InstagramPage.module.css'

const CAPA_LABEL: Record<string, string> = { '1': 'Teal', '2': 'Off-white', '3': 'Split', '4': 'Cream', '5': 'Destaque' }
const FONTE_LABEL: Record<string, string> = {
  insight: 'Insight do site', publicacao: 'Publicação da semana', andamento: 'Andamento',
  peca: 'Peça produzida', tese: 'Tese IA', evergreen: 'Tema recorrente',
}
const FONTES: { key: FonteColeta; label: string }[] = [
  { key: 'insights', label: 'Insights do site' }, { key: 'publicacoes', label: 'Publicações' },
  { key: 'andamentos', label: 'Andamentos' }, { key: 'pecas', label: 'Peças' },
  { key: 'teses', label: 'Teses' }, { key: 'evergreen', label: 'Evergreen' },
]

function mesKey(su: Sugestao): string | null {
  const d = su.aprovado_em ?? su.data_sugerida
  return d ? d.slice(0, 7) : null // YYYY-MM
}
function mesLabel(k: string): string {
  const [y, m] = k.split('-')
  return `${m}/${y}`
}

// ─────────────────── Brinde / isca (lead magnet) ───────────────────
const FORMATOS_BRINDE: { key: 'one_pager' | 'slides' | 'html'; label: string }[] = [
  { key: 'one_pager', label: 'One-pager' }, { key: 'slides', label: 'Guia (blocos)' }, { key: 'html', label: 'Material completo' },
]

function BrindeDownloads({ id, estilo, label }: { id: string; estilo: 'instagram' | 'site'; label: string }) {
  const [copiado, setCopiado] = useState(false)
  return (
    <div className={s.brindeRow}>
      <span className={s.brindeTitulo}>{label}:</span>
      <a className={s.driveLink} href={brindeUrl(id, 'view', estilo)} target="_blank" rel="noreferrer"><FileText size={13} /> Ver</a>
      <a className={s.driveLink} href={brindeUrl(id, 'pdf', estilo)} target="_blank" rel="noreferrer"><Download size={13} /> PDF</a>
      <a className={s.driveLink} href={brindeUrl(id, 'html', estilo)} target="_blank" rel="noreferrer"><Download size={13} /> HTML</a>
      <button className={s.driveLink} onClick={() => { navigator.clipboard?.writeText(brindeUrl(id, 'view', estilo)); setCopiado(true); setTimeout(() => setCopiado(false), 2000) }}>
        <Link2 size={13} /> {copiado ? 'Copiado!' : 'Link'}
      </button>
    </div>
  )
}

function BrindeSection({ sug }: { sug: Sugestao }) {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: ['instagram-sugestoes'] })
  const [kw, setKw] = useState(sug.brinde_palavra_chave ?? '')
  const [formato, setFormato] = useState<'one_pager' | 'slides' | 'html'>((sug.brinde_formato as never) || 'one_pager')
  const fileRef = useRef<HTMLInputElement>(null)

  const salvarKw = useMutation({ mutationFn: () => instagramApi.brindeKeyword(sug.id, kw.trim()), onSuccess: invalidate })
  const gerar = useMutation({
    mutationFn: (estilo: 'instagram' | 'site') => instagramApi.brindeGerar(sug.id, formato, estilo),
    onSuccess: invalidate,
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Falha ao gerar brinde.'),
  })
  const upload = useMutation({
    mutationFn: (f: File) => instagramApi.brindeUpload(sug.id, f),
    onSuccess: invalidate,
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Falha no upload.'),
  })
  const gerandoSite = gerar.isPending && gerar.variables === 'site'
  const gerandoIg = gerar.isPending && gerar.variables === 'instagram'

  return (
    <div className={s.brindeBox}>
      <div className={s.brindeHead}><Gift size={15} /> Brinde / isca</div>
      <div className={s.brindeRow}>
        <input className={s.brindeKw} placeholder="Palavra-chave (ex.: HOLDING)" value={kw}
          onChange={(e) => setKw(e.target.value.toUpperCase())} onBlur={() => { if ((kw.trim()) !== (sug.brinde_palavra_chave ?? '')) salvarKw.mutate() }} />
        <span className={s.brindeHint}>a pessoa comenta e recebe o material</span>
      </div>
      <div className={s.brindeRow}>
        <select className={s.dateInput} value={formato} onChange={(e) => setFormato(e.target.value as never)}>
          {FORMATOS_BRINDE.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
        </select>
        <button className={s.btn} disabled={gerar.isPending} onClick={() => gerar.mutate('instagram')}>
          <Sparkles size={14} /> {gerandoIg ? 'Gerando…' : sug.tem_brinde ? 'Regerar brinde' : 'Gerar brinde (teal)'}
        </button>
        <button className={s.btn} disabled={gerar.isPending} onClick={() => gerar.mutate('site')} title="Identidade oficial do site (bege/preto), estilo landing page">
          <Sparkles size={14} /> {gerandoSite ? 'Gerando…' : 'Versão site'}
        </button>
        <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f) }} />
        <button className={s.btn} disabled={upload.isPending} onClick={() => fileRef.current?.click()}>
          <Upload size={14} /> {upload.isPending ? 'Subindo…' : 'Subir PDF'}
        </button>
      </div>
      {sug.tem_brinde && <BrindeDownloads id={sug.id} estilo="instagram" label="Brinde (Instagram)" />}
      {sug.tem_brinde_site && <BrindeDownloads id={sug.id} estilo="site" label="Versão site" />}
      {sug.brinde_drive_link && (
        <a className={s.driveLink} href={sug.brinde_drive_link} target="_blank" rel="noreferrer"><FolderOpen size={13} /> PDF no Drive</a>
      )}
    </div>
  )
}

// ─────────────────── Vídeo → copy ───────────────────
function VideoSection({ sug }: { sug: Sugestao }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const up = useMutation({
    mutationFn: (f: File) => instagramApi.videoCopy(sug.id, f),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['instagram-sugestoes'] }),
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Falha ao processar o vídeo.'),
  })
  return (
    <div className={s.videoBox}>
      <div className={s.videoHead}><Film size={15} /> Vídeo → copy</div>
      <input ref={fileRef} type="file" accept="video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) up.mutate(f) }} />
      <div className={s.brindeRow}>
        <button className={s.btn} disabled={up.isPending} onClick={() => fileRef.current?.click()}>
          <Upload size={14} /> {up.isPending ? 'Interpretando vídeo…' : 'Subir vídeo (Gemini gera a copy)'}
        </button>
        {sug.video_drive_link && <a className={s.driveLink} href={sug.video_drive_link} target="_blank" rel="noreferrer"><FolderOpen size={13} /> Vídeo no Drive</a>}
      </div>
      {up.isPending && <span className={s.brindeHint}>pode levar até 1 min (o Gemini processa e assiste o vídeo).</span>}
    </div>
  )
}

// ─────────────────── Card de sugestão ───────────────────
function SugestaoCard({ sug }: { sug: Sugestao }) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['instagram-sugestoes'] })
    qc.invalidateQueries({ queryKey: ['instagram-custos'] })
  }
  const [ajuste, setAjuste] = useState('')
  const [zipBusy, setZipBusy] = useState(false)
  const [driveBusy, setDriveBusy] = useState(false)
  const [aberto, setAberto] = useState(sug.status !== 'publicado')
  const [verHist, setVerHist] = useState(false)
  const alterado = (sug.ajustes_count ?? 0) > 0

  const patch = useMutation({
    mutationFn: (p: Parameters<typeof instagramApi.atualizar>[1]) => instagramApi.atualizar(sug.id, p),
    onSuccess: invalidate,
  })
  const excluir = useMutation({ mutationFn: () => instagramApi.excluir(sug.id), onSuccess: invalidate })
  const enviar = useMutation({ mutationFn: () => instagramApi.enviarAssessoria(sug.id), onSuccess: invalidate })
  const ajustar = useMutation({
    mutationFn: () => instagramApi.ajustar(sug.id, ajuste.trim()),
    onSuccess: () => { setAjuste(''); invalidate() },
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Falha ao ajustar.'),
  })

  const aprovar = async () => {
    const upd = await patch.mutateAsync({ status: 'aprovado' })
    // Salva no Drive automaticamente em background (não bloqueia a aprovação)
    if (!upd.drive_link) salvarNoDrive(upd).then(() => invalidate()).catch(() => {})
  }
  const onZip = async () => {
    setZipBusy(true)
    try { await baixarZip(sug) } catch { alert('Falha ao gerar o ZIP.') } finally { setZipBusy(false) }
  }
  const onDrive = async () => {
    setDriveBusy(true)
    try {
      const pasta = await salvarNoDrive(sug); invalidate()
      if (confirm('Salvo no Drive! Abrir a pasta?')) window.open(pasta, '_blank')
    } catch (e) {
      alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Falha ao salvar no Drive.')
    } finally { setDriveBusy(false) }
  }

  // Barra compacta (colapsado)
  if (!aberto) {
    return (
      <div className={s.card}>
        <div className={s.compact}>
          <button className={s.compactExpand} onClick={() => setAberto(true)} title="Expandir"><ChevronDown size={18} /></button>
          <div className={s.compactBody}>
            <div className={s.cardTitle}>{sug.titulo}</div>
            <div className={s.metaRow}>
              {sug.status === 'publicado' && <span className={s.pubBadge}>✓ Publicado</span>}
              {sug.data_sugerida && <span className={s.chip}>{new Date(sug.data_sugerida + 'T12:00:00').toLocaleDateString('pt-BR')}</span>}
              {sug.drive_link && <a className={s.driveLink} href={sug.drive_link} target="_blank" rel="noreferrer"><FolderOpen size={13} /> Drive</a>}
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`${s.card} ${alterado ? s.cardChanged : ''}`}>
      <SlideCarousel slides={sug.slides} width={320} />
      <div className={s.cardBody}>
        <div className={s.cardTitleRow}>
          <div className={s.cardTitle}>{sug.titulo}</div>
          {(sug.status === 'aprovado' || sug.status === 'publicado') && (
            <button className={s.compactExpand} onClick={() => setAberto(false)} title="Colapsar"><ChevronUp size={18} /></button>
          )}
        </div>
        <div className={s.metaRow}>
          <span className={s.chip}>{sug.formato === 'carrossel' ? 'Carrossel' : 'Estático'}</span>
          <span className={s.chip}>Capa {CAPA_LABEL[sug.tema_capa] ?? sug.tema_capa}</span>
          <span className={`${s.chip} ${s.chipFonte}`}>{FONTE_LABEL[sug.fonte_tipo] ?? sug.fonte_tipo}</span>
          <span className={s.chipCusto}><DollarSign size={11} />{(sug.custo_usd ?? 0).toFixed(3)}</span>
          {alterado && (
            <button className={s.chipAlterado} onClick={() => setVerHist((v) => !v)} title="Ver histórico de alterações">
              <History size={12} /> {sug.ajustes_count} alteração{sug.ajustes_count > 1 ? 'ões' : ''}
            </button>
          )}
          {sug.drive_link && <a className={s.driveLink} href={sug.drive_link} target="_blank" rel="noreferrer"><FolderOpen size={13} /> Drive</a>}
        </div>
        {verHist && alterado && (
          <div className={s.histBox}>
            {sug.ajustes.map((a, i) => (
              <div key={i} className={s.histItem}>
                <span className={s.histDate}>{new Date(a.quando).toLocaleString('pt-BR')}</span>
                <span>{a.instrucao}</span>
              </div>
            ))}
          </div>
        )}
        {sug.motivo_ia && <div className={s.motivo}>“{sug.motivo_ia}”</div>}

        <div className={s.ajusteBox}>
          <input
            placeholder="Ajuste pontual (ex.: troca a palavra X no slide 3)"
            value={ajuste} onChange={(e) => setAjuste(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && ajuste.trim()) ajustar.mutate() }}
          />
          <button className={s.btn} disabled={!ajuste.trim() || ajustar.isPending} onClick={() => ajustar.mutate()}>
            <Wand2 size={14} /> {ajustar.isPending ? 'Ajustando…' : 'Ajustar'}
          </button>
        </div>

        {sug.legenda && <div className={s.legenda}>{sug.legenda}</div>}
        {sug.hashtags && <div className={s.hashtags}>{sug.hashtags}</div>}

        <div className={s.actions}>
          {sug.status === 'sugerido' && (
            <>
              <button className={`${s.btn} ${s.btnApprove}`} onClick={aprovar}><Check size={14} /> Aprovar</button>
              <button className={`${s.btn} ${s.btnReject}`} onClick={() => patch.mutate({ status: 'rejeitado' })}><X size={14} /> Rejeitar</button>
            </>
          )}
          {sug.status === 'aprovado' && (
            <>
              <label style={{ fontSize: 12, color: '#667' }}>Data:</label>
              <input type="date" className={s.dateInput} value={sug.data_sugerida ?? ''} onChange={(e) => patch.mutate({ data_sugerida: e.target.value || null })} />
              <button className={`${s.btn} ${s.btnSend}`} disabled={enviar.isPending} onClick={() => enviar.mutate()}>
                <Send size={14} /> {enviar.isPending ? 'Enviando…' : 'Enviar à assessoria'}
              </button>
              <button className={`${s.btn} ${s.btnPub}`} onClick={() => patch.mutate({ status: 'publicado' })}><CheckCircle2 size={14} /> Marcar publicado</button>
              <button className={s.btn} onClick={() => patch.mutate({ status: 'sugerido' })}><RotateCcw size={14} /> Voltar</button>
            </>
          )}
          {sug.status === 'publicado' && (
            <button className={s.btn} onClick={() => patch.mutate({ status: 'aprovado' })}><RotateCcw size={14} /> Reabrir</button>
          )}
          {sug.status === 'rejeitado' && (
            <button className={s.btn} onClick={() => patch.mutate({ status: 'sugerido' })}><RotateCcw size={14} /> Restaurar</button>
          )}
          <button className={s.btn} title="Baixar ZIP (PNGs + copy)" disabled={zipBusy} onClick={onZip}><Download size={14} /> {zipBusy ? 'Gerando…' : 'ZIP'}</button>
          <button className={s.btn} title="Salvar no Drive" disabled={driveBusy} onClick={onDrive}><HardDrive size={14} /> {driveBusy ? 'Salvando…' : 'Drive'}</button>
          <button className={s.btn} title="Excluir" onClick={() => { if (confirm('Excluir esta sugestão?')) excluir.mutate() }}><Trash2 size={14} /></button>
        </div>

        <BrindeSection sug={sug} />
        <VideoSection sug={sug} />

        {sug.status === 'publicado' && <div className={s.pubBadge}>✓ Publicado</div>}
        {sug.enviado_assessoria_em && sug.status !== 'publicado' && (
          <div className={s.sentBadge}>✓ Enviado à assessoria em {new Date(sug.enviado_assessoria_em).toLocaleDateString('pt-BR')}</div>
        )}
      </div>
    </div>
  )
}

// ─────────────────── Config de e-mails (multi + botão +) ───────────────────
function EmailsConfig() {
  const qc = useQueryClient()
  const { data: config } = useQuery({ queryKey: ['instagram-config'], queryFn: () => instagramApi.obterConfig() })
  const emails = useMemo(() => (config?.assessoria_emails ?? '').split(',').map((e) => e.trim()).filter(Boolean), [config])
  const [novo, setNovo] = useState('')
  const salvar = useMutation({
    mutationFn: (lista: string[]) => instagramApi.salvarConfig(lista.join(', ')),
    onSuccess: (c) => qc.setQueryData(['instagram-config'], c),
  })
  const add = () => { const e = novo.trim(); if (!e || emails.includes(e)) { setNovo(''); return } salvar.mutate([...emails, e]); setNovo('') }
  const remove = (e: string) => salvar.mutate(emails.filter((x) => x !== e))

  return (
    <div className={s.configRow}>
      <Mail size={16} color="#4a6a6a" />
      <span className={s.configLabel}>Assessoria:</span>
      <div className={s.emailChips}>
        {emails.map((e) => <span key={e} className={s.emailChip}>{e}<button title="Remover" onClick={() => remove(e)}>×</button></span>)}
      </div>
      <div className={s.addEmail}>
        <input type="email" placeholder="adicionar e-mail" value={novo} onChange={(e) => setNovo(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') add() }} />
        <button className={s.iconBtn} title="Adicionar" onClick={add}><Plus size={16} /></button>
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
  const [fontes, setFontes] = useState<Record<FonteColeta, boolean>>({
    insights: true, publicacoes: true, andamentos: true, pecas: true, teses: true, evergreen: true,
  })
  const [mesFiltro, setMesFiltro] = useState('todos')

  const { data: sugestoes = [], isLoading } = useQuery({
    queryKey: ['instagram-sugestoes'], queryFn: () => instagramApi.listar(),
  })
  const { data: custos } = useQuery({ queryKey: ['instagram-custos'], queryFn: () => instagramApi.custos() })

  const gerar = useMutation({
    mutationFn: () => {
      const selecionadas = (Object.keys(fontes) as FonteColeta[]).filter((k) => fontes[k])
      return instagramApi.gerar(quantidade, undefined, selecionadas)
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['instagram-sugestoes'] })
      qc.invalidateQueries({ queryKey: ['instagram-custos'] })
      if (res.aviso) alert(res.aviso)
      setAba('sugeridas')
    },
    onError: (e: unknown) => alert((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Falha ao gerar sugestões.'),
  })

  const grupos = useMemo(() => {
    const g: Record<Aba, Sugestao[]> = { sugeridas: [], agenda: [], rejeitadas: [] }
    for (const su of sugestoes) {
      if (su.status === 'sugerido') g.sugeridas.push(su)
      else if (su.status === 'rejeitado') g.rejeitadas.push(su)
      else g.agenda.push(su)
    }
    return g
  }, [sugestoes])

  const meses = useMemo(() => {
    const set = new Set<string>()
    for (const su of grupos.agenda) { const k = mesKey(su); if (k) set.add(k) }
    return [...set].sort().reverse()
  }, [grupos.agenda])

  const dicaFormato = useMemo(() => {
    const agendados = [...grupos.agenda].filter((x) => x.data_sugerida).sort((a, b) => (b.data_sugerida! < a.data_sugerida! ? -1 : 1))
    let streak = 0
    for (const p of agendados) { if (p.formato === 'carrossel') streak++; else break }
    return streak >= 3 ? `Já são ${streak} carrosséis seguidos na agenda. Que tal variar hoje com um Reels ou Stories?` : null
  }, [grupos.agenda])

  let lista = grupos[aba]
  if (aba === 'agenda' && mesFiltro !== 'todos') lista = lista.filter((su) => mesKey(su) === mesFiltro)

  return (
    <div>
      <div className={page.pageHeader}>
        <h1 className={page.pageTitle}><Camera size={22} style={{ verticalAlign: '-4px', marginRight: 8 }} />Instagram · @dr.lucasjudice</h1>
        {custos && (
          <div className={s.gastoBox} title="Gasto de IA (geração + ajustes)">
            <span className={s.gastoMes}>Gasto do mês: <b>${custos.mes_atual_usd.toFixed(2)}</b></span>
            <span className={s.gastoTotal}>Total: ${custos.total_usd.toFixed(2)}</span>
          </div>
        )}
      </div>

      <div className={s.toolbar}>
        <p style={{ margin: 0, color: '#667', fontSize: 14 }} className={s.grow}>
          O Agente master varre a semana e propõe posts no padrão do escritório. Valide, ajuste, agende e envie para a assessoria.
        </p>
        <input type="number" min={1} max={8} className={s.qtyInput} value={quantidade}
          onChange={(e) => setQuantidade(Math.max(1, Math.min(8, Number(e.target.value) || 1)))} />
        <button className={s.genBtn} disabled={gerar.isPending} onClick={() => gerar.mutate()}>
          <Sparkles size={16} />{gerar.isPending ? 'Gerando sugestões…' : 'Gerar sugestões'}
        </button>
      </div>

      <div className={s.fontesRow}>
        <span className={s.configLabel}>Fontes desta geração:</span>
        {FONTES.map(({ key, label }) => (
          <label key={key} className={s.fonteChk}>
            <input type="checkbox" checked={fontes[key]} onChange={(e) => setFontes({ ...fontes, [key]: e.target.checked })} />
            {label}
          </label>
        ))}
      </div>

      <EmailsConfig />

      {dicaFormato && <div className={s.dica}><Lightbulb size={18} /><span>{dicaFormato}</span></div>}

      <div className={s.tabs}>
        {([['sugeridas', 'Sugestões'], ['agenda', 'Aprovados / Agenda'], ['rejeitadas', 'Rejeitados']] as [Aba, string][]).map(([key, label]) => (
          <button key={key} className={`${s.tab} ${aba === key ? s.tabActive : ''}`} onClick={() => setAba(key)}>
            {label}<span className={s.tabCount}>{grupos[key].length}</span>
          </button>
        ))}
      </div>

      {aba === 'agenda' && meses.length > 0 && (
        <div className={s.filterRow}>
          <span className={s.configLabel}>Mês de aprovação:</span>
          <select className={s.dateInput} value={mesFiltro} onChange={(e) => setMesFiltro(e.target.value)}>
            <option value="todos">Todos</option>
            {meses.map((m) => <option key={m} value={m}>{mesLabel(m)}</option>)}
          </select>
        </div>
      )}

      {isLoading ? (
        <p className={page.empty}>Carregando…</p>
      ) : lista.length === 0 ? (
        <p className={page.empty}>{aba === 'sugeridas' ? 'Nenhuma sugestão pendente. Clique em “Gerar sugestões”.' : 'Nada por aqui ainda.'}</p>
      ) : (
        <div className={s.grid}>{lista.map((su) => <SugestaoCard key={su.id} sug={su} />)}</div>
      )}
    </div>
  )
}
