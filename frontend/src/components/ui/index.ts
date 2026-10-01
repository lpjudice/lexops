// UI Components - Basic HTML wrappers for Carteira module

import React from 'react'

export const Button = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string; size?: string }
>(({ className, variant, size, ...props }, ref) => {
  const classes = [
    'px-4 py-2 rounded font-medium transition-colors',
    variant === 'outline' ? 'border border-gray-300 hover:bg-gray-50' : 'bg-blue-600 text-white hover:bg-blue-700',
    size === 'sm' ? 'px-2 py-1 text-sm' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return <button ref={ref} className={classes} {...props} />
})

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} className={`border border-gray-300 rounded px-3 py-2 w-full ${className || ''}`} {...props} />
  ),
)

export const Select: React.FC<any> = ({ children, ...props }) => (
  <select className="border border-gray-300 rounded px-3 py-2 w-full" {...props}>
    {children}
  </select>
)
export const SelectTrigger = Select
export const SelectValue: React.FC<any> = ({ placeholder }) => <option value="">{placeholder}</option>
export const SelectContent: React.FC<{ children: React.ReactNode }> = ({ children }) => <>{children}</>
export const SelectItem: React.FC<{ value: string; children: React.ReactNode }> = ({ value, children }) => (
  <option value={value}>{children}</option>
)

export const Label: React.FC<React.LabelHTMLAttributes<HTMLLabelElement>> = ({ children, ...props }) => (
  <label className="block text-sm font-medium text-gray-700 mb-1" {...props}>
    {children}
  </label>
)

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={`border border-gray-300 rounded px-3 py-2 w-full ${className || ''}`} {...props} />
))

export const Dialog: React.FC<{ open: boolean; onOpenChange: (open: boolean) => void; children: React.ReactNode }> =
  ({ open, onOpenChange, children }) =>
    open
      ? (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => onOpenChange(false)}>
            {children}
          </div>
        )
      : null

export const DialogContent: React.FC<{ className?: string; children: React.ReactNode }> = ({
  className,
  children,
}) => (
  <div
    className={`bg-white rounded-lg shadow-lg max-w-2xl w-full mx-4 ${className || ''}`}
    onClick={(e) => e.stopPropagation()}
  >
    {children}
  </div>
)

export const DialogHeader: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="border-b px-6 py-4">{children}</div>
)

export const DialogTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h2 className="text-lg font-semibold">{children}</h2>
)

export const Card: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <div className={`border border-gray-200 rounded-lg shadow-sm ${className || ''}`}>{children}</div>
)

export const CardHeader: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="border-b px-6 py-4">{children}</div>
)

export const CardTitle: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <h3 className={`text-lg font-semibold ${className || ''}`}>{children}</h3>
)

export const CardContent: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => (
  <div className={`px-6 py-4 ${className || ''}`}>{children}</div>
)

export const Tabs: React.FC<{ value: string; onValueChange: (value: string) => void; children: React.ReactNode }> = ({
  value,
  onValueChange,
  children,
}) => <div data-value={value} onClick={() => {}} data-change={onValueChange}>{children}</div>

export const TabsList: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="flex gap-1 border-b">{children}</div>
)

export const TabsTrigger: React.FC<{
  value: string
  children: React.ReactNode
}> = ({ value, children }) => (
  <button className={`px-4 py-2 font-medium border-b-2 ${value ? 'border-blue-600 text-blue-600' : 'border-transparent'}`}>
    {children}
  </button>
)

export const TabsContent: React.FC<{ value: string; children: React.ReactNode }> = ({ value, children }) => (
  <div>{children}</div>
)

export const Table: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <table className="w-full border-collapse">{children}</table>
)

export const TableHeader: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <thead className="bg-gray-100">{children}</thead>
)

export const TableBody: React.FC<{ children: React.ReactNode }> = ({ children }) => <tbody>{children}</tbody>

export const TableRow: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <tr className="border-b hover:bg-gray-50">{children}</tr>
)

export const TableCell: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => (
  <td className={`px-6 py-4 text-sm ${className || ''}`}>{children}</td>
)
