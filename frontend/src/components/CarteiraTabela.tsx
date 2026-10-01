import { useState } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Edit2, Trash2, Eye, Download } from 'lucide-react'

interface Column {
  key: string
  label: string
  render?: (value: any, row: any) => React.ReactNode
}

interface CarteiraTabeaProps {
  columns: Column[]
  data: any[]
  isLoading: boolean
  onEdit: (row: any) => void
  onDelete: (id: number) => void
  onView: (row: any) => void
  filters?: React.ReactNode
  title: string
  addButtonLabel?: string
  onAddNew?: () => void
}

export default function CarteiraTabela({
  columns,
  data,
  isLoading,
  onEdit,
  onDelete,
  onView,
  filters,
  title,
  addButtonLabel = '+ Novo',
  onAddNew,
}: CarteiraTabeaProps) {
  const [searchTerm, setSearchTerm] = useState('')

  const filtered = data.filter((row) =>
    JSON.stringify(row).toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">{title}</h2>
        {onAddNew && (
          <Button onClick={onAddNew} className="bg-teal-600 hover:bg-teal-700">
            {addButtonLabel}
          </Button>
        )}
      </div>

      {/* Filtros */}
      {filters && (
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
          {filters}
        </div>
      )}

      {/* Busca */}
      <Input
        placeholder="Buscar por qualquer campo..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        className="w-full md:w-64"
      />

      {/* Tabela */}
      {isLoading ? (
        <div className="text-center py-8 text-gray-500">Carregando...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-8 text-gray-500">Nenhum registro encontrado</div>
      ) : (
        <div className="border rounded-lg overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-gray-50">
                {columns.map((col) => (
                  <TableHead key={col.key} className="font-semibold">
                    {col.label}
                  </TableHead>
                ))}
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((row, idx) => (
                <TableRow key={row.id || idx} className="hover:bg-gray-50">
                  {columns.map((col) => (
                    <TableCell key={col.key}>
                      {col.render ? col.render(row[col.key], row) : String(row[col.key] || '-')}
                    </TableCell>
                  ))}
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onView(row)}
                        title="Visualizar"
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onEdit(row)}
                        title="Editar"
                      >
                        <Edit2 className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          if (confirm('Tem certeza que deseja deletar?')) {
                            onDelete(row.id)
                          }
                        }}
                        title="Deletar"
                        className="text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Paginação simples */}
      <div className="text-sm text-gray-500">
        Total: {filtered.length} registro{filtered.length !== 1 ? 's' : ''}
      </div>
    </div>
  )
}
