/**
 * Seleção MÚLTIPLA de responsáveis (equipe interna) — chips dos escolhidos + o
 * ResponsavelComboBox pra adicionar mais um (inclusive criar um novo na hora).
 * Guarda só os ids (Responsavel.id); os nomes vêm da mesma lista do combobox.
 */
import { useQuery } from '@tanstack/react-query'
import { responsaveisApi } from '../api/responsaveis'
import ResponsavelComboBox from './ResponsavelComboBox'

interface Props {
  value: string[]
  onChange: (ids: string[]) => void
  disabled?: boolean
}

const VAZIO = { nome: '', email: '', id: null }

export default function ResponsaveisMulti({ value, onChange, disabled }: Props) {
  const { data: responsaveis = [] } = useQuery({
    queryKey: ['responsaveis'],
    queryFn: () => responsaveisApi.listar(),
    staleTime: 30_000,
  })
  const porId = new Map(responsaveis.map((r) => [r.id, r]))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {value.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {value.map((id) => {
            const r = porId.get(id)
            return (
              <span key={id} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 4px 3px 10px',
                borderRadius: 999, background: '#ecfdf5', border: '1px solid #a7f3d0', fontSize: 12, color: '#065f46',
              }}>
                {r ? r.nome : 'Responsável removido'}
                {r && !r.email && (
                  <span title="Sem e-mail cadastrado — não receberá o aviso por e-mail" style={{ color: '#b45309' }}>⚠</span>
                )}
                {!disabled && (
                  <button type="button" aria-label={`Remover ${r?.nome ?? 'responsável'}`}
                    onClick={() => onChange(value.filter((v) => v !== id))}
                    style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#065f46', fontSize: 14, lineHeight: 1, padding: '0 6px' }}>
                    ×
                  </button>
                )}
              </span>
            )
          })}
        </div>
      )}
      {!disabled && (
        <ResponsavelComboBox
          value={VAZIO}
          onChange={(v) => {
            if (v.id && !value.includes(v.id)) onChange([...value, v.id])
          }}
        />
      )}
    </div>
  )
}
