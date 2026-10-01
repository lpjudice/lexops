import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/api/client'

export default function CarteiraPage() {
  const [tab, setTab] = useState('debentures')

  const { data: dashboardData, isLoading } = useQuery({
    queryKey: ['carteira-dashboard'],
    queryFn: () => api.get('/api/carteira/dashboard').then(r => r.data),
  })

  if (isLoading) {
    return <div className="p-8">Carregando...</div>
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-3xl font-bold">📊 Carteira</h1>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white border rounded-lg p-4">
          <div className="text-sm text-gray-600">Clientes</div>
          <div className="text-2xl font-bold">{dashboardData?.total_clientes || 0}</div>
        </div>
        <div className="bg-white border rounded-lg p-4">
          <div className="text-sm text-gray-600">Carteira Total</div>
          <div className="text-2xl font-bold">
            R$ {(dashboardData?.carteira_total || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
          </div>
        </div>
        <div className="bg-white border rounded-lg p-4">
          <div className="text-sm text-gray-600">Valor Atual</div>
          <div className="text-2xl font-bold">
            R$ {(dashboardData?.valor_atual_total || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
          </div>
        </div>
        <div className="bg-white border rounded-lg p-4">
          <div className="text-sm text-gray-600">Honorários</div>
          <div className="text-2xl font-bold">
            R$ {(dashboardData?.expectativa_honorarios || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
          </div>
        </div>
      </div>

      {/* Tabs simples */}
      <div className="border-b border-gray-200">
        <div className="flex gap-4">
          <button
            onClick={() => setTab('debentures')}
            className={`px-4 py-2 font-medium border-b-2 transition ${
              tab === 'debentures' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600'
            }`}
          >
            💰 Debêntures
          </button>
          <button
            onClick={() => setTab('imobiliario')}
            className={`px-4 py-2 font-medium border-b-2 transition ${
              tab === 'imobiliario' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600'
            }`}
          >
            🏢 Imobiliário
          </button>
          <button
            onClick={() => setTab('fundos')}
            className={`px-4 py-2 font-medium border-b-2 transition ${
              tab === 'fundos' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600'
            }`}
          >
            📈 Fundos
          </button>
          <button
            onClick={() => setTab('estrategias')}
            className={`px-4 py-2 font-medium border-b-2 transition ${
              tab === 'estrategias' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600'
            }`}
          >
            🎯 Estratégias
          </button>
        </div>
      </div>

      {/* Conteúdo das abas */}
      <div className="bg-white border rounded-lg p-6">
        {tab === 'debentures' && (
          <div>
            <h2 className="text-xl font-bold mb-4">Debêntures</h2>
            <p className="text-gray-600">Total: {dashboardData?.breakdown?.debentures || 0} posições</p>
            <p className="text-gray-600">
              Valor: R$ {(dashboardData?.carteira_total || 0).toLocaleString('pt-BR')}
            </p>
          </div>
        )}
        {tab === 'imobiliario' && (
          <div>
            <h2 className="text-xl font-bold mb-4">Imobiliário</h2>
            <p className="text-gray-600">Total: {dashboardData?.breakdown?.imobiliario || 0} posições</p>
          </div>
        )}
        {tab === 'fundos' && (
          <div>
            <h2 className="text-xl font-bold mb-4">Fundos</h2>
            <p className="text-gray-600">Total: {dashboardData?.breakdown?.fundos || 0} posições</p>
          </div>
        )}
        {tab === 'estrategias' && (
          <div>
            <h2 className="text-xl font-bold mb-4">Estratégias</h2>
            <p className="text-gray-600">Carregar estratégias reutilizáveis...</p>
          </div>
        )}
      </div>
    </div>
  )
}
