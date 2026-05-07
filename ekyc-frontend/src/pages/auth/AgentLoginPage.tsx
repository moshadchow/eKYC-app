import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, ArrowRight, User, Lock } from 'lucide-react'
import { agentAuthAPI } from '@/api/services'
import { useAuthStore } from '@/store/authStore'
import { getErrorMessage } from '@/api/client'
import { Alert, OTPInput, Input, Field, Spinner } from '@/components/ui'

type Step = 'credentials' | 'otp'

export default function AgentLoginPage() {
  const navigate = useNavigate()
  const { setAgentTokens } = useAuthStore()

  const [step, setStep] = useState<Step>('credentials')
  const [employeeId, setEmployeeId] = useState('')
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      await agentAuthAPI.login({
        employee_id: employeeId.trim(),
        password,
        device_fingerprint: 'web-browser-agent',
      })
      setStep('otp')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify2FA() {
    if (otp.length < 6) return
    setLoading(true); setError('')
    try {
      const res = await agentAuthAPI.verify2FA({
        employee_id: employeeId,
        otp,
        device_fingerprint: 'web-browser-agent',
      })
      if (res.data.success && res.data.data) {
        // Fetch agent profile for role
        const meRes = await agentAuthAPI.me()
        const role = meRes.data.data?.role ?? 'maker'
        setAgentTokens(res.data.data.access_token, res.data.data.refresh_token, employeeId, role)
        navigate('/agent/dashboard')
      }
    } catch (err) {
      setError(getErrorMessage(err))
      setOtp('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-surface-900 via-surface-800 to-surface-700 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white/10 rounded-2xl backdrop-blur mb-4">
            <ShieldCheck className="h-9 w-9 text-white" />
          </div>
          <h1 className="text-2xl font-semibold text-white">Agent Portal</h1>
          <p className="text-surface-400 text-sm mt-1">eKYC Onboarding Platform</p>
        </div>

        <div className="bg-white rounded-2xl shadow-modal p-8 animate-slide-up">
          {step === 'credentials' ? (
            <>
              <h2 className="text-lg font-semibold text-surface-900 mb-1">Agent Sign In</h2>
              <p className="text-sm text-surface-500 mb-6">Enter your credentials to continue</p>

              {error && <Alert variant="error" className="mb-4" onDismiss={() => setError('')}>{error}</Alert>}

              <form onSubmit={handleLogin} className="space-y-4">
                <Field label="Employee ID" required>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-surface-400" />
                    <Input placeholder="EMP-XXXXX" value={employeeId} onChange={e => setEmployeeId(e.target.value)} className="pl-9" required />
                  </div>
                </Field>
                <Field label="Password" required>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-surface-400" />
                    <Input type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} className="pl-9" required />
                  </div>
                </Field>
                <button type="submit" className="btn-primary w-full btn-lg mt-2" disabled={loading}>
                  {loading ? <Spinner size="sm" /> : <><span>Continue</span><ArrowRight className="h-4 w-4" /></>}
                </button>
              </form>

              <p className="text-center text-xs text-surface-400 mt-6">
                Customer?{' '}
                <a href="/login" className="text-brand-600 hover:underline font-medium">Sign in here</a>
              </p>
            </>
          ) : (
            <>
              <button onClick={() => { setStep('credentials'); setOtp(''); setError('') }} className="text-sm text-brand-600 hover:underline mb-4">← Back</button>
              <h2 className="text-lg font-semibold text-surface-900 mb-1">Two-Factor Authentication</h2>
              <p className="text-sm text-surface-500 mb-6">Enter the OTP sent to your registered device</p>

              {error && <Alert variant="error" className="mb-4" onDismiss={() => setError('')}>{error}</Alert>}

              <div className="mb-6"><OTPInput value={otp} onChange={setOtp} /></div>

              <button className="btn-primary w-full btn-lg" onClick={handleVerify2FA} disabled={loading || otp.length < 6}>
                {loading ? <Spinner size="sm" /> : <><span>Verify & Sign In</span><ArrowRight className="h-4 w-4" /></>}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
