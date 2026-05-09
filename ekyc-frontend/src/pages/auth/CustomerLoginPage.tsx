import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, ArrowRight, Phone, Mail } from 'lucide-react'
import { authAPI } from '@/api/services'
import { useAuthStore } from '@/store/authStore'
import { useOnboardingStore } from '@/store/onboardingStore'
import { getErrorMessage } from '@/api/client'
import { Alert, OTPInput, Input, Field, Spinner } from '@/components/ui'

type Step = 'phone' | 'otp'

export default function CustomerLoginPage() {
  const navigate = useNavigate()
  const { setCustomerTokens } = useAuthStore()
  const resetOnboarding = useOnboardingStore(s => s.reset)

  const [step, setStep] = useState<Step>('phone')
  const [mobile, setMobile] = useState('')
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [countdown, setCountdown] = useState(0)

  function startCountdown(sec: number) {
    setCountdown(sec)
    const t = setInterval(() => {
      setCountdown(c => { if (c <= 1) { clearInterval(t); return 0 } return c - 1 })
    }, 1000)
  }

  async function handleSendOTP(e: React.FormEvent) {
    e.preventDefault()
    if (!mobile.trim()) { setError('Mobile number is required'); return }
    setLoading(true); setError('')
    try {
      const res = await authAPI.sendOTP({ mobile_number: mobile.trim(), email: email || undefined })
      if (res.data.success) {
        setStep('otp')
        startCountdown(res.data.data?.expires_in_seconds ?? 300)
      }
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleVerifyOTP() {
    if (otp.length < 6) { setError('Enter the complete 6-digit OTP'); return }
    setLoading(true); setError('')
    try {
      const res = await authAPI.verifyOTP({ mobile_number: mobile, otp, device_fingerprint: 'web-browser' })
      if (res.data.success && res.data.data) {
        setCustomerTokens(res.data.data.access_token, res.data.data.refresh_token, mobile)
        resetOnboarding()
        navigate('/onboarding')
      }
    } catch (err) {
      setError(getErrorMessage(err))
      setOtp('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-950 via-brand-900 to-brand-800 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white/10 rounded-2xl backdrop-blur mb-4">
            <ShieldCheck className="h-9 w-9 text-white" />
          </div>
          <h1 className="text-2xl font-semibold text-white">eKYC Portal</h1>
          <p className="text-brand-300 text-sm mt-1">Bangladesh Capital Market & Insurance</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-modal p-8 animate-slide-up">
          {step === 'phone' ? (
            <>
              <h2 className="text-lg font-semibold text-surface-900 mb-1">Customer Sign In</h2>
              <p className="text-sm text-surface-500 mb-6">Enter your mobile number to receive an OTP</p>

              {error && <Alert variant="error" className="mb-4" onDismiss={() => setError('')}>{error}</Alert>}

              <form onSubmit={handleSendOTP} className="space-y-4">
                <Field label="Mobile Number" required>
                  <div className="relative">
                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-surface-400" />
                    <Input
                      type="tel"
                      placeholder="+8801XXXXXXXXX"
                      value={mobile}
                      onChange={e => setMobile(e.target.value)}
                      className="pl-9"
                      required
                    />
                  </div>
                </Field>

                <Field label="Email (optional)">
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-surface-400" />
                    <Input
                      type="email"
                      placeholder="your@email.com"
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      className="pl-9"
                    />
                  </div>
                </Field>

                <button type="submit" className="btn-primary w-full btn-lg mt-2" disabled={loading}>
                  {loading ? <Spinner size="sm" /> : <><span>Send OTP</span><ArrowRight className="h-4 w-4" /></>}
                </button>
              </form>

              <p className="text-center text-xs text-surface-400 mt-6">
                Are you an agent?{' '}
                <a href="/agent/login" className="text-brand-600 hover:underline font-medium">Sign in here</a>
              </p>
            </>
          ) : (
            <>
              <button onClick={() => { setStep('phone'); setOtp(''); setError('') }} className="text-sm text-brand-600 hover:underline mb-4 flex items-center gap-1">
                ← Change number
              </button>
              <h2 className="text-lg font-semibold text-surface-900 mb-1">Enter OTP</h2>
              <p className="text-sm text-surface-500 mb-2">
                Sent to <span className="font-medium text-surface-700">{mobile}</span>
              </p>
              {countdown > 0 && (
                <p className="text-xs text-brand-600 mb-6">Expires in {Math.floor(countdown / 60)}:{String(countdown % 60).padStart(2, '0')}</p>
              )}

              {error && <Alert variant="error" className="mb-4" onDismiss={() => setError('')}>{error}</Alert>}

              <div className="mb-6">
                <OTPInput value={otp} onChange={setOtp} />
              </div>

              <button className="btn-primary w-full btn-lg" onClick={handleVerifyOTP} disabled={loading || otp.length < 6}>
                {loading ? <Spinner size="sm" /> : <><span>Verify & Continue</span><ArrowRight className="h-4 w-4" /></>}
              </button>

              <div className="text-center mt-4">
                <button
                  className="text-sm text-surface-500 hover:text-brand-600 transition-colors"
                  disabled={countdown > 0}
                  onClick={() => { setStep('phone'); setOtp('') }}
                >
                  {countdown > 0 ? `Resend in ${countdown}s` : 'Resend OTP'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
