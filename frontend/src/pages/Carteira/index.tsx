// @ts-nocheck
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
// removed: tabs'
// removed: card'
import { DollarSign, Users, TrendingUp, Target } from 'lucide-react'
import api from '@/api/client'
import Debentures from './Debentures'
import Imobiliario from './Imobiliario'
import Fundos from './Fundos'
import Estrategias from './Estrategias'

export default function CarteiraPage() {
  const { data: dashboardData, isLoading } = useQuery({
    queryKey: ['carteira-dashboard'],
    queryFn: () => api.get('/api/carteira/dashboard').then(r => r.data),
  })

  if (isLoading) {
    return <div className="p-8">Carregando...</div>
  }

  const stats = [
    {
      label: 'Clientes',
      value: dashboardData?.total_clientes || 0,
      icon: Users,
      color: 'text-blue-600',
    },
    {
      label: 'Carteira Total',
      value: `R$ ${(dashboardData?.carteira_total || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`,
      icon: DollarSign,
      color: 'text-green-600',
    },
    {
      label: 'Valor Atual',
      value: `R$ ${(dashboardData?.valor_atual_total || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`,
      icon: TrendingUp,
      color: 'text-purple-600',
    },
    {
      label: 'Expectativa Honorários',
      value: `R$ ${(dashboardData?.expectativa_honorarios || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`,
      icon: Target,
      color: 'text-orange-600',
    },
  ]

  return (
    <div className="space-y-6 p-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <Card key={stat.label}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{stat.label}</CardTitle>
                <Icon className={`h-4 w-4 ${stat.color}`} />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Variação */}
      {dashboardData?.variacao_total_percentual && (
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-gray-600">
              Variação do período:{' '}
              <span className={dashboardData.variacao_total_percentual >= 0 ? 'text-green-600' : 'text-red-600'}>
                {dashboardData.variacao_total_percentual > 0 ? '+' : ''}{dashboardData.variacao_total_percentual.toFixed(2)}%
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs de conteúdo */}
      <Tabs defaultValue="debentures" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="debentures">Debêntures</TabsTrigger>
          <TabsTrigger value="imobiliario">Imobiliário</TabsTrigger>
          <TabsTrigger value="fundos">Fundos</TabsTrigger>
          <TabsTrigger value="estrategias">Estratégias</TabsTrigger>
        </TabsList>

        <TabsContent value="debentures" className="space-y-4">
          <Debentures />
        </TabsContent>

        <TabsContent value="imobiliario" className="space-y-4">
          <Imobiliario />
        </TabsContent>

        <TabsContent value="fundos" className="space-y-4">
          <Fundos />
        </TabsContent>

        <TabsContent value="estrategias" className="space-y-4">
          <Estrategias />
        </TabsContent>
      </Tabs>
    </div>
  )
}
