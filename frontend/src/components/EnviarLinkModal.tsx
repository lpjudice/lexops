import { useEffect, useState } from 'react'
import { cadastroLinksApi } from '../api/clientes'
import cs from './EnviarLinkModal.module.css'

interface Props {
  cliente?: { id: string; nome: string; email?: string } // ausente => link genérico
  onClose: () => void
}

function waLink(numero: string, texto: string) {
  let d = numero.replace(/\D/g, '')
  if (!d) return ''
  if (d.length <= 11) d = '55' + d // assume Brasil se sem código do país
  return `https://wa.me/${d}?text=${encodeURIComponent(texto)}`
}

export default function EnviarLinkModal({ cliente, onClose }: Props) {
  const clienteId = cliente?.id ?? null
  const [url, setUrl] = useState<string>('')
  const [erroLink, setErroLink] = useState(false)

  const [emailDest, setEmailDest] = useState(cliente?.email ?? '')
  const [copiaPraMim, setCopiaPraMim] = useState(true)
  const [emailMsg, setEmailMsg] = useState<string | null>(null)
  const [emailEnviando, setEmailEnviando] = useState(false)

  const [waNumero, setWaNumero] = useState('')
  const [tgMsg, setTgMsg] = useState<string | null>(null)
  const [tgEnviando, setTgEnviando] = useState(false)
  const [copiado, setCopiado] = useState(false)

  // Monta a URL usando o domínio customizado (se configurado) como base.
  // Genérico: /cadastro. Cliente: cria (ou reaproveita) um convite.
  useEffect(() => {
    let ativo = true
    ;(async () => {
      const base = await cadastroLinksApi.baseUrl()
      if (!ativo) return
      if (!cliente) { setUrl(`${base}/cadastro`); return }
      try {
        const l = await cadastroLinksApi.criar({ cliente_id: cliente.id, rotulo: cliente.nome })
        if (ativo) setUrl(`${base}${l.caminho}`)
      } catch {
        if (ativo) setErroLink(true)
      }
    })()
    return () => { ativo = false }
  }, [cliente])

  async function copiar() {
    try { await navigator.clipboard.writeText(url); setCopiado(true); setTimeout(() => setCopiado(false), 2000) } catch { /* noop */ }
  }

  async function enviarEmail() {
    setEmailEnviando(true); setEmailMsg(null)
    try {
      const r = await cadastroLinksApi.enviarEmail(clienteId, emailDest || undefined, copiaPraMim)
      setEmailMsg(`✓ Enviado para ${r.destinatario}${copiaPraMim ? ' (com cópia para você)' : ''}.`)
    } catch (e: any) {
      setEmailMsg(`⚠ ${e?.response?.data?.detail ?? 'Falha ao enviar o e-mail.'}`)
    } finally { setEmailEnviando(false) }
  }

  async function enviarTelegram() {
    setTgEnviando(true); setTgMsg(null)
    try {
      await cadastroLinksApi.enviarTelegram(clienteId)
      setTgMsg('✓ Link enviado ao seu Telegram.')
    } catch (e: any) {
      setTgMsg(`⚠ ${e?.response?.data?.detail ?? 'Falha ao enviar pelo Telegram.'}`)
    } finally { setTgEnviando(false) }
  }

  const mensagemWa = `Olá! Segue o link para seu cadastro no escritório Pimenta Judice: ${url}`
  const waHref = waLink(waNumero, mensagemWa)

  return (
    <div className={cs.overlay} onClick={onClose}>
      <div className={cs.modal} onClick={(e) => e.stopPropagation()}>
        <div className={cs.head}>
          <h2 className={cs.titulo}>{cliente ? `Enviar link — ${cliente.nome}` : 'Enviar link de cadastro'}</h2>
          <button className={cs.fechar} onClick={onClose}>×</button>
        </div>

        {erroLink ? (
          <p className={cs.erro}>Não foi possível gerar o link.</p>
        ) : !url ? (
          <p className={cs.muted}>Gerando link…</p>
        ) : (
          <>
            {/* Link + copiar */}
            <div className={cs.linkBox}>
              <span className={cs.linkText}>{url}</span>
              <button className={cs.btnCopiar} onClick={copiar}>{copiado ? '✓' : 'Copiar'}</button>
            </div>

            {/* E-mail */}
            <section className={cs.secao}>
              <h3 className={cs.secaoTitulo}>✉️ Por e-mail</h3>
              <input className={cs.input} type="email" placeholder="email@cliente.com"
                value={emailDest} onChange={(e) => setEmailDest(e.target.value)} />
              <label className={cs.check}>
                <input type="checkbox" checked={copiaPraMim} onChange={(e) => setCopiaPraMim(e.target.checked)} />
                Enviar com cópia para mim
              </label>
              <button className={cs.btnAcao} disabled={emailEnviando || !emailDest} onClick={enviarEmail}>
                {emailEnviando ? 'Enviando…' : 'Enviar e-mail'}
              </button>
              {emailMsg && <p className={cs.msg}>{emailMsg}</p>}
            </section>

            {/* WhatsApp */}
            <section className={cs.secao}>
              <h3 className={cs.secaoTitulo}>💬 Por WhatsApp</h3>
              <input className={cs.input} inputMode="tel" placeholder="DDD + número (ex.: 11987654321)"
                value={waNumero} onChange={(e) => setWaNumero(e.target.value)} />
              <a className={`${cs.btnAcao} ${!waHref ? cs.btnDisabled : ''}`}
                href={waHref || undefined} target="_blank" rel="noreferrer"
                onClick={(e) => { if (!waHref) e.preventDefault() }}>
                Abrir WhatsApp
              </a>
            </section>

            {/* Telegram */}
            <section className={cs.secao}>
              <h3 className={cs.secaoTitulo}>📨 Telegram</h3>
              <button className={cs.btnAcao} disabled={tgEnviando} onClick={enviarTelegram}>
                {tgEnviando ? 'Enviando…' : 'Enviar pro meu Telegram'}
              </button>
              {tgMsg && <p className={cs.msg}>{tgMsg}</p>}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
