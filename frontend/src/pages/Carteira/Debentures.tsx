// @ts-nocheck
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import CarteiraTabela from '@/components/CarteiraTabela'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import api from '@/api/client'
import UploadDocumentoModal from './UploadDocumentoModal'

interface DebenturePosicao {
  id: number
  cliente_id: number
  emissao_id: number
  numero_cautela: string
  valor_aplicado: number
  valor_atual_estimado: number
  variacao_percentual: number
  status_resgate: string
  data_aquisicao: string
}

export default function Debentures() {
  const queryClient = useQueryClient()
  const [filtroSerie, setFiltroSerie] = useState('')
  const [filtroStatus, setFiltroStatus] = useState('')
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)

  const [formData, setFormData] = useState({
    cliente_id: 0,
    emissao_id: 0,
    numero_cautela: '',
    valor_aplicado: 0,
    data_aquisicao: new Date().toISOString().split('T')[0],
    valor_atual_estimado: 0,
    status_resgate: 'Ativo',
    observacoes: '',
  })

  const { data: debentures = [], isLoading } = useQuery({
    queryKey: ['carteira-debentures', filtroSerie, filtroStatus],
    queryFn: () =>
      api.get('/api/carteira/debentures', {
        params: { serie: filtroSerie, status_resgate: filtroStatus },
      }).then((r: any) => r.data.data),
  })

  const { data: emissoes = [] } = useQuery({
    queryKey: ['carteira-emissoes'],
    queryFn: () => api.get('/api/carteira/emissoes').then((r: any) => r.data),
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['carteira-clientes'],
    queryFn: () => api.get('/api/carteira/clientes', { params: { limit: 1000 } }).then((r: any) => r.data.data),
  })

  // Mutações
  const createMutation = useMutation({
    mutationFn: (data: any) => api.post('/api/carteira/debentures', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carteira-debentures'] })
      setIsDialogOpen(false)
      setFormData({
        cliente_id: 0,
        emissao_id: 0,
        numero_cautela: '',
        valor_aplicado: 0,
        data_aquisicao: new Date().toISOString().split('T')[0],
        valor_atual_estimado: 0,
        status_resgate: 'Ativo',
        observacoes: '',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/api/carteira/debentures/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['carteira-debentures'] }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (formData.cliente_id && formData.emissao_id) {
      createMutation.mutate(formData)
    }
  }

  const variacaoColor = (variacao: number) => {
    if (variacao > 0) return 'text-green-600 font-semibold'
    if (variacao < 0) return 'text-red-600 font-semibold'
    return 'text-gray-600'
  }

  const statusColor = (status: string) => {
    const colors: Record<string, string> = {
      'Ativo': 'bg-green-100 text-green-800',
      'Solicitado': 'bg-yellow-100 text-yellow-800',
      'Negado': 'bg-red-100 text-red-800',
      'Processando': 'bg-blue-100 text-blue-800',
      'Liquidado': 'bg-gray-100 text-gray-800',
    }
    return colors[status] || 'bg-gray-100 text-gray-800'
  }

  const columns = [
    {
      key: 'numero_cautela',
      label: 'Cautela',
    },
    {
      key: 'emissao_id',
      label: 'Série',
      render: (emissaoId: number) => {
        const emissao = emissoes.find((e: any) => e.id === emissaoId)
        return emissao?.nome_serie || '-'
      },
    },
    {
      key: 'valor_aplicado',
      label: 'Valor Aplicado',
      render: (v: number) => `R$ ${v.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}`,
    },
    {
      key: 'valor_atual_estimado',
      label: 'Valor Atual',
      render: (v: number) => `R$ ${v.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}`,
    },
    {
      key: 'variacao_percentual',
      label: 'Variação',
      render: (v: number) => <span className={variacaoColor(v)}>{v.toFixed(2)}%</span>,
    },
    {
      key: 'status_resgate',
      label: 'Status',
      render: (status: string) => (
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusColor(status)}`}>
          {status}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* Filtros & Ações */}
      <div className="space-y-3">
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <Label className="text-sm font-medium">Série</Label>
            <Input
              placeholder="BRMAPEX110..."
              value={filtroSerie}
              onChange={(e) => setFiltroSerie(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-sm font-medium">Status Resgate</Label>
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Todos</SelectItem>
                <SelectItem value="Ativo">Ativo</SelectItem>
                <SelectItem value="Solicitado">Solicitado</SelectItem>
                <SelectItem value="Negado">Negado</SelectItem>
                <SelectItem value="Processando">Processando</SelectItem>
                <SelectItem value="Liquidado">Liquidado</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setFiltroSerie('')
                setFiltroStatus('')
              }}
            >
              Limpar
            </Button>
            <Button
              className="bg-purple-600 hover:bg-purple-700 flex-1"
              onClick={() => setIsUploadOpen(true)}
            >
              📄 Extrair com IA
            </Button>
          </div>
        </div>
      </div>

      {/* Tabela */}
      <CarteiraTabela
        title="Posições em Debêntures"
        columns={columns}
        data={debentures}
        isLoading={isLoading}
        addButtonLabel="+ Nova Debênture"
        onAddNew={() => {
          setEditingId(null)
          setFormData({
            cliente_id: 0,
            emissao_id: 0,
            numero_cautela: '',
            valor_aplicado: 0,
            data_aquisicao: new Date().toISOString().split('T')[0],
            valor_atual_estimado: 0,
            status_resgate: 'Ativo',
            observacoes: '',
          })
          setIsDialogOpen(true)
        }}
        onEdit={(row) => {
          setEditingId(row.id)
          setFormData(row)
          setIsDialogOpen(true)
        }}
        onDelete={(id) => deleteMutation.mutate(id)}
        onView={(row) => {
          console.log('Viewing:', row)
          // TODO: Abrir modal de detalhes
        }}
      />

      {/* Dialog de Novo/Edição */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editingId ? 'Editar Debênture' : 'Nova Debênture'}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Cliente *</Label>
                <Select
                  value={String(formData.cliente_id)}
                  onValueChange={(v) => setFormData({ ...formData, cliente_id: parseInt(v) })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {clientes.map((c: any) => (
                      <SelectItem key={c.id} value={String(c.id)}>
                        {c.observacoes || `Cliente ${c.id}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Série/Emissão *</Label>
                <Select
                  value={String(formData.emissao_id)}
                  onValueChange={(v) => setFormData({ ...formData, emissao_id: parseInt(v) })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {emissoes.map((e: any) => any) => (
                      <SelectItem key={e.id} value={String(e.id)}>
                        {e.nome_serie}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Nº Cautela *</Label>
                <Input
                  value={formData.numero_cautela}
                  onChange={(e) => setFormData({ ...formData, numero_cautela: e.target.value })}
                  placeholder="1954"
                  required
                />
              </div>

              <div>
                <Label>Valor Aplicado (R$) *</Label>
                <Input
                  type="number"
                  value={formData.valor_aplicado}
                  onChange={(e) => setFormData({ ...formData, valor_aplicado: parseFloat(e.target.value) })}
                  placeholder="0.00"
                  step="0.01"
                  required
                />
              </div>

              <div>
                <Label>Data de Aquisição *</Label>
                <Input
                  type="date"
                  value={formData.data_aquisicao}
                  onChange={(e) => setFormData({ ...formData, data_aquisicao: e.target.value })}
                  required
                />
              </div>

              <div>
                <Label>Valor Atual (R$)</Label>
                <Input
                  type="number"
                  value={formData.valor_atual_estimado}
                  onChange={(e) => setFormData({ ...formData, valor_atual_estimado: parseFloat(e.target.value) })}
                  placeholder="0.00"
                  step="0.01"
                />
              </div>

              <div>
                <Label>Status</Label>
                <Select
                  value={formData.status_resgate}
                  onValueChange={(v) => setFormData({ ...formData, status_resgate: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Ativo">Ativo</SelectItem>
                    <SelectItem value="Solicitado">Solicitado</SelectItem>
                    <SelectItem value="Negado">Negado</SelectItem>
                    <SelectItem value="Processando">Processando</SelectItem>
                    <SelectItem value="Liquidado">Liquidado</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label>Observações</Label>
              <Textarea
                value={formData.observacoes}
                onChange={(e) => setFormData({ ...formData, observacoes: e.target.value })}
                placeholder="Notas..."
                className="h-20"
              />
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                Cancelar
              </Button>
              <Button
                type="submit"
                className="bg-teal-600 hover:bg-teal-700"
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Modal de Upload com IA */}
      <UploadDocumentoModal
        clienteId={formData.cliente_id}
        open={isUploadOpen}
        onOpenChange={setIsUploadOpen}
      />
    </div>
  )
}
