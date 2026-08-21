import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { prazosApi } from '../api/prazos'
import type { StatusPrazo, TipoContagem, TipoPrazo } from '../api/prazos'
import ResponsavelComboBox from './ResponsavelComboBox'
import styles from '../pages/Page.module.css'

/** Editor do prazo usado dentro do Diário Oficial e do Recorte Digital.
 *
 * Grava sempre em PATCH /prazos/{id} — o mesmo endpoint da tela de Prazos.
 * Como é a mesma linha no banco, alterar por qualquer um dos três menus
 * reflete automaticamente nos outros; o que este componente garante é que as
 * três telas invalidem os mesmos caches e mostrem o novo valor na hora.
 */
export interface PrazoEditavel {
  id: string
  tipo: string
  peca_necessaria: string | null
  descricao: string | null
  data_publicacao: string | null
  dias_prazo: number
  tipo_contagem: 'uteis' | 'corridos'
  responsavel: string | null
  status: string
}

const TIPOS: TipoPrazo[] = [
  'contestacao', 'recurso', 'contrarrazoes', 'manifestacao', 'audiencia', 'pericia', 'outro',
]

const PECAS = [
  'Contestação', 'Recurso de Apelação', 'Recurso Ordinário', 'Agravo Interno',
  'Agravo Regimental', 'Embargos de Declaração', 'Contrarrazões de Apelação',
  'Manifestação', 'Impugnação', 'Réplica', 'Memorial', 'Alegações Finais',
  'Petição Simples', 'Pedido de Prazo', 'Outro',
]

const STATUS: { valor: StatusPrazo; label: string }[] = [
  { valor: 'pendente', label: 'pendente' },
  { valor: 'cumprido', label: 'cumprido' },
  { valor: 'perdido', label: 'perdido' },
  { valor: 'ignorado', label: 'ignorado' },
  { valor: 'nada_a_fazer', label: 'nada a fazer' },
]

export default function PrazoEditorInline({
  prazo,
  dataPublicacaoFallback,
  onSaved,
  onCancel,
}: {
  prazo: PrazoEditavel
  /** Data da publicação de origem, usada quando o prazo não trouxe a própria. */
  dataPublicacaoFallback?: string
  onSaved?: () => void
  onCancel: () => void
}) {
  const qc = useQueryClient()
  const [tipo, setTipo] = useState<TipoPrazo>(
    (TIPOS.includes(prazo.tipo as TipoPrazo) ? prazo.tipo : 'outro') as TipoPrazo,
  )
  const [peca, setPeca] = useState(prazo.peca_necessaria ?? '')
  const [dataPub, setDataPub] = useState(prazo.data_publicacao ?? dataPublicacaoFallback ?? '')
  const [dias, setDias] = useState(prazo.dias_prazo)
  const [contagem, setContagem] = useState<TipoContagem>(prazo.tipo_contagem)
  const [status, setStatus] = useState<StatusPrazo>(prazo.status as StatusPrazo)
  const [descricao, setDescricao] = useState(prazo.descricao ?? '')
  const [responsavel, setResponsavel] = useState<{ nome: string; email: string; id?: string | null }>({
    nome: prazo.responsavel ?? '', email: '', id: null,
  })
  const [erro, setErro] = useState('')

  const salvar = useMutation({
    mutationFn: () =>
      prazosApi.atualizar(prazo.id, {
        tipo,
        peca_necessaria: peca || undefined,
        data_publicacao: dataPub || undefined,
        dias_prazo: dias,
        tipo_contagem: contagem,
        status,
        descricao: descricao || undefined,
        responsavel: responsavel.nome || undefined,
        responsavel_id: responsavel.id ?? undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prazos'] })
      qc.invalidateQueries({ queryKey: ['diario'] })
      qc.invalidateQueries({ queryKey: ['diario2'] })
      qc.invalidateQueries({ queryKey: ['tarefas'] })
      qc.invalidateQueries({ queryKey: ['despacho'] })
      onSaved?.()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setErro(e.response?.data?.detail ?? 'Não foi possível salvar as alterações.'),
  })

  const campo = (label: string, node: React.ReactNode) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={{ fontSize: 10, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '.03em' }}>
        {label}
      </span>
      {node}
    </label>
  )

  return (
    <div style={{
      marginTop: 8, padding: 12, background: '#f9fafb',
      border: '1px solid #e5e7eb', borderRadius: 8,
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
        {campo('Tipo', (
          <select className={styles.input} value={tipo} onChange={(e) => setTipo(e.target.value as TipoPrazo)}>
            {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        ))}
        {campo('Peça necessária', (
          <select className={styles.input} value={peca} onChange={(e) => setPeca(e.target.value)}>
            <option value="">— Selecione —</option>
            {PECAS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        ))}
        {campo('Data da publicação', (
          <input className={styles.input} type="date" value={dataPub} onChange={(e) => setDataPub(e.target.value)} />
        ))}
        {campo('Dias do prazo', (
          <input className={styles.input} type="number" min={0} value={dias} onChange={(e) => setDias(Number(e.target.value))} />
        ))}
        {campo('Contagem', (
          <select className={styles.input} value={contagem} onChange={(e) => setContagem(e.target.value as TipoContagem)}>
            <option value="uteis">Dias úteis</option>
            <option value="corridos">Dias corridos</option>
          </select>
        ))}
        {campo('Status', (
          <select className={styles.input} value={status} onChange={(e) => setStatus(e.target.value as StatusPrazo)}>
            {STATUS.map((s) => <option key={s.valor} value={s.valor}>{s.label}</option>)}
          </select>
        ))}
      </div>

      {campo('Responsável', <ResponsavelComboBox value={responsavel} onChange={setResponsavel} />)}
      {campo('Descrição', (
        <textarea className={styles.input} rows={2} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
      ))}

      {erro && <div style={{ fontSize: 12, color: '#b91c1c' }}>{erro}</div>}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          className={styles.btnPrimary}
          style={{ fontSize: 12, padding: '6px 12px' }}
          disabled={salvar.isPending}
          onClick={() => {
            setErro('')
            if (status === 'nada_a_fazer' && prazo.status !== 'nada_a_fazer' && !confirm(
              'Marcar como "Nada a fazer"?\n\nA publicação é encerrada e as tarefas automáticas dela são canceladas.',
            )) return
            salvar.mutate()
          }}
        >
          {salvar.isPending ? 'Recalculando...' : 'Salvar'}
        </button>
        <button className={styles.btnDanger} onClick={onCancel}>Cancelar</button>
        <span style={{ fontSize: 11, color: '#6b7280' }}>
          A data limite é recalculada com os feriados do estado do processo.
          A alteração vale também na tela de Prazos e no outro menu de publicações.
        </span>
      </div>
    </div>
  )
}
