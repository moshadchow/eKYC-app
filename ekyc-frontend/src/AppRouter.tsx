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
import AgentOnboardingPage from '@/pages/agent/AgentOnboardingPage'

// Customer
import CustomerLifecyclePage from '@/pages/customer/CustomerLifecyclePage'
import NotificationHistoryPage from '@/pages/customer/NotificationHistoryPage'

// Admin
import AuditPage from '@/pages/admin/AuditPage'
import LifecyclePage from '@/pages/admin/LifecyclePage'
import NotificationQueuePage from '@/pages/admin/NotificationQueuePage'

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
        <Route path="/lifecycle" element={<CustomerLifecyclePage />} />
        <Route path="/notifications" element={<NotificationHistoryPage />} />
      </Route>

      {/* Agent */}
      <Route element={<RequireAuth role="agent"><AppShell /></RequireAuth>}>
        <Route path="/agent/dashboard" element={<AgentQueuePage />} />
        <Route path="/agent/queue" element={<AgentQueuePage />} />
        <Route path="/agent/compliance/:appId" element={<CompliancePage />} />
        <Route path="/agent/onboarding/:appId?" element={<AgentOnboardingPage />} />
        <Route path="/admin/queue" element={<AgentQueuePage />} />
        <Route path="/admin/audit" element={<AuditPage />} />
        <Route path="/admin/lifecycle" element={<LifecyclePage />} />
        <Route path="/admin/notifications" element={<NotificationQueuePage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
