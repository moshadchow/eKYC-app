import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import AppShell from '@/components/layout/AppShell'

// Auth
import CustomerLoginPage from '@/pages/auth/CustomerLoginPage'
import AgentLoginPage from '@/pages/auth/AgentLoginPage'

// Onboarding
import OnboardingPage from '@/pages/onboarding/OnboardingPage'

// Agent
import AgentQueuePage from '@/pages/agent/AgentQueuePage'
import CompliancePage from '@/pages/agent/CompliancePage'

// Admin
import AuditPage from '@/pages/admin/AuditPage'

function RequireAuth({ children, role }: { children: React.ReactElement; role?: 'customer' | 'agent' }) {
  const { isAuthenticated, actorType } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (role && actorType !== role) return <Navigate to={actorType === 'agent' ? '/agent/dashboard' : '/onboarding'} replace />
  return children
}

export default function AppRouter() {
  const { isAuthenticated, actorType } = useAuthStore()

  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<CustomerLoginPage />} />
      <Route path="/agent/login" element={<AgentLoginPage />} />

      {/* Root redirect */}
      <Route path="/" element={
        !isAuthenticated ? <Navigate to="/login" /> :
        actorType === 'agent' ? <Navigate to="/agent/dashboard" /> :
        <Navigate to="/onboarding" />
      } />

      {/* Customer */}
      <Route element={<RequireAuth role="customer"><AppShell /></RequireAuth>}>
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>

      {/* Agent */}
      <Route element={<RequireAuth role="agent"><AppShell /></RequireAuth>}>
        <Route path="/agent/dashboard" element={<AgentQueuePage />} />
        <Route path="/agent/queue" element={<AgentQueuePage />} />
        <Route path="/agent/compliance/:appId" element={<CompliancePage />} />
        <Route path="/admin/queue" element={<AgentQueuePage />} />
        <Route path="/admin/audit" element={<AuditPage />} />
        <Route path="/admin/lifecycle" element={<div className="p-6 text-surface-500">KYC Lifecycle — coming in next step</div>} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
