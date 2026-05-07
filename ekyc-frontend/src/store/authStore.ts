import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ActorType = 'customer' | 'agent' | null

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  actorType: ActorType
  mobileNumber: string | null
  employeeId: string | null
  agentRole: string | null
  isAuthenticated: boolean

  setCustomerTokens: (access: string, refresh: string, mobile: string) => void
  setAgentTokens:    (access: string, refresh: string, employeeId: string, role: string) => void
  clearAuth:         () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      actorType: null,
      mobileNumber: null,
      employeeId: null,
      agentRole: null,
      isAuthenticated: false,

      setCustomerTokens: (access, refresh, mobile) => {
        localStorage.setItem('access_token', access)
        set({ accessToken: access, refreshToken: refresh, mobileNumber: mobile, actorType: 'customer', isAuthenticated: true })
      },

      setAgentTokens: (access, refresh, employeeId, role) => {
        localStorage.setItem('access_token', access)
        set({ accessToken: access, refreshToken: refresh, employeeId, agentRole: role, actorType: 'agent', isAuthenticated: true })
      },

      clearAuth: () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({ accessToken: null, refreshToken: null, actorType: null, mobileNumber: null, employeeId: null, agentRole: null, isAuthenticated: false })
      },
    }),
    { name: 'ekyc-auth', partialize: (s) => ({ accessToken: s.accessToken, refreshToken: s.refreshToken, actorType: s.actorType, mobileNumber: s.mobileNumber, employeeId: s.employeeId, agentRole: s.agentRole, isAuthenticated: s.isAuthenticated }) }
  )
)
