/**
 * Searchable ComboBox — replaces <select> with a text-filtered dropdown.
 * Supports optional "Create" action when no option matches the query.
 */
import { useEffect, useRef, useState } from 'react'
import styles from './ComboBox.module.css'

export interface ComboOption {
  value: string
  label: string         // primary display
  sublabel?: string     // secondary line (smaller)
}

interface Props {
  options: ComboOption[]
  value: string
  onChange: (value: string) => void
  placeholder?: string
  onCreate?: (query: string) => void   // shown when no option matches
  createLabel?: string                 // e.g. "Criar cliente"
  disabled?: boolean
  required?: boolean
  className?: string
  onQueryChange?: (query: string) => void  // fired on every keystroke — for remote/async search
}

export default function ComboBox({
  options, value, onChange, placeholder = 'Buscar...', onCreate,
  createLabel = 'Criar', disabled, required, className, onQueryChange,
}: Props) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [isFocused, setIsFocused] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Sync query with selected label when value changes externally (but not while user is typing)
  useEffect(() => {
    if (!isFocused) {
      const found = options.find((o) => o.value === value)
      setQuery(found ? found.label : '')
    }
  }, [value, options, isFocused])

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = query
    ? options.filter(
        (o) =>
          o.label.toLowerCase().includes(query.toLowerCase()) ||
          (o.sublabel && o.sublabel.toLowerCase().includes(query.toLowerCase()))
      )
    : options

  const handleSelect = (opt: ComboOption) => {
    onChange(opt.value)
    setQuery(opt.label)
    setOpen(false)
  }

  const handleInputChange = (v: string) => {
    setQuery(v)
    setOpen(true)
    onQueryChange?.(v)
    // If cleared, reset value
    if (!v) onChange('')
  }

  const showCreate = onCreate && query.length > 1 && filtered.length === 0

  return (
    <div ref={ref} className={`${styles.wrap} ${className ?? ''}`}>
      <input
        className={styles.input}
        value={query}
        onChange={(e) => handleInputChange(e.target.value)}
        onFocus={() => { setQuery(''); setOpen(true); setIsFocused(true) }}
        onBlur={() => {
          setIsFocused(false)
          // Restore label on blur if user didn't pick a new option
          setTimeout(() => {
            const found = options.find((o) => o.value === value)
            setQuery(found ? found.label : '')
          }, 150) // small delay so mousedown on option fires first
        }}
        placeholder={placeholder}
        disabled={disabled}
        required={required && !value}
        autoComplete="off"
      />
      {open && (
        <div className={styles.dropdown}>
          {filtered.length === 0 && !showCreate && (
            <div className={styles.empty}>Nenhum resultado</div>
          )}
          {filtered.map((opt) => (
            <div
              key={opt.value}
              className={`${styles.option} ${opt.value === value ? styles.selected : ''}`}
              onMouseDown={() => handleSelect(opt)}
            >
              <div className={styles.optLabel}>{opt.label}</div>
              {opt.sublabel && <div className={styles.optSub}>{opt.sublabel}</div>}
            </div>
          ))}
          {showCreate && (
            <div
              className={styles.createOption}
              onMouseDown={() => { onCreate!(query); setOpen(false) }}
            >
              <span className={styles.createIcon}>+</span>
              {createLabel} &ldquo;{query}&rdquo;
            </div>
          )}
        </div>
      )}
    </div>
  )
}
