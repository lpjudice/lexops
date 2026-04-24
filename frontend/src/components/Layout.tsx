import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  Users,
  Briefcase,
  Calendar,
  Newspaper,
  Sparkles,
  FileText,
  FolderOpen,
  Receipt,
  TrendingUp,
  Handshake,
  Settings,
  Scale,
  CheckSquare,
  Menu,
  X,
  LogOut,
} from 'lucide-react'
import api from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import styles from './Layout.module.css'

function useTarefasVencendo() {
  return useQuery({
    queryKey: ['tarefas'],
    queryFn: () => api.get<{ data_limite?: string | null; status: string }[]>('/tarefas/').then((r) => r.data),
    select: (tarefas) => {
      const hoje = new Date().toISOString().slice(0, 10)
      const em7dias = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
      return tarefas.filter(
        (t) =>
          t.status !== 'concluido' &&
          t.status !== 'cancelado' &&
          t.data_limite != null &&
          t.data_limite >= hoje &&
          t.data_limite <= em7dias,
      ).length
    },
    staleTime: 24 * 60 * 60 * 1000,
  })
}

function TarefasBadge() {
  const { data: count = 0 } = useTarefasVencendo()
  if (!count) return null
  return <span className={styles.navBadge}>{count}</span>
}

const navGroups = [
  {
    label: 'GESTÃO',
    items: [
      { to: '/dashboard', label: 'Home', Icon: LayoutDashboard },
      { to: '/clientes', label: 'Clientes', Icon: Users },
      { to: '/processos', label: 'Processos', Icon: Briefcase },
      { to: '/prazos', label: 'Prazos', Icon: Calendar },
      { to: '/atendimentos', label: 'Atendimentos', Icon: Handshake },
      { to: '/tarefas', label: 'Tarefas', Icon: CheckSquare },
    ],
  },
  {
    label: 'CONTEÚDO',
    items: [
      { to: '/diario', label: 'Diário Oficial', Icon: Newspaper },
      { to: '/teses', label: 'Teses IA', Icon: Sparkles },
      { to: '/jurisprudencia', label: 'Jurisprudência', Icon: Scale },
    ],
  },
  {
    label: 'DOCUMENTOS',
    items: [
      { to: '/contratos', label: 'Contratos', Icon: FileText },
      { to: '/organizador', label: 'Folder Organizer', Icon: FolderOpen },
    ],
  },
  {
    label: 'FINANCEIRO',
    items: [
      { to: '/financeiro', label: 'Financeiro', Icon: TrendingUp },
      { to: '/reembolsos', label: 'Reembolsos', Icon: Receipt },
    ],
  },
  {
    label: 'SISTEMA',
    items: [
      { to: '/configuracoes', label: 'Configurações', Icon: Settings },
    ],
  },
]

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/clientes': 'Clientes',
  '/processos': 'Processos',
  '/prazos': 'Prazos',
  '/diario': 'Diário Oficial',
  '/teses': 'Teses IA',
  '/jurisprudencia': 'Jurisprudência',
  '/contratos': 'Contratos',
  '/organizador': 'Folder Organizer',
  '/reembolsos': 'Reembolsos',
  '/financeiro': 'Financeiro',
  '/atendimentos': 'Atendimentos',
  '/tarefas': 'Tarefas',
  '/configuracoes': 'Configurações',
}

function Topbar({ onMenuToggle }: { onMenuToggle: () => void }) {
  const location = useLocation()
  const base = '/' + location.pathname.split('/')[1]
  const title = PAGE_TITLES[base] ?? 'Gestor Jurídico'
  const { usuario, logout } = useAuth()

  const initials = usuario?.nome
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase() ?? 'U'

  return (
    <header className={styles.topbar}>
      <div className={styles.topbarLeft}>
        <button className={styles.hamburger} onClick={onMenuToggle} aria-label="Menu">
          <Menu size={20} />
        </button>
        <span className={styles.topbarTitle}>{title}</span>
      </div>
      <div className={styles.topbarUser}>
        <div className={styles.userBadge}>{initials}</div>
        <span className={styles.userName}>{usuario?.nome ?? ''}</span>
        <button className={styles.logoutBtn} onClick={logout} title="Sair">
          <LogOut size={15} />
        </button>
      </div>
    </header>
  )
}

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const closeSidebar = () => setSidebarOpen(false)

  return (
    <div className={styles.shell}>
      {/* Mobile overlay */}
      {sidebarOpen && <div className={styles.overlay} onClick={closeSidebar} />}

      <nav className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ''}`}>
        <div className={styles.sidebarTop}>
          <div className={styles.logo}>
            <span className={styles.logoMain}>PIMENTA JUDICE</span>
            <span className={styles.logoSub}>Advogados</span>
          </div>
          <button className={styles.sidebarClose} onClick={closeSidebar} aria-label="Fechar menu">
            <X size={18} />
          </button>
        </div>

        <div className={styles.nav}>
          {navGroups.map((group) => (
            <div key={group.label} className={styles.navGroup}>
              <span className={styles.navGroupLabel}>{group.label}</span>
              {group.items.map(({ to, label, Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `${styles.navLink} ${isActive ? styles.active : ''}`
                  }
                  onClick={closeSidebar}
                >
                  <Icon size={16} className={styles.navIcon} />
                  <span>{label}</span>
                  {to === '/tarefas' && <TarefasBadge />}
                </NavLink>
              ))}
            </div>
          ))}
        </div>

        <div className={styles.sidebarFooter}>Gestor Jurídico v1.0</div>
      </nav>

      <div className={styles.mainWrapper}>
        <Topbar onMenuToggle={() => setSidebarOpen((o) => !o)} />
        <main className={styles.main}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
