import { useEffect, useRef, useState } from 'react'

/** Formata número como "40.000,00" (sem R$) */
export function formatBRL(val: number): string {
  if (isNaN(val) || val === 0) return ''
  return val.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** Converte "40.000,00" ou "40000,00" ou "40000.00" → 40000.00 */
export function parseBRL(str: string): number {
  if (!str) return 0
  // Remove pontos de milhar, troca vírgula decimal por ponto
  const clean = str.replace(/\./g, '').replace(',', '.')
  const n = parseFloat(clean)
  return isNaN(n) ? 0 : Math.round(n * 100) / 100
}

interface Props {
  value: number
  onChange: (val: number) => void
  placeholder?: string
  className?: string
  required?: boolean
  disabled?: boolean
}

export default function CurrencyInput({
  value,
  onChange,
  placeholder = '0,00',
  className,
  required,
  disabled,
}: Props) {
  const [raw, setRaw] = useState(value > 0 ? formatBRL(value) : '')
  const focused = useRef(false)

  // Sync when external value changes (e.g., form reset) — only when not focused
  useEffect(() => {
    if (!focused.current) {
      setRaw(value > 0 ? formatBRL(value) : '')
    }
  }, [value])

  return (
    <input
      type="text"
      inputMode="decimal"
      className={className}
      placeholder={placeholder}
      value={raw}
      required={required}
      disabled={disabled}
      onFocus={() => { focused.current = true }}
      onChange={(e) => {
        setRaw(e.target.value)
        onChange(parseBRL(e.target.value))
      }}
      onBlur={() => {
        focused.current = false
        const n = parseBRL(raw)
        setRaw(n > 0 ? formatBRL(n) : '')
        onChange(n)
      }}
    />
  )
}
