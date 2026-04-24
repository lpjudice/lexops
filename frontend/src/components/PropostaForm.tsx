/**
 * PropostaForm — painel para configurar e gerar a proposta PDF.
 * Aparece dentro do card de Anamnese.
 */

import { useState } from 'react'
import api from '../api/client'
import { anotacoesApi } from '../api/anotacoes'
import styles from '../pages/Page.module.css'
import s from './PropostaForm.module.css'

const PROJETOS = ['PPS', 'Patrimonial', 'Personalizado']

interface Props {
  clienteId: string
  clienteNome: string
  anamneseTexto: string
  onClose: () => void
}

export default function PropostaForm({ clienteId, clienteNome, anamneseTexto, onClose }: Props) {
  const [projetoTipo, setProjetoTipo] = useState('PPS')
  const [valor, setValor] = useState('')
  const [condicao, setCondicao] = useState('')
  const [intro, setIntro] = useState('')
  const [gerando, setGerando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const gerar = async () => {
    setGerando(true)
    setErro(null)
    try {
      const resp = await api.post(
        `/clientes/${clienteId}/proposta`,
        {
          projeto_tipo: projetoTipo,
          valor,
          condicao_pagamento: condicao,
          intro_texto: intro,
          anamnese_resumo: anamneseTexto,
        },
        { responseType: 'blob' }
      )
      // Download automático
      const url = URL.createObjectURL(new Blob([resp.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `Proposta_${projetoTipo}_${clienteNome.replace(/\s+/g, '_')}.pdf`
      a.click()
      URL.revokeObjectURL(url)

      // Registra proposta gerada como anotação
      await anotacoesApi.criar({
        cliente_id: clienteId,
        tipo: 'documento',
        data_evento: new Date().toISOString().slice(0, 10),
        titulo: `Proposta ${projetoTipo} gerada`,
        texto: `Proposta ${projetoTipo} — ${valor || 'valor não definido'}${condicao ? ` — ${condicao}` : ''}`,
      })
    } catch {
      setErro('Erro ao gerar proposta. Tente novamente.')
    } finally {
      setGerando(false)
    }
  }

  return (
    <div className={s.root}>
      <div className={s.header}>
        <span>📄 Gerar Proposta</span>
        <button className={s.btnFechar} onClick={onClose}>×</button>
      </div>

      <div className={s.corpo}>
        <div className={s.twoCol}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Tipo de projeto</label>
            <div className={s.chipRow}>
              {PROJETOS.map((p) => (
                <button key={p} type="button"
                  className={`${s.chip} ${projetoTipo === p ? s.chipActive : ''}`}
                  onClick={() => setProjetoTipo(p)}>
                  {p}
                </button>
              ))}
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>Honorários</label>
            <input className={styles.input} placeholder="Ex: R$ 25.000,00" value={valor}
              onChange={(e) => setValor(e.target.value)} />
          </div>
        </div>

        <div className={styles.formRow}>
          <label className={styles.formLabel}>Condição de pagamento</label>
          <input className={styles.input} placeholder="Ex: 50% na assinatura + 50% em 30 dias"
            value={condicao} onChange={(e) => setCondicao(e.target.value)} />
        </div>

        <div className={styles.formRow}>
          <label className={styles.formLabel}>Parágrafo introdutório (opcional)</label>
          <textarea className={styles.input} rows={3} value={intro}
            placeholder="Deixe em branco para usar o texto padrão"
            onChange={(e) => setIntro(e.target.value)} />
        </div>

        {erro && <div className={s.erro}>{erro}</div>}

        <div className={s.acoes}>
          <button className={styles.btnPrimary} onClick={gerar} disabled={gerando}>
            {gerando ? '⏳ Gerando PDF...' : '⬇ Gerar e Baixar Proposta'}
          </button>
          <button className={styles.btnTable} onClick={onClose}>Cancelar</button>
        </div>
      </div>
    </div>
  )
}
