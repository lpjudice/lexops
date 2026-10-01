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

export default function Imobiliario() {
  const queryClient = useQueryClient()
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  const [formData, setFormData] = useState({
    cliente_id: 0,
    empreendimento_id: 0,
    partes_interessadas: [''],
    percentual_participacao: 100,
    valor_total_compromissado: 0,
    valor_efetivamente_investido: 0,
    valor_esperado_retorno: 0,
    observacoes: '',
  })

  const { data: posicoes = [], isLoading } = useQuery({
    queryKey: ['carteira-imobiliario'],
    queryFn: () => api.get('/api/carteira/imobiliario', { params: { limit: 1000 } }).then(r => r.data.data),
  })

  const { data: empreendimentos = [] } = useQuery({
    queryKey: ['carteira-empreendimentos'],
    queryFn: () => api.get('/api/carteira/empreendimentos').then(r => r.data),
  })

  const { data: clientes = [] } = useQuery({
    queryKey: ['carteira-clientes'],
    queryFn: () => api.get('/api/carteira/clientes', { params: { limit: 1000 } }).then(r => r.data.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: any) => api.post('/api/carteira/imobiliario', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carteira-imobiliario'] })
      setIsDialogOpen(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/api/carteira/imobiliario/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['carteira-imobiliario'] }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (formData.cliente_id && formData.empreendimento_id) {
      createMutation.mutate(formData)
    }
  }

  const columns = [
    {
      key: 'empreendimento_id',
      label: 'Empreendimento',
      render: (id: number) => {
        const emp = empreendimentos.find((e: any) => e.id === id)
        return emp?.nome_venda || '-'
      },
    },
    {
      key: 'valor_efetivamente_investido',
      label: 'Investido',
      render: (v: number) => `R$ ${v.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`,
    },
    {
      key: 'valor_total_compromissado',
      label: 'Compromissado',
      render: (v: number) => `R$ ${v.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`,
    },
    {
      key: 'valor_esperado_retorno',
      label: 'Retorno Esperado',
      render: (v: number) => `R$ ${v.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`,
    },
    {
      key: 'percentual_participacao',
      label: '%',
      render: (v: number) => `${v.toFixed(0)}%`,
    },
  ]

  return (
    <div className="space-y-4">
      <CarteiraTabela
        title="Posições Imobiliárias"
        columns={columns}
        data={posicoes}
        isLoading={isLoading}
        addButtonLabel="+ Novo Empreendimento"
        onAddNew={() => {
          setFormData({
            cliente_id: 0,
            empreendimento_id: 0,
            partes_interessadas: [''],
            percentual_participacao: 100,
            valor_total_compromissado: 0,
            valor_efetivamente_investido: 0,
            valor_esperado_retorno: 0,
            observacoes: '',
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
            <DialogTitle>Novo Investimento Imobiliário</DialogTitle>
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
                <Label>Empreendimento *</Label>
                <Select
                  value={String(formData.empreendimento_id)}
                  onValueChange={(v) => setFormData({ ...formData, empreendimento_id: parseInt(v) })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {empreendimentos.map((e: any) => (
                      <SelectItem key={e.id} value={String(e.id)}>
                        {e.nome_venda}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Valor Compromissado (R$) *</Label>
                <Input
                  type="number"
                  value={formData.valor_total_compromissado}
                  onChange={(e) => setFormData({ ...formData, valor_total_compromissado: parseFloat(e.target.value) })}
                  step="0.01"
                  required
                />
              </div>

              <div>
                <Label>Valor Investido (R$) *</Label>
                <Input
                  type="number"
                  value={formData.valor_efetivamente_investido}
                  onChange={(e) => setFormData({ ...formData, valor_efetivamente_investido: parseFloat(e.target.value) })}
                  step="0.01"
                  required
                />
              </div>

              <div>
                <Label>Participação (%)</Label>
                <Input
                  type="number"
                  value={formData.percentual_participacao}
                  onChange={(e) => setFormData({ ...formData, percentual_participacao: parseFloat(e.target.value) })}
                  step="0.01"
                />
              </div>

              <div>
                <Label>Retorno Esperado (R$)</Label>
                <Input
                  type="number"
                  value={formData.valor_esperado_retorno}
                  onChange={(e) => setFormData({ ...formData, valor_esperado_retorno: parseFloat(e.target.value) })}
                  step="0.01"
                />
              </div>
            </div>

            <div>
              <Label>Observações</Label>
              <Textarea
                value={formData.observacoes}
                onChange={(e) => setFormData({ ...formData, observacoes: e.target.value })}
                className="h-20"
              />
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
