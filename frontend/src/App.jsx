import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { Home, History, BarChart2, FlaskConical, Settings } from 'lucide-react'
import clsx from 'clsx'

import Dashboard from './pages/Dashboard.jsx'
import SignalHistory from './pages/SignalHistory.jsx'
import Performance from './pages/Performance.jsx'
import Backtest from './pages/Backtest.jsx'
import SettingsPage from './pages/Settings.jsx'

const NAV_ITEMS = [
  { path: '/',           label: 'Home',        Icon: Home },
  { path: '/history',    label: 'Signals',     Icon: History },
  { path: '/performance',label: 'Stats',       Icon: BarChart2 },
  { path: '/backtest',   label: 'Backtest',    Icon: FlaskConical },
  { path: '/settings',   label: 'Settings',    Icon: Settings },
]

function BottomNav() {
  const location = useLocation()

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-bg-secondary/95 backdrop-blur-md border-t border-border-primary pb-safe">
      <div className="flex items-center justify-around px-2 py-1 max-w-md mx-auto">
        {NAV_ITEMS.map(({ path, label, Icon }) => {
          const isActive = path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)
          return (
            <NavLink
              key={path}
              to={path}
              className={clsx(
                'flex flex-col items-center gap-0.5 py-2 px-3 rounded-xl transition-all duration-150',
                isActive ? 'text-brand-green' : 'text-text-muted hover:text-text-secondary'
              )}
            >
              <Icon size={20} strokeWidth={isActive ? 2.5 : 1.8} />
              <span className={clsx('text-[10px] font-medium', isActive ? 'text-brand-green' : 'text-text-muted')}>
                {label}
              </span>
            </NavLink>
          )
        })}
      </div>
    </nav>
  )
}

// Desktop sidebar for larger screens
function SideNav() {
  const location = useLocation()

  return (
    <aside className="hidden lg:flex flex-col w-56 h-screen fixed left-0 top-0 bg-bg-secondary border-r border-border-primary p-4 z-50">
      {/* Logo */}
      <div className="flex items-center gap-2.5 mb-8 px-2">
        <div className="w-8 h-8 bg-brand-green/15 rounded-lg flex items-center justify-center">
          <span className="text-brand-green font-bold text-sm">M</span>
        </div>
        <div>
          <div className="text-sm font-bold text-text-primary">Mirror Trade</div>
          <div className="text-[10px] text-text-muted">Bank Nifty AI</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ path, label, Icon }) => {
          const isActive = path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)
          return (
            <NavLink
              key={path}
              to={path}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all',
                isActive
                  ? 'bg-brand-green/10 text-brand-green'
                  : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
              )}
            >
              <Icon size={18} strokeWidth={isActive ? 2.5 : 1.8} />
              {label}
            </NavLink>
          )
        })}
      </nav>

      <div className="mt-auto px-2">
        <div className="text-[10px] text-text-muted text-center">
          Mirror Trade AI v1.0.0
        </div>
      </div>
    </aside>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg-primary">
        <SideNav />

        {/* Main content — shifted right on desktop */}
        <main className="lg:ml-56 min-h-screen">
          <Routes>
            <Route path="/"            element={<Dashboard />} />
            <Route path="/history"     element={<SignalHistory />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/backtest"    element={<Backtest />} />
            <Route path="/settings"    element={<SettingsPage />} />
          </Routes>
        </main>

        {/* Mobile bottom nav */}
        <div className="lg:hidden">
          <BottomNav />
        </div>
      </div>
    </BrowserRouter>
  )
}
