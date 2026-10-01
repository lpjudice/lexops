// @ts-nocheck
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
// removed: card'
// removed: button'
// removed: input'
// removed: label'
// removed: textarea'
// removed: dialog'
import api from '@/api/client'

export default function Estrategias() {
  const queryClient = useQueryClient()
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')

  const [formData, setFormData] = useState({
    nome: '',
    descricao: '',
    publico: true,
  })

  const { data: estrategias = [], isLoading } = useQuery({
    queryKey: ['carteira-estrategias'],
    queryFn: () => api.get('/api/carteira/estrategias', { params: { limit: 1000 } }).then(r => r.data.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: any) => api.post('/api/carteira/estrategias', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carteira-estrategias'] })
      setIsDialogOpen(false)
      setFormData({ nome: '', descricao: '', publico: true })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (formData.nome.trim()) {
      createMutation.mutate(formData)
    }
  }

  const filtered = estrategias.filter((est: any) =>
    est.nome.toLowerCase().includes(searchTerm.toLowerCase()) ||
    est.descricao?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Estratégias</h2>
        <Button onClick={() => setIsDialogOpen(true)} className="bg-teal-600 hover:bg-teal-700">
          + Nova Estratégia
        </Button>
      </div>

      {/* Busca */}
      <Input
        placeholder="Buscar estratégias..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        className="w-full md:w-96"
      />

      {/* Grid de Cards */}
      {isLoading ? (
        <div className="text-center py-8">Carregando...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="mb-4">Nenhuma estratégia encontrada</p>
          <Button onClick={() => setIsDialogOpen(true)} variant="outline">
            Criar primeira estratégia
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((est: any) => (
            <Card key={est.id} className="hover:shadow-lg transition-shadow">
              <CardHeader>
                <CardTitle className="text-lg">{est.nome}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-gray-600 line-clamp-3">{est.descricao || 'Sem descrição'}</p>

                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>
                    {est.usuarios_count || 0} cliente{(est.usuarios_count || 0) !== 1 ? 's' : ''}
                  </span>
                  <span className={`px-2 py-1 rounded ${est.publico ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
                    {est.publico ? 'Pública' : 'Privada'}
                  </span>
                </div>

                <Button variant="outline" size="sm" className="w-full">
                  Usar essa estratégia
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialog de Nova Estratégia */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Nova Estratégia</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label>Nome da Estratégia *</Label>
              <Input
                value={formData.nome}
                onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                placeholder="Ex: Debentures RH + Resgate Solicitado"
                required
              />
            </div>

            <div>
              <Label>Descrição</Label>
              <Textarea
                value={formData.descricao}
                onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                placeholder="Descreva os objetivos, composição e características dessa estratégia..."
                className="h-32"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="publico"
                checked={formData.publico}
                onChange={(e) => setFormData({ ...formData, publico: e.target.checked })}
                className="rounded"
              />
              <Label htmlFor="publico" className="cursor-pointer">
                Disponibilizar para outros clientes (Pública)
              </Label>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" className="bg-teal-600 hover:bg-teal-700" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Criando...' : 'Criar Estratégia'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
