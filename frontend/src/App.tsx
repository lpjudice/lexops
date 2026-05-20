import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ClientesPage from './pages/ClientesPage'
import ProcessosPage from './pages/ProcessosPage'
import PrazosPage from './pages/PrazosPage'
import DiarioPage from './pages/DiarioPage'
import Diario2Page from './pages/Diario2Page'
import ClienteDetailPage from './pages/ClienteDetailPage'
import ContratosPage from './pages/ContratosPage'
import TesesPage from './pages/TesesPage'
import ReembolsosPage from './pages/ReembolsosPage'
import FinanceiroPage from './pages/FinanceiroPage'
import AtendimentosPage from './pages/AtendimentosPage'
import ConfiguracoesPage from './pages/ConfiguracoesPage'
import OrganizadorPage from './pages/OrganizadorPage'
import JurisprudenciaPage from './pages/JurisprudenciaPage'
import TarefasPage from './pages/TarefasPage'
import AceitarConvitePage from './pages/AceitarConvitePage'
import ReunioesPage from './pages/ReunioesPage'

const queryClient = new QueryClient()

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { usuario, loading } = useAuth()
  if (loading) return null
  if (!usuario) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/aceitar-convite/:token" element={<AceitarConvitePage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="clientes" element={<ClientesPage />} />
        <Route path="clientes/:id" element={<ClienteDetailPage />} />
        <Route path="processos" element={<ProcessosPage />} />
        <Route path="prazos" element={<PrazosPage />} />
        <Route path="diario" element={<DiarioPage />} />
        <Route path="diario2" element={<Diario2Page />} />
        <Route path="contratos" element={<ContratosPage />} />
        <Route path="teses" element={<TesesPage />} />
        <Route path="reembolsos" element={<ReembolsosPage />} />
        <Route path="financeiro" element={<FinanceiroPage />} />
        <Route path="atendimentos" element={<AtendimentosPage />} />
        <Route path="configuracoes" element={<ConfiguracoesPage />} />
        <Route path="organizador" element={<OrganizadorPage />} />
        <Route path="jurisprudencia" element={<JurisprudenciaPage />} />
        <Route path="tarefas" element={<TarefasPage />} />
        <Route path="reunioes" element={<ReunioesPage />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
