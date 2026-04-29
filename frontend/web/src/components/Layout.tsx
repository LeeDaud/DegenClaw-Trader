import { Link, useLocation } from 'react-router-dom'
import { Activity, Users, Coins, FileText, BarChart3, AlertTriangle } from 'lucide-react'

const navItems = [
  { path: '/', label: 'Dashboard', icon: BarChart3 },
  { path: '/agents', label: 'Agents', icon: Users },
  { path: '/tokens', label: 'Tokens', icon: Coins },
  { path: '/alerts', label: 'Alerts', icon: AlertTriangle },
  { path: '/logs', label: 'Logs', icon: FileText },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="border-b border-gray-800 bg-gray-900/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 flex items-center h-14 gap-6">
          <Link to="/" className="flex items-center gap-2 text-emerald-400 font-bold text-lg">
            <Activity size={22} />
            <span>DegenClaw</span>
          </Link>
          <div className="flex gap-1 ml-4">
            {navItems.map((item) => {
              const active = location.pathname === item.path
              const Icon = item.icon
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                    active
                      ? 'bg-emerald-500/10 text-emerald-400'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                  }`}
                >
                  <Icon size={16} />
                  {item.label}
                </Link>
              )
            })}
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
    </div>
  )
}
