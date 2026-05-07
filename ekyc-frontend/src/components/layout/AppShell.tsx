import React from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  ShieldCheck, FileText, LayoutDashboard, Users, Settings,
  LogOut, ClipboardList, RefreshCw, Activity, ChevronRight,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { agentAuthAPI } from '@/api/services'

const customerNav = [
  { to: '/onboarding', icon: <FileText className="h-4 w-4" />, label: 'New Application' },
]

const agentNav = [
  { to: '/agent/dashboard', icon: <LayoutDashboard className="h-4 w-4" />, label: 'Dashboard' },
  { to: '/agent/queue', icon: <ClipboardList className="h-4 w-4" />, label: 'Review Queue' },
]

const adminNav = [
  { to: '/admin/queue', icon: <ClipboardList className="h-4 w-4" />, label: 'Approval Queue' },
  { to: '/admin/audit', icon: <Activity className="h-4 w-4" />, label: 'Audit Trail' },
  { to: '/admin/lifecycle', icon: <RefreshCw className="h-4 w-4" />, label: 'KYC Lifecycle' },
]

export default function AppShell() {
  const { actorType, agentRole, mobileNumber, employeeId, clearAuth } = useAuthStore()
  const navigate = useNavigate()

  const navItems = actorType === 'customer' ? customerNav
    : (agentRole === 'system_admin' || agentRole === 'system_auditor') ? [...agentNav, ...adminNav]
    : agentNav

  async function handleLogout() {
    try {
      if (actorType === 'customer') await import('@/api/services').then(m => m.authAPI.logout())
      else await agentAuthAPI.logout()
    } catch { /* ignore */ }
    clearAuth()
    navigate('/login')
  }

  const displayName = actorType === 'customer' ? mobileNumber : employeeId

  return (
    <div className="flex h-screen bg-surface-50">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-white border-r border-surface-200 flex flex-col">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-surface-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center">
              <ShieldCheck className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="font-semibold text-surface-900 text-sm leading-tight">eKYC Portal</div>
              <div className="text-xs text-surface-400 capitalize">{actorType}</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-700 font-medium'
                    : 'text-surface-600 hover:bg-surface-50 hover:text-surface-900'
                )
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User footer */}
        <div className="px-3 py-4 border-t border-surface-100">
          <div className="flex items-center gap-3 px-3 py-2 mb-1">
            <div className="w-7 h-7 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 text-xs font-semibold">
              {displayName?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-surface-800 truncate">{displayName}</div>
              {agentRole && <div className="text-xs text-surface-400 capitalize">{agentRole.replace(/_/g, ' ')}</div>}
            </div>
          </div>
          <button onClick={handleLogout} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-surface-500 hover:bg-red-50 hover:text-danger transition-colors">
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
