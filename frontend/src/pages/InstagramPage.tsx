import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Camera, Sparkles, Check, X, Send, Trash2, RotateCcw, Mail, Lightbulb, Wand2, Plus, CheckCircle2,
} from 'lucide-react'
import { instagramApi } from '../api/instagram'
import type { Sugestao } from '../api/instagram'
import { SlideCarousel } from '../components/InstagramSlide'
import page from './Page.module.css'
import s from './InstagramPage.module.css'

const CAPA_LABEL: Record<string, string> = { '1': 'Teal', '2': 'Off-white', '3': 'Split', '4': 'Cream', '5': 'Destaque' }
const FONTE_LABEL: Record<string, string> = {
  insight: 'Insight do site', publicacao: 'Publicação da semana', andamento: 'Andamento',
  peca: 'Peça produzida', tese: 'Tese IA', evergreen: 'Tema recorrente',
}

// ─────────────────── Card de sugestão ───────────────────
function SugestaoCard({ sug }: { sug: Sugestao }) {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: ['instagram-sugestoes'] })
  const [ajuste, setAjuste] = useState('')

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

  return (
    <div className={s.card}>
      <SlideCarousel slides={sug.slides} width={320} />
      <div className={s.cardBody}>
        <div className={s.cardTitle}>{sug.titulo}</div>
        <div className={s.metaRow}>
          <span className={s.chip}>{sug.formato === 'carrossel' ? 'Carrossel' : 'Estático'}</span>
          <span className={s.chip}>Capa {CAPA_LABEL[sug.tema_capa] ?? sug.tema_capa}</span>
          <span className={`${s.chip} ${s.chipFonte}`}>{FONTE_LABEL[sug.fonte_tipo] ?? sug.fonte_tipo}</span>
        </div>
        {sug.motivo_ia && <div className={s.motivo}>“{sug.motivo_ia}”</div>}

        {/* Ajuste pontual com IA */}
        <div className={s.ajusteBox}>
          <input
            placeholder="Ajuste pontual (ex.: troca a palavra X no slide 3)"
            value={ajuste}
            onChange={(e) => setAjuste(e.target.value)}
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
              <button className={`${s.btn} ${s.btnApprove}`} onClick={() => patch.mutate({ status: 'aprovado' })}><Check size={14} /> Aprovar</button>
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
              <button className={`${s.btn} ${s.btnPub}`} onClick={() => patch.mutate({ status: 'publicado' })}><CheckCircle2 size={14} /> Publicado</button>
              <button className={s.btn} onClick={() => patch.mutate({ status: 'sugerido' })}><RotateCcw size={14} /> Voltar</button>
            </>
          )}

          {sug.status === 'publicado' && (
            <button className={s.btn} onClick={() => patch.mutate({ status: 'aprovado' })}><RotateCcw size={14} /> Reabrir</button>
          )}

          {sug.status === 'rejeitado' && (
            <button className={s.btn} onClick={() => patch.mutate({ status: 'sugerido' })}><RotateCcw size={14} /> Restaurar</button>
          )}

          <button className={s.btn} title="Excluir" onClick={() => { if (confirm('Excluir esta sugestão?')) excluir.mutate() }}><Trash2 size={14} /></button>
        </div>

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
  const emails = useMemo(
    () => (config?.assessoria_emails ?? '').split(',').map((e) => e.trim()).filter(Boolean),
    [config],
  )
  const [novo, setNovo] = useState('')
  const salvar = useMutation({
    mutationFn: (lista: string[]) => instagramApi.salvarConfig(lista.join(', ')),
    onSuccess: (c) => qc.setQueryData(['instagram-config'], c),
  })

  const add = () => {
    const e = novo.trim()
    if (!e || emails.includes(e)) { setNovo(''); return }
    salvar.mutate([...emails, e]); setNovo('')
  }
  const remove = (e: string) => salvar.mutate(emails.filter((x) => x !== e))

  return (
    <div className={s.configRow}>
      <Mail size={16} color="#4a6a6a" />
      <span className={s.configLabel}>Assessoria:</span>
      <div className={s.emailChips}>
        {emails.map((e) => (
          <span key={e} className={s.emailChip}>{e}<button title="Remover" onClick={() => remove(e)}>×</button></span>
        ))}
      </div>
      <div className={s.addEmail}>
        <input
          type="email" placeholder="adicionar e-mail" value={novo}
          onChange={(e) => setNovo(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') add() }}
        />
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

  const { data: sugestoes = [], isLoading } = useQuery({
    queryKey: ['instagram-sugestoes'],
    queryFn: () => instagramApi.listar(),
  })

  const gerar = useMutation({
    mutationFn: () => instagramApi.gerar(quantidade),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['instagram-sugestoes'] })
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

  const dicaFormato = useMemo(() => {
    const agendados = [...grupos.agenda].filter((x) => x.data_sugerida)
      .sort((a, b) => (b.data_sugerida! < a.data_sugerida! ? -1 : 1))
    let streak = 0
    for (const p of agendados) { if (p.formato === 'carrossel') streak++; else break }
    return streak >= 3
      ? `Já são ${streak} carrosséis seguidos na agenda. Que tal variar hoje com um Reels ou Stories para movimentar o alcance?`
      : null
  }, [grupos.agenda])

  const lista = grupos[aba]

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
          O Agente master varre a semana (insights, publicações, andamentos, peças, teses) e propõe posts no
          padrão visual do escritório. Valide, ajuste, agende e envie para a assessoria.
        </p>
        <input type="number" min={1} max={8} className={s.qtyInput} value={quantidade}
          onChange={(e) => setQuantidade(Math.max(1, Math.min(8, Number(e.target.value) || 1)))} />
        <button className={s.genBtn} disabled={gerar.isPending} onClick={() => gerar.mutate()}>
          <Sparkles size={16} />{gerar.isPending ? 'Gerando sugestões…' : 'Gerar sugestões'}
        </button>
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
