export function Select({ value, onValueChange, children, className = '' }) {
  return (
    <select
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
      className={`border border-gray-300 rounded px-3 py-2 w-full ${className}`}
    >
      {children}
    </select>
  )
}

export function SelectTrigger({ children, className = '' }) {
  return <div className={className}>{children}</div>
}

export function SelectValue({ placeholder }) {
  return <option value="">{placeholder}</option>
}

export function SelectContent({ children }) {
  return <>{children}</>
}

export function SelectItem({ value, children }) {
  return <option value={value}>{children}</option>
}
