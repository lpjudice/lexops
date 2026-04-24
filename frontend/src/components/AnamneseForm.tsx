/**
 * AnamneseForm — formulário estruturado de anamnese jurídica.
 * Serializa as respostas num texto formatado e chama onSave(texto).
 */

import { useState } from 'react'
import styles from '../pages/Page.module.css'
import s from './AnamneseForm.module.css'

interface Section {
  titulo: string
  campos: { label: string; key: string; rows?: number }[]
}

const SECTIONS: Section[] = [
  {
    titulo: 'Dados Pessoais e Familiares',
    campos: [
      { label: 'Estado civil', key: 'estado_civil' },
      { label: 'Regime de bens', key: 'regime_bens' },
      { label: 'Filhos (nome e idade)', key: 'filhos', rows: 2 },
      { label: 'Outros dependentes', key: 'dependentes' },
    ],
  },
  {
    titulo: 'Patrimônio',
    campos: [
      { label: 'Imóveis (quantidade e estimativa de valor)', key: 'imoveis', rows: 2 },
      { label: 'Participações societárias / empresas', key: 'empresas', rows: 2 },
      { label: 'Investimentos financeiros (estimativa)', key: 'investimentos' },
      { label: 'Veículos, obras, outros bens', key: 'outros_bens' },
      { label: 'Dívidas e passivos relevantes', key: 'passivos' },
    ],
  },
  {
    titulo: 'Situação Tributária',
    campos: [
      { label: 'Tipo de tributação atual (Simples, Lucro Real, IRPF…)', key: 'tributacao' },
      { label: 'Problemas ou riscos tributários identificados', key: 'riscos_tributarios', rows: 2 },
    ],
  },
  {
    titulo: 'Objetivos e Necessidades',
    campos: [
      { label: 'Objetivo principal do planejamento', key: 'objetivo_principal', rows: 2 },
      { label: 'Preocupações com sucessão (quem herda, como)', key: 'sucessao', rows: 2 },
      { label: 'Proteção patrimonial desejada', key: 'protecao', rows: 2 },
      { label: 'Prazo desejado para implementação', key: 'prazo_impl' },
    ],
  },
  {
    titulo: 'Informações Adicionais',
    campos: [
      { label: 'Processos judiciais pendentes ou relevantes', key: 'processos_pendentes', rows: 2 },
      { label: 'Outras observações', key: 'obs', rows: 3 },
    ],
  },
]

function serializarRespostas(respostas: Record<string, string>): string {
  const linhas: string[] = []
  for (const sec of SECTIONS) {
    const temResposta = sec.campos.some((c) => respostas[c.key]?.trim())
    if (!temResposta) continue
    linhas.push(`[${sec.titulo.toUpperCase()}]`)
    for (const campo of sec.campos) {
      const val = respostas[campo.key]?.trim()
      if (val) linhas.push(`${campo.label}: ${val}`)
    }
    linhas.push('')
  }
  return linhas.join('\n').trim()
}

interface Props {
  onSave: (texto: string, titulo: string) => void
  onCancel: () => void
  isSaving?: boolean
}

export default function AnamneseForm({ onSave, onCancel, isSaving }: Props) {
  const [respostas, setRespostas] = useState<Record<string, string>>({})

  const set = (key: string, val: string) => setRespostas((r) => ({ ...r, [key]: val }))

  const handleSave = () => {
    const texto = serializarRespostas(respostas)
    if (!texto) return
    onSave(texto, 'Anamnese')
  }

  return (
    <div className={s.root}>
      <div className={s.header}>
        <span className={s.headerIcon}>📋</span>
        <span className={s.headerTitulo}>Anamnese Jurídica</span>
        <span className={s.headerSub}>Preencha apenas os campos relevantes</span>
      </div>

      {SECTIONS.map((sec) => (
        <div key={sec.titulo} className={s.secao}>
          <div className={s.secaoTitulo}>{sec.titulo}</div>
          <div className={s.campos}>
            {sec.campos.map((campo) => (
              <div key={campo.key} className={styles.formRow}>
                <label className={styles.formLabel}>{campo.label}</label>
                {(campo.rows ?? 1) > 1 ? (
                  <textarea
                    className={styles.input}
                    rows={campo.rows}
                    value={respostas[campo.key] ?? ''}
                    onChange={(e) => set(campo.key, e.target.value)}
                    placeholder="(opcional)"
                  />
                ) : (
                  <input
                    className={styles.input}
                    value={respostas[campo.key] ?? ''}
                    onChange={(e) => set(campo.key, e.target.value)}
                    placeholder="(opcional)"
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className={s.acoes}>
        <button
          className={styles.btnPrimary}
          onClick={handleSave}
          disabled={isSaving || !Object.values(respostas).some((v) => v?.trim())}
        >
          {isSaving ? 'Salvando...' : 'Salvar Anamnese'}
        </button>
        <button className={styles.btnTable} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  )
}
