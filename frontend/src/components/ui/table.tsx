export function Table({ children, className = '' }) {
  return (
    <div className="border rounded-lg overflow-hidden">
      <table className={`w-full border-collapse ${className}`}>{children}</table>
    </div>
  )
}

export function TableHeader({ children, className = '' }) {
  return <thead className={`bg-gray-100 ${className}`}>{children}</thead>
}

export function TableBody({ children, className = '' }) {
  return <tbody className={className}>{children}</tbody>
}

export function TableRow({ children, className = '' }) {
  return <tr className={`border-b hover:bg-gray-50 ${className}`}>{children}</tr>
}

export function TableCell({ children, className = '' }) {
  return (
    <td className={`px-6 py-4 text-sm text-gray-900 ${className}`}>{children}</td>
  )
}
