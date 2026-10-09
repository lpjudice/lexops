import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autosIa } from '../../api/autosIa'
import pageStyles from '../../pages/Page.module.css'
import styles from './AlertasConfig.module.css'

/** Painel global dos alertas de "novo andamento": interruptor + destinatários do e-mail.
 * O destinatário padrão é o usuário master (sempre recebe); os extras são editáveis aqui.
 * Cada alteração é salva na hora. */
export default function AlertasConfig() {
  const qc = useQueryClient()
  const [aberto, setAberto] = useState(false)
  const [novoEmail, setNovoEmail] = useState('')
  const [erro, setErro] = useState('')

  const { data: cfg } = useQuery({
    queryKey: ['autos-ia', 'alertas-config'],
    queryFn: () => autosIa.obterConfigAlertas(),
  })

  const salvar = useMutation({
    mutationFn: (data: { ativo?: boolean; emails_extras?: string[] }) => autosIa.atualizarConfigAlertas(data),
    onSuccess: (novo) => {
      qc.setQueryData(['autos-ia', 'alertas-config'], novo)
      setErro('')
    },
    onError: (e: any) => setErro(e?.response?.data?.detail || e?.message || 'Não foi possível salvar.'),
  })

  if (!cfg) return null

  const adicionar = () => {
    const e = novoEmail.trim().toLowerCase()
    if (!e) return
    if (cfg.email_padrao.includes(e) || cfg.emails_extras.includes(e)) {
      setErro('Esse e-mail já recebe os alertas.')
      return
    }
    salvar.mutate({ emails_extras: [...cfg.emails_extras, e] }, { onSuccess: () => setNovoEmail('') })
  }
  const totalDestinos = cfg.email_padrao.length + cfg.emails_extras.length

  return (
    <div className={styles.card}>
      <button type="button" className={styles.head} onClick={() => setAberto(!aberto)} aria-expanded={aberto}>
        <span className={styles.titulo}>🔔 Alertas de novo andamento</span>
        <span className={cfg.ativo ? styles.pillOn : styles.pillOff}>{cfg.ativo ? 'ligados' : 'desligados'}</span>
        <span className={styles.resumo}>
          Telegram + e-mail para {totalDestinos} endereço(s), logo após cada sincronização
        </span>
        <span className={styles.chevron}>{aberto ? '▾' : '▸'}</span>
      </button>

      {aberto && (
        <div className={styles.corpo}>
          <p className={styles.explica}>
            Depois de cada sincronização do Autos IA (as 3 automáticas do dia e também o “Sincronizar agora”), você
            recebe um aviso com os documentos e movimentos novos do processo: no Telegram (mesmo grupo do push de
            andamentos, com o botão para baixar os documentos) e por e-mail.
          </p>

          <label className={styles.switchRow}>
            <span className={styles.switch}>
              <input
                type="checkbox"
                checked={cfg.ativo}
                disabled={salvar.isPending}
                onChange={(e) => salvar.mutate({ ativo: e.target.checked })}
              />
              <span className={styles.slider} />
            </span>
            {cfg.ativo ? 'Alertas ligados' : 'Alertas desligados — nenhum aviso automático será enviado'}
          </label>

          <div>
            <span className={styles.label}>E-mails que recebem</span>
            <div className={styles.chips}>
              {cfg.email_padrao.map((e) => (
                <span key={e} className={`${styles.chip} ${styles.chipPadrao}`} title="Usuário master do sistema — sempre recebe">
                  {e} <span className={styles.chipSub}>padrão · usuário master</span>
                </span>
              ))}
              {cfg.emails_extras.map((e) => (
                <span key={e} className={styles.chip}>
                  {e}
                  <button
                    type="button"
                    className={styles.chipX}
                    aria-label={`Remover ${e}`}
                    title="Remover"
                    disabled={salvar.isPending}
                    onClick={() => salvar.mutate({ emails_extras: cfg.emails_extras.filter((x) => x !== e) })}
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
            <div className={styles.addRow}>
              <input
                className={styles.addInput}
                type="email"
                placeholder="Adicionar outro e-mail para receber os andamentos"
                value={novoEmail}
                onChange={(e) => { setNovoEmail(e.target.value); setErro('') }}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); adicionar() } }}
              />
              <button type="button" className={pageStyles.btnSmall} disabled={salvar.isPending || !novoEmail.trim()} onClick={adicionar}>
                Adicionar
              </button>
            </div>
            {erro && <div className={styles.erro}>{erro}</div>}
          </div>

          <div className={styles.nota}>
            Para conferir como fica, abra um caso e use <strong>Testar alerta</strong>.
          </div>
        </div>
      )}
    </div>
  )
}
