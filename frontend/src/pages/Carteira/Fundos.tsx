// @ts-nocheck
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import CarteiraTabela from '@/components/CarteiraTabela'
// removed: dialog'
// removed: button'
// removed: input'
// removed: select'
// removed: label'
import api from '@/api/client'

export default function Fundos() {
  const queryClient = useQueryClient()
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  const [formData, setFormData] = useState({
    cliente_id: 0,
    fundo_id: 0,
    numero_conta: '',
    data_aplicacao: new Date().toISOString().split('T')[0],
    valor_aplicado: 0,
    quantidade_cotas: 0,
    valor_cota_atual: 0,
  })

  const { data: posicoes = [], isLoading } = useQuery({
    queryKey: ['carteira-fundos'],
    queryFn: () => api.get('/api/carteira/fundos', { params: { limit: 1000 } }).then(r => r.data.data),
  })

  const { data: fundos = [] } = useQuery({
    queryKey: ['carteira-fundos-referencia'],
    queryFn: () => api.get('/api/carteira/fundos-referencia').then(r => r.data),
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['carteira-clientes'],
    queryFn: () => api.get('/api/carteira/clientes', { params: { limit: 1000 } }).then(r => r.data.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: any) => api.post('/api/carteira/fundos', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carteira-fundos'] })
      setIsDialogOpen(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/api/carteira/fundos/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['carteira-fundos'] }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (formData.cliente_id && formData.fundo_id && formData.valor_aplicado > 0) {
      createMutation.mutate(formData)
    }
  }

  const variacaoColor = (variacao: number | null | undefined) => {
    if (!variacao) return 'text-gray-600'
    if (variacao > 0) return 'text-green-600 font-semibold'
    return 'text-red-600 font-semibold'
  }

  const columns = [
    {
      key: 'fundo_id',
      label: 'Fundo',
      render: (id: number) => {
        const fundo = fundos.find((f: any) => f.id === id)
        return fundo?.nome_fundo.substring(0, 40) + (fundo?.nome_fundo.length > 40 ? '...' : '') || '-'
      },
    },
    {
      key: 'valor_aplicado',
      label: 'Investido',
      render: (v: number) => `R$ ${v.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`,
    },
    {
      key: 'valor_atual_estimado',
      label: 'Valor Atual',
      render: (v: number) => `R$ ${v?.toLocaleString('pt-BR', { maximumFractionDigits: 0 }) || '-'}`,
    },
    {
      key: 'variacao_percentual',
      label: 'Variação',
      render: (v: number | null | undefined) => (
        <span className={variacaoColor(v)}>
          {v !== null && v !== undefined ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '-'}
        </span>
      ),
    },
    {
      key: 'tem_direito_recompra',
      label: 'Direito Recompra',
      render: (v: boolean) => (v ? '✓ Sim' : '-'),
    },
  ]

  return (
    <div className="space-y-4">
      <CarteiraTabela
        title="Posições em Fundos"
        columns={columns}
        data={posicoes}
        isLoading={isLoading}
        addButtonLabel="+ Novo Fundo"
        onAddNew={() => {
          setFormData({
            cliente_id: 0,
            fundo_id: 0,
            numero_conta: '',
            data_aplicacao: new Date().toISOString().split('T')[0],
            valor_aplicado: 0,
            quantidade_cotas: 0,
            valor_cota_atual: 0,
          })
          setIsDialogOpen(true)
        }}
        onEdit={() => {}} // TODO: implementar
        onDelete={(id) => deleteMutation.mutate(id)}
        onView={() => {}} // TODO: implementar
      />

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Novo Investimento em Fundo</DialogTitle>
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
                    {clientes.map((c: any) => any) => (
                      <SelectItem key={c.id} value={String(c.id)}>
                        {c.observacoes || `Cliente ${c.id}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Fundo *</Label>
                <Select
                  value={String(formData.fundo_id)}
                  onValueChange={(v) => setFormData({ ...formData, fundo_id: parseInt(v) })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {fundos.map((f: any) => any) => (
                      <SelectItem key={f.id} value={String(f.id)}>
                        {f.nome_fundo.substring(0, 50)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Nº Conta</Label>
                <Input
                  value={formData.numero_conta}
                  onChange={(e) => setFormData({ ...formData, numero_conta: e.target.value })}
                  placeholder="Número da conta"
                />
              </div>

              <div>
                <Label>Data de Aplicação *</Label>
                <Input
                  type="date"
                  value={formData.data_aplicacao}
                  onChange={(e) => setFormData({ ...formData, data_aplicacao: e.target.value })}
                  required
                />
              </div>

              <div>
                <Label>Valor Aplicado (R$) *</Label>
                <Input
                  type="number"
                  value={formData.valor_aplicado}
                  onChange={(e) => setFormData({ ...formData, valor_aplicado: parseFloat(e.target.value) })}
                  step="0.01"
                  required
                />
              </div>

              <div>
                <Label>Qtd Cotas</Label>
                <Input
                  type="number"
                  value={formData.quantidade_cotas}
                  onChange={(e) => setFormData({ ...formData, quantidade_cotas: parseFloat(e.target.value) })}
                  step="0.01"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" className="bg-teal-600 hover:bg-teal-700" disabled={createMutation.isPending}>
                Salvar
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
