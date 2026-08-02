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
  Video,
  Menu,
  X,
  LogOut,
  ScrollText,
  BarChart3,
  ShieldCheck,
  Users2,
  LayoutGrid,
  Gavel,
  Landmark,
  Camera,
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

type NavItem = { to: string; label: string; Icon: React.ComponentType<{ size?: number; className?: string }> }
type NavGroup = {
  label: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    label: 'GESTÃO',
    items: [
      { to: '/dashboard', label: 'Home', Icon: LayoutDashboard },
      { to: '/clientes', label: 'Clientes', Icon: Users },
      { to: '/processos', label: 'Processos', Icon: Briefcase },
      { to: '/prazos', label: 'Prazos', Icon: Calendar },
      { to: '/atendimentos', label: 'Atendimentos', Icon: Handshake },
      { to: '/tarefas', label: 'Tarefas', Icon: CheckSquare },
      { to: '/tarefas-cards', label: 'Tarefas Cards', Icon: LayoutGrid },
      { to: '/reunioes', label: 'Reuniões', Icon: Video },
      { to: '/conselho', label: 'Expansão', Icon: Users2 },
      { to: '/instagram', label: 'Instagram', Icon: Camera },
    ],
  },
  {
    label: 'CONTEÚDO',
    items: [
      { to: '/despacho', label: 'Despacho', Icon: Gavel },
      { to: '/conselho-juridico', label: 'Conselho Jurídico', Icon: Landmark },
      { to: '/diario', label: 'Diário Oficial', Icon: Newspaper },
      { to: '/diario2', label: 'Recorte Digital OAB', Icon: Newspaper },
      { to: '/teses', label: 'Teses IA', Icon: Sparkles },
      { to: '/jurisprudencia', label: 'Jurisprudência', Icon: Scale },
      { to: '/precedentcheck', label: 'PrecedentCheck', Icon: ShieldCheck },
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
    label: 'BACKOFFICE & FINANCEIRO',
    items: [
      { to: '/financeiro', label: 'Financeiro', Icon: TrendingUp },
      { to: '/pagantes', label: 'Pagantes', Icon: Users },
      { to: '/reembolsos', label: 'Reembolsos', Icon: Receipt },
      { to: '/fiscal', label: 'Notas Fiscais', Icon: ScrollText },
      { to: '/backoffice/despesas', label: 'Despesas', Icon: Receipt },
      { to: '/fiscal/visao', label: 'Visão Fiscal', Icon: TrendingUp },
      { to: '/fiscal/decisao', label: 'Decisão Tributária', Icon: BarChart3 },
      { to: '/fiscal/config', label: 'Config Fiscal', Icon: Settings },
    ],
  },
  {
    label: 'SISTEMA',
    items: [
      { to: '/configuracoes', label: 'Configurações', Icon: Settings },
    ],
  },
]

// Mapa de rota do BACKOFFICE → chave de permissão em usuario.acessos_backoffice
const BACKOFFICE_ACCESS_KEY: Record<string, keyof NonNullable<import('../api/usuarios').AcessosBackoffice>> = {
  '/financeiro': 'financeiro',
  '/reembolsos': 'reembolsos',
  '/fiscal': 'notas_fiscais',
  '/backoffice/despesas': 'despesas',
  '/fiscal/visao': 'visao_fiscal',
  '/fiscal/decisao': 'decisao',
  '/fiscal/config': 'config_fiscal',
}

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/clientes': 'Clientes',
  '/processos': 'Processos',
  '/prazos': 'Prazos',
  '/diario': 'Diário Oficial',
  '/diario2': 'Recorte Digital OAB',
  '/teses': 'Teses IA',
  '/jurisprudencia': 'Jurisprudência',
  '/contratos': 'Contratos',
  '/organizador': 'Folder Organizer',
  '/reembolsos': 'Reembolsos',
  '/financeiro': 'Financeiro',
  '/pagantes': 'Pagantes',
  '/fiscal': 'Notas Fiscais',
  '/fiscal/visao': 'Visão Fiscal',
  '/fiscal/decisao': 'Decisão Tributária',
  '/fiscal/config': 'Config Fiscal',
  '/backoffice/despesas': 'Despesas',
  '/atendimentos': 'Atendimentos',
  '/tarefas': 'Tarefas',
  '/tarefas-cards': 'Tarefas Cards',
  '/reunioes': 'Reuniões',
  '/conselho': 'Expansão',
  '/instagram': 'Instagram',
  '/configuracoes': 'Configurações',
}


function Topbar({ onMenuToggle }: { onMenuToggle: () => void }) {
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] ?? PAGE_TITLES['/' + location.pathname.split('/')[1]] ?? 'Sui'
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
  const { usuario } = useAuth()

  const isSuperAdmin = usuario?.role === 'super_admin'
  const acessos = usuario?.acessos_backoffice ?? null

  function podeVer(to: string): boolean {
    const key = BACKOFFICE_ACCESS_KEY[to]
    if (!key) return true  // não é item de backoffice — visível
    if (isSuperAdmin) return true
    if (!acessos) return false
    return acessos[key] === true
  }

  return (
    <div className={styles.shell}>
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
          {navGroups.map((group) => {
            const visibleItems = group.items.filter(item => podeVer(item.to))
            if (visibleItems.length === 0) return null
            return (
              <div key={group.label} className={styles.navGroup}>
                <span className={styles.navGroupLabel}>{group.label}</span>

                {visibleItems.map(({ to, label, Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end
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
            )
          })}
        </div>

        <div className={styles.sidebarFooter}>Sui v1.0</div>
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
