import React, { useState, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowRight, ArrowLeft, CheckCircle2, RotateCcw, Camera, Fingerprint } from 'lucide-react'
import { applicationsAPI, verificationAPI, uploadSelfieBlob } from '@/api/services'
import { useOnboardingStore } from '@/store/onboardingStore'
import { getErrorMessage } from '@/api/client'
import { Alert, Card, Field, Input, Select, Steps, Spinner } from '@/components/ui'
import type { CustomerProfileRequest, FingerprintResult } from '@/types/api'
import { PROFESSION_OPTIONS, BUSINESS_ACTIVITY_OPTIONS } from '@/constants/riskCategories'

type AgentStep = 'create' | 'nid' | 'fingerprint' | 'face_match' | 'profile' | 'submitted'

const AGENT_STEPS = [
  { key: 'nid', label: 'NID' },
  { key: 'fingerprint', label: 'Fingerprint' },
  { key: 'profile', label: 'Profile' },
]

export default function AgentOnboardingPage() {
  const { appId: urlAppId } = useParams<{ appId?: string }>()
  const navigate = useNavigate()
  const store = useOnboardingStore()

  const [step, setStep] = useState<AgentStep>(urlAppId ? 'nid' : 'create')
  const [appId, setAppId] = useState(urlAppId ?? store.application?.id ?? '')
  const [customerMobile, setCustomerMobile] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [usedFallback, setUsedFallback] = useState(false)

  const visibleStepIndex = AGENT_STEPS.findIndex(s => s.key === step)

  // ── Step 1: Create Application ─────────────────────────────────────────────
  function CreateStep() {
    const [mobile, setMobile] = useState(customerMobile)

    async function handle() {
      if (!mobile) return
      setLoading(true); setError('')
      try {
        const res = await applicationsAPI.agentCreate(
          { kyc_type: 'simplified', onboarding_channel: 'assisted', product_type: 'bo_account' },
          mobile
        )
        if (res.data.data) {
          store.setApplication(res.data.data)
          store.setOnboardingChannel('assisted')
          setAppId(res.data.data.id)
          setCustomerMobile(mobile)
          setStep('nid')
        }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Assisted Onboarding</h2>
          <p className="text-sm text-surface-500 mt-1">Create a new KYC application for the customer</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
        <Field label="Customer Mobile Number" required>
          <Input
            placeholder="e.g. 01700000000"
            value={mobile}
            onChange={e => setMobile(e.target.value)}
          />
        </Field>
        <button
          className="btn-primary w-full"
          onClick={handle}
          disabled={loading || !mobile}
        >
          {loading ? <Spinner size="sm" /> : <><span>Create Application</span><ArrowRight className="h-4 w-4" /></>}
        </button>
      </div>
    )
  }

  // ── Step 2: NID ────────────────────────────────────────────────────────────
  function NIDStep() {
    const [nid, setNid] = useState(store.nidRecord?.nid_number ?? '')
    const [dob, setDob] = useState(store.nidRecord?.date_of_birth ?? '')

    async function handle() {
      if (!nid || !dob || !appId) return
      setLoading(true); setError('')
      try {
        const res = await verificationAPI.validateNID(appId, { nid_number: nid, date_of_birth: dob })
        if (res.data.data) {
          store.setNIDRecord(res.data.data)
          setStep('fingerprint')
        }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">NID Verification</h2>
          <p className="text-sm text-surface-500 mt-1">Validate customer's National Identity Card</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
        {store.nidRecord && (
          <Alert variant="success">NID verified — <strong>{store.nidRecord.full_name_en}</strong></Alert>
        )}
        <Field label="NID Number" required>
          <Input placeholder="10–17 digit NID number" value={nid} onChange={e => setNid(e.target.value)} />
        </Field>
        <Field label="Date of Birth" required>
          <Input type="date" value={dob} onChange={e => setDob(e.target.value)} />
        </Field>
        <div className="flex gap-3">
          {!urlAppId && (
            <button onClick={() => setStep('create')} className="btn-secondary flex-1">
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
          )}
          <button onClick={handle} className="btn-primary flex-1" disabled={loading || !nid || !dob}>
            {loading ? <Spinner size="sm" /> : <><span>Validate NID</span><ArrowRight className="h-4 w-4" /></>}
          </button>
        </div>
      </div>
    )
  }

  // ── Step 3: Fingerprint ────────────────────────────────────────────────────
  function FingerprintStep() {
    const [fingerPosition, setFingerPosition] = useState('right_index')
    const [template, setTemplate] = useState('')
    const [result, setResult] = useState<FingerprintResult | null>(null)
    const [exhausted, setExhausted] = useState(false)
    const [fpLoading, setFpLoading] = useState(false)
    const [fpError, setFpError] = useState('')

    async function handleSubmit() {
      if (!appId || !store.nidRecord || !template) return
      setFpLoading(true); setFpError(''); setResult(null)
      try {
        const res = await verificationAPI.fingerprint(appId, {
          nid_number: store.nidRecord.nid_number,
          fingerprint_template: template,
          finger_position: fingerPosition,
          date_of_birth: store.nidRecord.date_of_birth,
        })
        if (res.data.data) {
          const r = res.data.data
          store.setFingerprintResult(r)
          setResult(r)
        }
      } catch (err: any) {
        if (err?.response?.status === 429) {
          setExhausted(true)
        } else {
          setFpError(getErrorMessage(err))
        }
      } finally { setFpLoading(false) }
    }

    const attemptLabel = result
      ? `Session ${result.session_number} — Attempt ${result.attempt_number} of 10`
      : 'Session 1 — Attempt 1 of 10'

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Fingerprint Verification</h2>
          <p className="text-sm text-surface-500 mt-1">Scan customer fingerprint against EC database</p>
        </div>
        <p className="text-xs text-surface-400 font-mono">{attemptLabel}</p>

        {fpError && <Alert variant="error" onDismiss={() => setFpError('')}>{fpError}</Alert>}

        {exhausted && (
          <Alert variant="error">
            Maximum sessions reached. Offer traditional paper KYC.
          </Alert>
        )}

        {result?.matched && (
          <Alert variant="success">
            Fingerprint matched — similarity {result.similarity_score?.toFixed(1)}%
          </Alert>
        )}

        {result && !result.matched && !result.suggest_face_fallback && (
          <Alert variant="error">
            Fingerprint did not match (score: {result.similarity_score?.toFixed(1)}%). Please retry.
          </Alert>
        )}

        {result && !result.matched && result.suggest_face_fallback && (
          <Alert variant="warning">
            {result.fallback_message ?? 'Fingerprint sessions exhausted. Switching to face match as required by BFIU guidelines.'}
          </Alert>
        )}

        {!exhausted && (
          <>
            <Field label="Finger Position">
              <Select value={fingerPosition} onChange={e => setFingerPosition(e.target.value)}>
                <option value="right_thumb">Right Thumb</option>
                <option value="right_index">Right Index</option>
                <option value="right_middle">Right Middle</option>
                <option value="right_ring">Right Ring</option>
                <option value="right_little">Right Little</option>
                <option value="left_thumb">Left Thumb</option>
                <option value="left_index">Left Index</option>
                <option value="left_middle">Left Middle</option>
                <option value="left_ring">Left Ring</option>
                <option value="left_little">Left Little</option>
              </Select>
            </Field>
            <Field label="Fingerprint Template (Base64)">
              <textarea
                className="input font-mono text-xs resize-none"
                rows={3}
                placeholder="Paste base64-encoded fingerprint template here"
                value={template}
                onChange={e => setTemplate(e.target.value)}
              />
            </Field>
            <button
              className="btn-secondary w-full"
              onClick={() => setTemplate(btoa('mock-fp-scan-' + Date.now()))}
            >
              Simulate Scan
            </button>
          </>
        )}

        <div className="flex flex-col gap-3">
          {result?.matched && (
            <button className="btn-primary w-full" onClick={() => setStep('profile')}>
              <span>Continue</span><ArrowRight className="h-4 w-4" />
            </button>
          )}
          {result && !result.matched && !result.suggest_face_fallback && !exhausted && (
            <button className="btn-secondary w-full" onClick={() => { setTemplate(''); setResult(null) }}>
              <RotateCcw className="h-4 w-4" /> Retry
            </button>
          )}
          {result && !result.matched && result.suggest_face_fallback && (
            <button className="btn-primary w-full" onClick={() => { setUsedFallback(true); setStep('face_match') }}>
              Switch to Face Match
            </button>
          )}
          {!exhausted && !result?.matched && (
            <button
              className="btn-primary w-full"
              onClick={handleSubmit}
              disabled={fpLoading || !template}
            >
              {fpLoading ? <Spinner size="sm" /> : <><span>Submit Fingerprint</span><ArrowRight className="h-4 w-4" /></>}
            </button>
          )}
          <button onClick={() => setStep('nid')} className="btn-ghost w-full text-sm">
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
        </div>
      </div>
    )
  }

  // ── Step 3b: Face Match Fallback ───────────────────────────────────────────
  function FaceMatchStep() {
    const videoRef = useRef<HTMLVideoElement>(null)
    const [stream, setStream] = useState<MediaStream | null>(null)
    const [captured, setCaptured] = useState<string | null>(null)
    const [cameraError, setCameraError] = useState('')

    const startCamera = useCallback(async () => {
      setCameraError('')
      try {
        const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 640, height: 480 } })
        setStream(s)
        if (videoRef.current) videoRef.current.srcObject = s
      } catch { setCameraError('Camera access denied. Please allow camera access.') }
    }, [])

    function stopCamera() { stream?.getTracks().forEach(t => t.stop()); setStream(null) }

    function capture() {
      if (!videoRef.current) return
      const canvas = document.createElement('canvas')
      canvas.width = videoRef.current.videoWidth
      canvas.height = videoRef.current.videoHeight
      canvas.getContext('2d')?.drawImage(videoRef.current, 0, 0)
      setCaptured(canvas.toDataURL('image/jpeg', 0.85))
      stopCamera()
    }

    const [loadingLabel, setLoadingLabel] = useState('')

    async function handle() {
      if (!appId || !store.nidRecord || !captured) return
      setLoading(true); setError('')
      try {
        setLoadingLabel('Uploading selfie…')
        let storage_key = `selfies/${appId}-${Date.now()}.jpg`
        try {
          const urlRes = await verificationAPI.getSelfieUploadUrl(appId)
          if (urlRes.data.data) {
            const { upload_url, storage_key: key } = urlRes.data.data
            const blob = await fetch(captured).then(r => r.blob())
            await uploadSelfieBlob(upload_url, blob)
            storage_key = key
          }
        } catch { /* storage unavailable in dev — proceed with generated key */ }

        setLoadingLabel('Verifying…')
        const res = await verificationAPI.faceMatch(appId, {
          nid_number: store.nidRecord.nid_number,
          selfie_storage_key: storage_key,
          date_of_birth: store.nidRecord.date_of_birth,
        })
        if (res.data.data) {
          store.setFaceMatchResult(res.data.data)
          if (res.data.data.matched) setStep('profile')
          else setError(`Face match failed (score: ${res.data.data.similarity_score?.toFixed(1)}%). Please try again.`)
        }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Face Verification (Fallback)</h2>
          <p className="text-sm text-surface-500 mt-1">Fingerprint sessions exhausted — verifying via face match per BFIU guidelines</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
        {cameraError && <Alert variant="warning">{cameraError}</Alert>}

        {store.faceMatchResult?.matched && (
          <Alert variant="success">Face matched — similarity {store.faceMatchResult.similarity_score?.toFixed(1)}%</Alert>
        )}

        <div className="bg-surface-900 rounded-xl overflow-hidden aspect-video flex items-center justify-center relative">
          {stream ? (
            <>
              <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-48 h-60 border-2 border-white/50 rounded-full" />
              </div>
            </>
          ) : captured ? (
            <img src={captured} alt="Captured selfie" className="w-full h-full object-cover" />
          ) : (
            <div className="text-center text-white/60 p-8">
              <Camera className="h-12 w-12 mx-auto mb-3 opacity-40" />
              <p className="text-sm">Camera preview will appear here</p>
            </div>
          )}
        </div>

        <div className="flex gap-3">
          {!stream && !captured && (
            <button onClick={startCamera} className="btn-secondary flex-1"><Camera className="h-4 w-4" /> Open Camera</button>
          )}
          {stream && (
            <button onClick={capture} className="btn-primary flex-1"><Camera className="h-4 w-4" /> Capture</button>
          )}
          {captured && (
            <button onClick={() => { setCaptured(null); startCamera() }} className="btn-secondary flex-1"><RotateCcw className="h-4 w-4" /> Retake</button>
          )}
          {captured && (
            <button onClick={handle} className="btn-primary flex-1" disabled={loading}>
              {loading ? <><Spinner size="sm" /><span className="ml-2 text-sm">{loadingLabel}</span></> : <><span>Verify Face</span><ArrowRight className="h-4 w-4" /></>}
            </button>
          )}
        </div>

        <div className="flex gap-3">
          <button onClick={() => setStep('fingerprint')} className="btn-ghost w-full text-sm"><ArrowLeft className="h-4 w-4" /> Back</button>
          {store.faceMatchResult?.matched && (
            <button onClick={() => setStep('profile')} className="btn-primary flex-1"><span>Continue</span><ArrowRight className="h-4 w-4" /></button>
          )}
        </div>
      </div>
    )
  }

  // ── Step 4: Profile (abbreviated) ─────────────────────────────────────────
  function ProfileStep() {
    const nid = store.nidRecord
    const [form, setForm] = useState<Partial<CustomerProfileRequest>>({
      full_name_en: nid?.full_name_en ?? '',
      mobile_number: '',
      profession: '',
      source_of_fund: undefined,
      nationality: 'Bangladeshi',
      residency_status: 'resident_bangladeshi',
      is_pep: false, is_ip: false, is_nrb: false,
    })

    function setField(k: keyof CustomerProfileRequest, v: any) { setForm(f => ({ ...f, [k]: v })) }

    async function handle() {
      if (!appId) return
      setLoading(true); setError('')
      try {
        await applicationsAPI.saveProfile(appId, form as CustomerProfileRequest)
        store.markProfileSaved()
        await applicationsAPI.submit(appId)
        setStep('submitted')
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Customer Profile</h2>
          <p className="text-sm text-surface-500 mt-1">Complete the required profile fields</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

        <Field label="Full Name (English)" required>
          <Input value={form.full_name_en ?? ''} onChange={e => setField('full_name_en', e.target.value)} />
        </Field>
        <Field label="Mobile Number" required>
          <Input placeholder="01700000000" value={form.mobile_number ?? ''} onChange={e => setField('mobile_number', e.target.value)} />
        </Field>
        <Field label="Profession">
          <Select value={form.profession ?? ''} onChange={e => setField('profession', e.target.value || undefined)}>
            <option value="">Select...</option>
            {PROFESSION_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
        </Field>
        <Field label="Business Activity">
          <Select value={form.business_activity ?? ''} onChange={e => setField('business_activity', e.target.value || undefined)}>
            <option value="">Select (if applicable)...</option>
            {BUSINESS_ACTIVITY_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
        </Field>
        <Field label="Source of Fund">
          <Select value={form.source_of_fund ?? ''} onChange={e => setField('source_of_fund', e.target.value || undefined)}>
            <option value="">Select source</option>
            <option value="salary">Salary</option>
            <option value="business_income">Business Income</option>
            <option value="investment">Investment</option>
            <option value="inheritance">Inheritance</option>
            <option value="remittance">Remittance</option>
            <option value="other">Other</option>
          </Select>
        </Field>

        <div className="flex gap-3">
          <button onClick={() => setStep(usedFallback ? 'face_match' : 'fingerprint')} className="btn-secondary flex-1">
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
          <button
            onClick={handle}
            className="btn-primary flex-1"
            disabled={loading || !form.full_name_en || !form.mobile_number}
          >
            {loading ? <Spinner size="sm" /> : <><span>Save & Submit</span><ArrowRight className="h-4 w-4" /></>}
          </button>
        </div>
      </div>
    )
  }

  // ── Submitted ──────────────────────────────────────────────────────────────
  if (step === 'submitted') {
    return (
      <div className="p-6 max-w-lg mx-auto">
        <Card className="p-8 text-center space-y-4">
          <div className="w-14 h-14 bg-success/10 rounded-full flex items-center justify-center mx-auto">
            <CheckCircle2 className="h-8 w-8 text-success" />
          </div>
          <h2 className="text-lg font-semibold text-surface-900">Application Submitted</h2>
          <p className="text-sm text-surface-500">The customer's assisted eKYC application has been submitted for review.</p>
          <p className="text-sm font-mono bg-surface-50 rounded-lg px-4 py-2 text-surface-700">{store.application?.application_ref}</p>
          <button
            onClick={() => { store.reset(); navigate('/agent/queue') }}
            className="btn-primary w-full"
          >
            Back to Queue
          </button>
        </Card>
      </div>
    )
  }

  const stepComponents: Record<AgentStep, React.ReactElement> = {
    create: <CreateStep />,
    nid: <NIDStep />,
    fingerprint: <FingerprintStep />,
    face_match: <FaceMatchStep />,
    profile: <ProfileStep />,
    submitted: <></>,
  }

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Fingerprint className="h-6 w-6 text-brand-600" />
        <div>
          <h1 className="page-title">Assist Customer</h1>
          <p className="text-sm text-surface-500 mt-0.5">Assisted onboarding — fingerprint verification</p>
        </div>
      </div>

      {step !== 'create' && (
        <div className="overflow-x-auto pb-2">
          <Steps
            steps={AGENT_STEPS}
            current={Math.max(0, visibleStepIndex)}
          />
        </div>
      )}

      <Card className="p-8">
        {stepComponents[step]}
      </Card>
    </div>
  )
}
