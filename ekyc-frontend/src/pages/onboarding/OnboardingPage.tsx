import React, { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Camera, Upload, CheckCircle2, AlertTriangle, RotateCcw, ArrowRight, ArrowLeft, Eye, EyeOff } from 'lucide-react'
import { preCheckAPI, applicationsAPI, verificationAPI, uploadSelfieBlob, uploadFileBlob } from '@/api/services'
import { useOnboardingStore } from '@/store/onboardingStore'
import { useAuthStore } from '@/store/authStore'
import { getErrorMessage } from '@/api/client'
import { Alert, Card, Field, Input, Select, Steps, Spinner, StatusBadge } from '@/components/ui'
import type { CustomerProfileRequest, OnboardingChannelValue, FingerprintResult } from '@/types/api'
import { verificationAPI as verAPI } from '@/api/services'
import { PROFESSION_OPTIONS, BUSINESS_ACTIVITY_OPTIONS } from '@/constants/riskCategories'

export default function OnboardingPage() {
  const navigate = useNavigate()
  const store = useOnboardingStore()
  const { mobileNumber } = useAuthStore()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const isAssisted = store.onboardingChannel === 'assisted' || store.onboardingChannel === 'branch'

  const STEPS = [
    { key: 'pre_check', label: 'Pre-check' },
    { key: 'nid_capture', label: 'NID' },
    isAssisted
      ? { key: 'fingerprint', label: 'Fingerprint' }
      : { key: 'face_match', label: 'Face Match' },
    { key: 'profile', label: 'Profile' },
    { key: 'nominee', label: 'Nominee' },
    { key: 'signature', label: 'Signature' },
    { key: 'review', label: 'Review' },
  ]

  const stepIndex = STEPS.findIndex(s => s.key === store.currentStep)

  function next(step: typeof STEPS[0]['key']) { store.setStep(step as any); setError('') }
  function prev() { if (stepIndex > 0) store.setStep(STEPS[stepIndex - 1].key as any); setError('') }

  // ── Step 1: Pre-check ────────────────────────────────────────────────────
  function PreCheckStep() {
    const [productType, setProductType] = useState('bo_account')
    const [investment, setInvestment] = useState('')
    const [isPep, setIsPep] = useState(false)
    const [isIp, setIsIp] = useState(false)
    const [channel, setChannel] = useState<OnboardingChannelValue>(store.onboardingChannel ?? 'self_checkin')

    async function handle() {
      setLoading(true); setError('')
      try {
        const res = await preCheckAPI.run({
          product_type: productType as any,
          expected_investment: investment ? Number(investment) : undefined,
          is_pep: isPep, is_ip: isIp,
          residency: 'resident_bangladeshi',
        })
        if (res.data.data) {
          store.setPreCheckResult(res.data.data)
          const appRes = await applicationsAPI.create({
            kyc_type: res.data.data.kyc_type,
            onboarding_channel: channel,
            product_type: productType as any,
            expected_investment: investment ? Number(investment) : undefined,
          })
          if (appRes.data.data) {
            store.setApplication(appRes.data.data)
            store.setOnboardingChannel(channel)
            next('nid_capture')
          }
        }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Pre-Onboarding Check</h2>
          <p className="text-sm text-surface-500 mt-1">We'll determine which eKYC process applies to you</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
        {store.preCheckResult && (
          <Alert variant="info">
            Previous decision: <strong>{store.preCheckResult.decision}</strong> eKYC — {store.preCheckResult.decision_reason}
          </Alert>
        )}
        <Field label="Product Type" required>
          <Select value={productType} onChange={e => setProductType(e.target.value)}>
            <option value="bo_account">BO Account (Capital Market)</option>
            <option value="life_insurance">Life Insurance</option>
            <option value="non_life_insurance">Non-Life Insurance</option>
          </Select>
        </Field>
        <Field label="Onboarding Channel" required>
          <Select value={channel} onChange={e => setChannel(e.target.value as OnboardingChannelValue)}>
            <option value="self_checkin">Self Check-in (online)</option>
            <option value="assisted">Assisted (agent at branch)</option>
          </Select>
        </Field>
        <Field label="Expected Investment / Sum Assured (BDT)" hint="Leave blank if unknown">
          <Input type="number" placeholder="e.g. 1000000" value={investment} onChange={e => setInvestment(e.target.value)} />
        </Field>
        <div className="bg-surface-50 rounded-xl p-4 space-y-3">
          <p className="text-sm font-medium text-surface-700">Risk Declarations</p>
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={isPep} onChange={e => setIsPep(e.target.checked)} className="rounded border-surface-300 text-brand-600" />
            <span className="text-sm text-surface-600">I am a Politically Exposed Person (PEP)</span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={isIp} onChange={e => setIsIp(e.target.checked)} className="rounded border-surface-300 text-brand-600" />
            <span className="text-sm text-surface-600">I am an Influential Person (IP)</span>
          </label>
        </div>
        <button onClick={handle} className="btn-primary w-full btn-lg" disabled={loading}>
          {loading ? <Spinner size="sm" /> : <><span>Check & Continue</span><ArrowRight className="h-4 w-4" /></>}
        </button>
      </div>
    )
  }

  // ── Step 2: NID Capture (3-phase: upload → OCR → review+validate) ─────────
  function NIDStep() {
    const appId = store.application?.id ?? ''

    // Phase A local state
    const [frontPreview, setFrontPreview] = useState<string | null>(null)
    const [backPreview, setBackPreview]   = useState<string | null>(null)
    const [uploadingFront, setUploadingFront] = useState(false)
    const [uploadingBack, setUploadingBack]   = useState(false)

    // Phase B local state
    const [ocrLoading, setOcrLoading] = useState(false)
    const [ocrError, setOcrError]     = useState('')
    const [manualMode, setManualMode] = useState(false)

    // Phase C local state — pre-filled from OCR, user-editable
    const [nid, setNid] = useState(store.ocrResult?.extracted_nid ?? store.nidRecord?.nid_number ?? '')
    const [dob, setDob] = useState(store.ocrResult?.extracted_dob ?? store.nidRecord?.date_of_birth ?? '')

    // Auto-trigger OCR when both keys are set and OCR hasn't run yet
    useEffect(() => {
      if (store.nidFrontKey && store.nidBackKey && !store.ocrResult && !ocrLoading && !ocrError && !manualMode) {
        runOcr()
      }
    }, [store.nidFrontKey, store.nidBackKey])

    // Sync NID/DOB fields when OCR result arrives
    useEffect(() => {
      if (store.ocrResult) {
        if (store.ocrResult.extracted_nid) setNid(store.ocrResult.extracted_nid)
        if (store.ocrResult.extracted_dob) setDob(store.ocrResult.extracted_dob)
      }
    }, [store.ocrResult])

    async function computeSha256(file: File): Promise<string> {
      const buf = await file.arrayBuffer()
      const hashBuf = await crypto.subtle.digest('SHA-256', buf)
      return Array.from(new Uint8Array(hashBuf)).map(b => b.toString(16).padStart(2, '0')).join('')
    }

    async function handleFileSelect(file: File, side: 'front' | 'back') {
      if (!appId) return
      if (!file.type.startsWith('image/')) {
        setError('Only image files are accepted (JPEG, PNG, WebP).')
        return
      }
      if (file.size > 10_000_000) {
        setError('File is too large. Please use an image under 10 MB.')
        return
      }
      const setter = side === 'front' ? setUploadingFront : setUploadingBack
      setter(true)
      setError('')
      try {
        // Step 1 — S3 upload (optional; silently skipped when MinIO unavailable in dev)
        let storage_key = `nid/${appId}/${side}/${Date.now()}.jpg`
        try {
          const urlRes = await verificationAPI.getNIDUploadUrl(appId, side, file.type || 'image/jpeg')
          if (urlRes.data.data) {
            const { upload_url, storage_key: key } = urlRes.data.data
            await uploadFileBlob(upload_url, file)
            storage_key = key
          }
        } catch { /* S3 unavailable in dev — use generated key */ }

        // Step 2 — DB registration (always runs so OCR can find the document row)
        const checksum = await computeSha256(file)
        try {
          await verificationAPI.uploadDocument(appId, {
            document_type: side === 'front' ? 'nid_front' : 'nid_back',
            storage_key,
            mime_type: file.type || 'image/jpeg',
            file_size_bytes: file.size,
            checksum_sha256: checksum,
          })
        } catch { /* best-effort in dev */ }

        const preview = URL.createObjectURL(file)
        if (side === 'front') { setFrontPreview(preview); store.setNIDFrontKey(storage_key) }
        else                  { setBackPreview(preview);  store.setNIDBackKey(storage_key) }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setter(false) }
    }

    async function runOcr() {
      if (!store.nidFrontKey || !store.nidBackKey) return
      setOcrLoading(true); setOcrError('')
      try {
        const res = await verificationAPI.runOCR(appId, {
          nid_front_key: store.nidFrontKey,
          nid_back_key:  store.nidBackKey,
        })
        if (res.data.data) store.setOCRResult(res.data.data)
      } catch (err) {
        setOcrError(getErrorMessage(err))
      } finally { setOcrLoading(false) }
    }

    function retakePhotos() {
      store.setNIDFrontKey('')
      store.setNIDBackKey('')
      store.setOCRResult(null as any)
      setFrontPreview(null); setBackPreview(null)
      setOcrError(''); setManualMode(false)
      setNid(''); setDob('')
    }

    async function handleValidate() {
      if (!nid || !dob || !store.application) return
      setLoading(true); setError('')
      try {
        const res = await verificationAPI.validateNID(
          store.application.id,
          { nid_number: nid, date_of_birth: dob },
        )
        if (res.data.data) {
          store.setNIDRecord(res.data.data)
          next(isAssisted ? 'fingerprint' : 'face_match')
        }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    const confidence = store.ocrResult?.confidence_score ?? null
    const confidenceBadge = confidence === null ? null
      : confidence >= 0.8 ? <span className="text-xs font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full">Confidence {(confidence * 100).toFixed(0)}%</span>
      : confidence >= 0.5 ? <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">Confidence {(confidence * 100).toFixed(0)}%</span>
      : <span className="text-xs font-medium text-red-700 bg-red-50 px-2 py-0.5 rounded-full">Confidence {(confidence * 100).toFixed(0)}%</span>

    // ── Phase A: Image Upload ────────────────────────────────────────────────
    if (!store.nidFrontKey || !store.nidBackKey) {
      return (
        <div className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-surface-900">NID Verification</h2>
            <p className="text-sm text-surface-500 mt-1">Upload photos of your National ID card — front and back</p>
          </div>
          {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
          <p className="text-xs text-surface-500 bg-surface-50 rounded-lg px-4 py-3">
            Place the card on a flat surface with good lighting. Avoid glare and shadows.
          </p>
          <div className="grid grid-cols-2 gap-4">
            {(['front', 'back'] as const).map(side => {
              const isUploading = side === 'front' ? uploadingFront : uploadingBack
              const preview     = side === 'front' ? frontPreview   : backPreview
              const isDone      = side === 'front' ? !!store.nidFrontKey : !!store.nidBackKey
              return (
                <label key={side} className={`relative flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-4 cursor-pointer transition-colors ${isDone ? 'border-green-400 bg-green-50' : 'border-surface-300 hover:border-brand-400 bg-surface-50'}`}>
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="sr-only"
                    disabled={isUploading}
                    onChange={e => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0], side) }}
                  />
                  {preview ? (
                    <img src={preview} alt={`NID ${side}`} className="w-full h-24 object-cover rounded-lg mb-2" />
                  ) : (
                    <Upload className={`h-8 w-8 mb-2 ${isDone ? 'text-green-500' : 'text-surface-400'}`} />
                  )}
                  {isUploading
                    ? <Spinner size="sm" />
                    : isDone
                      ? <span className="text-xs font-medium text-green-700 flex items-center gap-1"><CheckCircle2 className="h-3 w-3" /> Uploaded</span>
                      : <span className="text-xs text-surface-500">NID {side === 'front' ? 'Front' : 'Back'}</span>
                  }
                </label>
              )
            })}
          </div>
          <div className="flex gap-3">
            <button onClick={prev} className="btn-secondary flex-1"><ArrowLeft className="h-4 w-4" /> Back</button>
            <button
              onClick={() => { /* OCR auto-triggers via useEffect once both keys set */ }}
              className="btn-primary flex-1"
              disabled={!store.nidFrontKey || !store.nidBackKey}
            >
              <span>Next: Extract Data</span><ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )
    }

    // ── Phase B: OCR in progress ─────────────────────────────────────────────
    if (!store.ocrResult && !manualMode) {
      return (
        <div className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-surface-900">NID Verification</h2>
            <p className="text-sm text-surface-500 mt-1">Reading your NID card…</p>
          </div>
          {ocrLoading && (
            <div className="flex flex-col items-center justify-center py-10 gap-3">
              <Spinner size="lg" />
              <p className="text-sm text-surface-500">Extracting data from NID card…</p>
            </div>
          )}
          {ocrError && (
            <div className="space-y-3">
              <Alert variant="error">{ocrError}</Alert>
              <div className="flex gap-3">
                <button onClick={runOcr} className="btn-secondary flex-1"><RotateCcw className="h-4 w-4" /> Retry</button>
                <button onClick={() => setManualMode(true)} className="btn-ghost flex-1 text-sm">Enter manually</button>
              </div>
            </div>
          )}
          <button onClick={retakePhotos} className="btn-ghost w-full text-sm"><ArrowLeft className="h-4 w-4" /> Retake Photos</button>
        </div>
      )
    }

    // ── Phase C: Review extracted data + validate ────────────────────────────
    const ocrBlocked = (store.ocrResult?.confidence_score ?? 1) < 0.5
    return (
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-surface-900">NID Verification</h2>
            <p className="text-sm text-surface-500 mt-1">Review the extracted information and validate</p>
          </div>
          <div className="flex items-center">
            {confidenceBadge}
            {import.meta.env.DEV && store.ocrResult?.ocr_provider && (
              <code className="text-xs bg-surface-100 text-surface-500 px-1.5 py-0.5 rounded ml-2">
                OCR: {store.ocrResult.ocr_provider}
              </code>
            )}
          </div>
        </div>
        {store.ocrResult?.attempt_number && store.ocrResult.attempt_number > 1 && (
          <p className="text-xs text-surface-400">Extraction attempt {store.ocrResult.attempt_number}</p>
        )}
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
        {confidence !== null && confidence < 0.8 && !ocrBlocked && (
          <Alert variant="warning">OCR confidence is low. Please verify the fields below carefully before continuing.</Alert>
        )}
        {store.nidRecord && (
          <Alert variant="success">NID verified — <strong>{store.nidRecord.full_name_en}</strong></Alert>
        )}
        {store.ocrResult && (
          <div className="bg-surface-50 rounded-xl p-4 space-y-2 text-sm">
            {store.ocrResult.extracted_name_en   && <div className="flex justify-between"><span className="text-surface-500">Name (EN)</span><span className="font-medium">{store.ocrResult.extracted_name_en}</span></div>}
            {store.ocrResult.extracted_name_bn   && <div className="flex justify-between"><span className="text-surface-500">Name (BN)</span><span className="font-medium">{store.ocrResult.extracted_name_bn}</span></div>}
            {store.ocrResult.extracted_fathers_name && <div className="flex justify-between"><span className="text-surface-500">Father</span><span className="font-medium">{store.ocrResult.extracted_fathers_name}</span></div>}
            {store.ocrResult.extracted_mothers_name && <div className="flex justify-between"><span className="text-surface-500">Mother</span><span className="font-medium">{store.ocrResult.extracted_mothers_name}</span></div>}
            {store.ocrResult.extracted_address   && <div className="flex justify-between"><span className="text-surface-500">Address</span><span className="font-medium text-right max-w-xs">{store.ocrResult.extracted_address}</span></div>}
          </div>
        )}
        {store.ocrResult && !store.ocrResult.extracted_nid && (
          <Alert variant="warning">NID number could not be read from the card. Enter it manually or retake photos.</Alert>
        )}
        {store.ocrResult && !store.ocrResult.extracted_dob && (
          <Alert variant="warning">Date of birth could not be read from the card. Enter it manually or retake photos.</Alert>
        )}
        <Field label="NID Number" required>
          <Input placeholder="Enter 10–17 digit NID number" value={nid} onChange={e => setNid(e.target.value)} />
        </Field>
        {store.ocrResult?.field_confidence?.nid !== undefined &&
         store.ocrResult.field_confidence.nid < 0.7 && (
          <p className="text-xs text-amber-600 -mt-3">
            NID confidence {(store.ocrResult.field_confidence.nid * 100).toFixed(0)}% — verify carefully
          </p>
        )}
        <Field label="Date of Birth" required>
          <Input type="date" value={dob} onChange={e => setDob(e.target.value)} />
        </Field>
        {store.ocrResult?.field_confidence?.dob !== undefined &&
         store.ocrResult.field_confidence.dob < 0.7 && (
          <p className="text-xs text-amber-600 -mt-3">
            DOB confidence {(store.ocrResult.field_confidence.dob * 100).toFixed(0)}% — verify carefully
          </p>
        )}
        {ocrBlocked && (
          <Alert variant="error">OCR confidence is too low to proceed. Please retake the NID photos for a clearer scan.</Alert>
        )}
        <div className="flex gap-3">
          <button onClick={retakePhotos} className="btn-ghost flex-1 text-sm"><ArrowLeft className="h-4 w-4" /> Retake Photos</button>
          <button onClick={handleValidate} className="btn-primary flex-1" disabled={loading || !nid || !dob || ocrBlocked}>
            {loading ? <Spinner size="sm" /> : <><span>Validate NID</span><ArrowRight className="h-4 w-4" /></>}
          </button>
        </div>
      </div>
    )
  }

  // ── Step 3: Face Match ────────────────────────────────────────────────────
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
      } catch { setCameraError('Camera access denied. Please allow camera access and try again.') }
    }, [])

    useEffect(() => {
      if (stream && videoRef.current) {
        videoRef.current.srcObject = stream
      }
    }, [stream])

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
      if (!store.application || !store.nidRecord || !captured) return
      setLoading(true); setError('')
      try {
        setLoadingLabel('Uploading selfie…')
        let storage_key = `selfies/${store.application.id}-${Date.now()}.jpg`
        try {
          const urlRes = await verificationAPI.getSelfieUploadUrl(store.application.id)
          if (urlRes.data.data) {
            const { upload_url, storage_key: key } = urlRes.data.data
            const blob = await fetch(captured).then(r => r.blob())
            await uploadSelfieBlob(upload_url, blob)
            storage_key = key
          }
        } catch { /* storage unavailable in dev — proceed with generated key */ }

        setLoadingLabel('Verifying…')
        const res = await verificationAPI.faceMatch(store.application.id, {
          nid_number: store.nidRecord.nid_number,
          selfie_storage_key: storage_key,
          date_of_birth: store.nidRecord.date_of_birth,
        })
        if (res.data.data) {
          store.setFaceMatchResult(res.data.data)
          if (res.data.data.matched) next('profile')
          else setError(`Face match failed (score: ${res.data.data.similarity_score?.toFixed(1)}). Please try again.`)
        }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Face Verification</h2>
          <p className="text-sm text-surface-500 mt-1">Take a live selfie to verify your identity</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
        {cameraError && <Alert variant="warning">{cameraError}</Alert>}

        {store.faceMatchResult?.matched && (
          <Alert variant="success">
            Face matched — similarity {store.faceMatchResult.similarity_score?.toFixed(1)}%
          </Alert>
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
            <button onClick={capture} className="btn-primary flex-1"><Camera className="h-4 w-4" /> Capture Selfie</button>
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
          <button onClick={prev} className="btn-ghost w-full text-sm"><ArrowLeft className="h-4 w-4" /> Back</button>
          {store.faceMatchResult?.matched && (
            <button onClick={() => next('profile')} className="btn-primary flex-1"><span>Continue</span><ArrowRight className="h-4 w-4" /></button>
          )}
        </div>
      </div>
    )
  }

  // ── Step 3b: Fingerprint (assisted channel) ───────────────────────────────
  function FingerprintStep() {
    const [fingerPosition, setFingerPosition] = useState('right_index')
    const [template, setTemplate] = useState('')
    const [result, setResult] = useState<FingerprintResult | null>(store.fingerprintResult)
    const [exhausted, setExhausted] = useState(false)
    const [fpLoading, setFpLoading] = useState(false)
    const [fpError, setFpError] = useState('')

    async function handleSubmit() {
      if (!store.application || !store.nidRecord || !template) return
      setFpLoading(true); setFpError(''); setResult(null)
      try {
        const res = await verAPI.fingerprint(store.application.id, {
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
        const status = err?.response?.status
        if (status === 429) {
          setExhausted(true)
        } else {
          setFpError(getErrorMessage(err))
        }
      } finally { setFpLoading(false) }
    }

    const attemptLabel = result
      ? `Session ${result.session_number} — Attempt ${result.attempt_number} of 10`
      : store.fingerprintResult
        ? `Session ${store.fingerprintResult.session_number} — Attempt ${store.fingerprintResult.attempt_number} of 10`
        : 'Session 1 — Attempt 1 of 10'

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Fingerprint Verification</h2>
          <p className="text-sm text-surface-500 mt-1">Scan customer fingerprint to verify identity</p>
        </div>
        <p className="text-xs text-surface-400 font-mono">{attemptLabel}</p>

        {fpError && <Alert variant="error" onDismiss={() => setFpError('')}>{fpError}</Alert>}

        {exhausted && (
          <Alert variant="error">
            Maximum sessions reached. Offer traditional paper KYC to the customer.
          </Alert>
        )}

        {result && result.matched && (
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
            {result.fallback_message ?? 'Fingerprint sessions exhausted. Switching to face match is required by BFIU guidelines.'}
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
            <button className="btn-primary w-full" onClick={() => next('profile')}>
              <span>Continue</span><ArrowRight className="h-4 w-4" />
            </button>
          )}
          {result && !result.matched && !result.suggest_face_fallback && !exhausted && (
            <button className="btn-secondary w-full" onClick={() => { setTemplate(''); setResult(null) }}>
              <RotateCcw className="h-4 w-4" /> Retry
            </button>
          )}
          {result && !result.matched && result.suggest_face_fallback && (
            <button className="btn-primary w-full" onClick={() => { store.setStep('face_match'); setError('') }}>
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
          <button onClick={prev} className="btn-ghost w-full text-sm"><ArrowLeft className="h-4 w-4" /> Back</button>
        </div>
      </div>
    )
  }

  // ── Step 4: Customer Profile ──────────────────────────────────────────────
  function ProfileStep() {
    const nid = store.nidRecord
    const [form, setForm] = useState<Partial<CustomerProfileRequest>>({
      full_name_en: nid?.full_name_en ?? '',
      full_name_bn: nid?.full_name_bn ?? '',
      fathers_name_en: nid?.fathers_name_en ?? '',
      mothers_name_en: nid?.mothers_name_en ?? '',
      mobile_number: mobileNumber ?? '',
      nationality: 'Bangladeshi',
      residency_status: 'resident_bangladeshi',
      is_pep: false, is_ip: false, is_nrb: false,
      present_address: nid?.present_address ?? '',
    })

    function set(k: keyof CustomerProfileRequest, v: any) { setForm(f => ({ ...f, [k]: v })) }

    async function handle() {
      if (!store.application) return
      setLoading(true); setError('')
      try {
        await applicationsAPI.saveProfile(store.application.id, form as CustomerProfileRequest)
        store.markProfileSaved()
        next('nominee')
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Personal Information</h2>
          <p className="text-sm text-surface-500 mt-1">Verify and complete your KYC profile</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

        <div className="bg-surface-50 rounded-xl p-4 space-y-1 text-sm">
          <p className="font-medium text-surface-600 text-xs uppercase tracking-wide mb-2">From NID (non-editable)</p>
          <div className="grid grid-cols-2 gap-2">
            <div><span className="text-surface-500">NID:</span> <span className="font-mono font-medium">{nid?.nid_number}</span></div>
            <div><span className="text-surface-500">DOB:</span> <span className="font-medium">{nid?.date_of_birth}</span></div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Full Name (English)" required><Input value={form.full_name_en ?? ''} onChange={e => set('full_name_en', e.target.value)} /></Field>
          <Field label="Full Name (Bangla)"><Input value={form.full_name_bn ?? ''} onChange={e => set('full_name_bn', e.target.value)} /></Field>
          <Field label="Father's Name"><Input value={form.fathers_name_en ?? ''} onChange={e => set('fathers_name_en', e.target.value)} /></Field>
          <Field label="Mother's Name"><Input value={form.mothers_name_en ?? ''} onChange={e => set('mothers_name_en', e.target.value)} /></Field>
          <Field label="Mobile Number" required><Input value={form.mobile_number ?? ''} onChange={e => set('mobile_number', e.target.value)} /></Field>
          <Field label="Email"><Input type="email" value={form.email ?? ''} onChange={e => set('email', e.target.value)} /></Field>
          <Field label="Profession">
            <Select value={form.profession ?? ''} onChange={e => set('profession', e.target.value)}>
              <option value="">Select...</option>
              {PROFESSION_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </Select>
          </Field>
          <Field label="Business Activity">
            <Select value={form.business_activity ?? ''} onChange={e => set('business_activity', e.target.value)}>
              <option value="">Select (if applicable)...</option>
              {BUSINESS_ACTIVITY_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </Select>
          </Field>
          <Field label="Source of Fund">
            <Select value={form.source_of_fund ?? ''} onChange={e => set('source_of_fund', e.target.value)}>
              <option value="">Select...</option>
              {['salary','business','investment','inheritance','remittance','pension','other'].map(v => (
                <option key={v} value={v}>{v.charAt(0).toUpperCase() + v.slice(1)}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Present Address"><Input value={form.present_address ?? ''} onChange={e => set('present_address', e.target.value)} /></Field>
        <Field label="Permanent Address"><Input value={form.permanent_address ?? ''} onChange={e => set('permanent_address', e.target.value)} /></Field>

        <div className="flex gap-3">
          <button onClick={prev} className="btn-secondary flex-1"><ArrowLeft className="h-4 w-4" /> Back</button>
          <button onClick={handle} className="btn-primary flex-1" disabled={loading}>
            {loading ? <Spinner size="sm" /> : <><span>Save Profile</span><ArrowRight className="h-4 w-4" /></>}
          </button>
        </div>
      </div>
    )
  }

  // ── Step 5: Nominee ───────────────────────────────────────────────────────
  function NomineeStep() {
    const [name, setName] = useState('')
    const [relation, setRelation] = useState('spouse')
    const [dob, setDob] = useState('')
    const [isMinor, setIsMinor] = useState(false)
    const [guardianName, setGuardianName] = useState('')

    async function handle() {
      if (!store.application) return
      setLoading(true); setError('')
      try {
        await applicationsAPI.addNominee(store.application.id, {
          full_name: name, relation: relation as any,
          date_of_birth: dob || undefined, is_minor: isMinor,
          guardian_name: isMinor ? guardianName : undefined,
        })
        store.markNomineeSaved()
        next('signature')
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Nominee Details</h2>
          <p className="text-sm text-surface-500 mt-1">Add at least one nominee for your account</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Nominee Name" required><Input placeholder="Full legal name" value={name} onChange={e => setName(e.target.value)} /></Field>
          <Field label="Relation" required>
            <Select value={relation} onChange={e => setRelation(e.target.value)}>
              {['spouse','son','daughter','father','mother','brother','sister','other'].map(r => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </Select>
          </Field>
          <Field label="Date of Birth"><Input type="date" value={dob} onChange={e => setDob(e.target.value)} /></Field>
        </div>
        <label className="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={isMinor} onChange={e => setIsMinor(e.target.checked)} className="rounded border-surface-300 text-brand-600" />
          <span className="text-sm text-surface-600">Nominee is a minor (under 18)</span>
        </label>
        {isMinor && (
          <Field label="Guardian Name" required><Input placeholder="Legal guardian full name" value={guardianName} onChange={e => setGuardianName(e.target.value)} /></Field>
        )}
        <div className="flex gap-3">
          <button onClick={prev} className="btn-secondary flex-1"><ArrowLeft className="h-4 w-4" /> Back</button>
          <button onClick={handle} className="btn-primary flex-1" disabled={loading || !name}>
            {loading ? <Spinner size="sm" /> : <><span>Add Nominee</span><ArrowRight className="h-4 w-4" /></>}
          </button>
        </div>
      </div>
    )
  }

  // ── Step 6: Signature ─────────────────────────────────────────────────────
  function SignatureStep() {
    const isSimplified = store.preCheckResult?.kyc_type === 'simplified'
    const [sigType, setSigType] = useState<'pin' | 'electronic'>(isSimplified ? 'pin' : 'electronic')
    const [pin, setPin] = useState('')
    const [showPin, setShowPin] = useState(false)

    async function handle() {
      if (!store.application) return
      if (sigType === 'pin' && pin.length < 4) { setError('PIN must be at least 4 digits'); return }
      setLoading(true); setError('')
      try {
        await applicationsAPI.captureSignature(store.application.id, {
          signature_type: sigType,
          pin: sigType === 'pin' ? pin : undefined,
          storage_key: sigType === 'electronic' ? `signatures/${store.application.id}.png` : undefined,
        })
        store.markSignatureSaved()
        next('review')
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Signature / Consent</h2>
          <p className="text-sm text-surface-500 mt-1">
            {isSimplified ? 'Set a PIN for simplified eKYC accounts' : 'Provide your signature for account opening'}
          </p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

        <div className="grid grid-cols-2 gap-3">
          {isSimplified && (
            <button onClick={() => setSigType('pin')} className={`p-4 rounded-xl border-2 text-sm font-medium transition-colors text-left ${sigType === 'pin' ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-surface-200 text-surface-600'}`}>
              <div className="font-semibold mb-1">PIN</div>
              <div className="text-xs opacity-70">4–6 digit PIN for simplified accounts</div>
            </button>
          )}
          <button onClick={() => setSigType('electronic')} className={`p-4 rounded-xl border-2 text-sm font-medium transition-colors text-left ${sigType === 'electronic' ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-surface-200 text-surface-600'}`}>
            <div className="font-semibold mb-1">Electronic</div>
            <div className="text-xs opacity-70">Digital signature via device</div>
          </button>
        </div>

        {sigType === 'pin' && (
          <Field label="Set PIN" required hint="4–6 digits">
            <div className="relative">
              <Input
                type={showPin ? 'text' : 'password'}
                inputMode="numeric"
                maxLength={6}
                placeholder="••••"
                value={pin}
                onChange={e => setPin(e.target.value.replace(/\D/g, ''))}
                className="pr-10"
              />
              <button type="button" onClick={() => setShowPin(s => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400">
                {showPin ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </Field>
        )}

        <div className="flex gap-3">
          <button onClick={prev} className="btn-secondary flex-1"><ArrowLeft className="h-4 w-4" /> Back</button>
          <button onClick={handle} className="btn-primary flex-1" disabled={loading}>
            {loading ? <Spinner size="sm" /> : <><span>Confirm</span><ArrowRight className="h-4 w-4" /></>}
          </button>
        </div>
      </div>
    )
  }

  // ── Step 7: Review & Submit ───────────────────────────────────────────────
  function ReviewStep() {
    async function handle() {
      if (!store.application) return
      setLoading(true); setError('')
      try {
        const res = await applicationsAPI.submit(store.application.id)
        if (res.data.data) {
          store.setApplication(res.data.data)
          next('submitted')
        }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    const checks = [
      { label: 'NID verified', done: !!store.nidRecord },
      { label: 'Biometric verified', done: !!store.faceMatchResult?.matched || !!store.fingerprintResult?.matched },
      { label: 'Profile saved', done: store.profileSaved },
      { label: 'Nominee added', done: store.nomineeSaved },
      { label: 'Signature captured', done: store.signatureSaved },
    ]

    const allDone = checks.every(c => c.done)

    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-surface-900">Review & Submit</h2>
          <p className="text-sm text-surface-500 mt-1">Check everything before submitting your application</p>
        </div>
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

        <div className="bg-surface-50 rounded-xl p-5 space-y-3">
          <p className="text-sm font-medium text-surface-700 mb-3">Application Summary</p>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-surface-500">Ref:</span> <span className="font-mono text-xs">{store.application?.application_ref}</span></div>
            <div><span className="text-surface-500">Type:</span> <StatusBadge status={store.preCheckResult?.kyc_type ?? ''} /></div>
            <div><span className="text-surface-500">Product:</span> <span>{store.application?.product_type?.replace(/_/g, ' ')}</span></div>
            <div><span className="text-surface-500">Status:</span> <StatusBadge status={store.application?.status ?? ''} /></div>
          </div>
        </div>

        <div className="space-y-2">
          {checks.map(c => (
            <div key={c.label} className="flex items-center gap-3 text-sm">
              {c.done
                ? <CheckCircle2 className="h-5 w-5 text-success flex-shrink-0" />
                : <AlertTriangle className="h-5 w-5 text-warning flex-shrink-0" />}
              <span className={c.done ? 'text-surface-700' : 'text-warning-dark'}>{c.label}</span>
            </div>
          ))}
        </div>

        {!allDone && <Alert variant="warning">Some steps are incomplete. Please go back and complete them.</Alert>}

        <div className="flex gap-3">
          <button onClick={prev} className="btn-secondary flex-1"><ArrowLeft className="h-4 w-4" /> Back</button>
          <button onClick={handle} className="btn-primary flex-1" disabled={loading || !allDone}>
            {loading ? <Spinner size="sm" /> : <><span>Submit Application</span><ArrowRight className="h-4 w-4" /></>}
          </button>
        </div>
      </div>
    )
  }

  // ── Submitted confirmation ────────────────────────────────────────────────
  if (store.currentStep === 'submitted') {
    return (
      <div className="min-h-screen bg-surface-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full text-center p-10">
          <div className="w-16 h-16 bg-success/10 rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle2 className="h-9 w-9 text-success" />
          </div>
          <h2 className="text-xl font-semibold text-surface-900 mb-2">Application Submitted!</h2>
          <p className="text-surface-500 text-sm mb-1">Your eKYC application has been submitted for review.</p>
          <p className="text-sm font-mono bg-surface-50 rounded-lg px-4 py-2 my-4 text-surface-700">{store.application?.application_ref}</p>
          <p className="text-xs text-surface-400 mb-6">You will receive an SMS notification once the review is complete.</p>
          <button onClick={() => { store.reset(); navigate('/onboarding') }} className="btn-secondary w-full">Start New Application</button>
        </Card>
      </div>
    )
  }

  const stepComponents: Record<string, React.ReactElement> = {
    pre_check: <PreCheckStep />,
    nid_capture: <NIDStep />,
    fingerprint: <FingerprintStep />,
    face_match: <FaceMatchStep />,
    profile: <ProfileStep />,
    nominee: <NomineeStep />,
    signature: <SignatureStep />,
    review: <ReviewStep />,
  }

  return (
    <div className="min-h-screen bg-surface-50">
      <div className="max-w-2xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-xl font-semibold text-surface-900">eKYC Onboarding</h1>
          <p className="text-sm text-surface-500 mt-0.5">Self check-in — complete at your own pace</p>
        </div>

        {/* Steps */}
        <div className="mb-8 overflow-x-auto pb-2">
          <Steps steps={STEPS} current={Math.max(0, stepIndex)} />
        </div>

        {/* Step content */}
        <Card className="p-8">
          {stepComponents[store.currentStep]}
        </Card>
      </div>
    </div>
  )
}
