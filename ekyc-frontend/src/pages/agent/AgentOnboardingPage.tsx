import React, { useState, useRef, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowRight, ArrowLeft, CheckCircle2, RotateCcw, Camera, Fingerprint, Upload } from 'lucide-react'
import { applicationsAPI, verificationAPI, uploadSelfieBlob, uploadFileBlob } from '@/api/services'
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
          store.reset()
          store.setApplication(res.data.data)
          store.setOnboardingChannel('assisted')
          store.setCustomerMobile(mobile)
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

  // ── Step 2: NID (3-phase: upload → OCR → review+validate) ─────────────────
  function NIDStep() {
    const [frontPreview, setFrontPreview] = useState<string | null>(null)
    const [backPreview, setBackPreview]   = useState<string | null>(null)
    const [uploadingFront, setUploadingFront] = useState(false)
    const [uploadingBack, setUploadingBack]   = useState(false)
    const [ocrLoading, setOcrLoading] = useState(false)
    const [ocrError, setOcrError]     = useState('')
    const [manualMode, setManualMode] = useState(false)
    const [nid, setNid] = useState(store.ocrResult?.extracted_nid ?? store.nidRecord?.nid_number ?? '')
    const [dob, setDob] = useState(store.ocrResult?.extracted_dob ?? store.nidRecord?.date_of_birth ?? '')

    useEffect(() => {
      if (store.nidFrontKey && store.nidBackKey && !store.ocrResult && !ocrLoading && !ocrError && !manualMode) {
        runOcr()
      }
    }, [store.nidFrontKey, store.nidBackKey])

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
      setter(true); setError('')
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
            storage_key, mime_type: file.type || 'image/jpeg',
            file_size_bytes: file.size, checksum_sha256: checksum,
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
      } catch (err) { setOcrError(getErrorMessage(err)) }
      finally { setOcrLoading(false) }
    }

    function retakePhotos() {
      store.setNIDFrontKey(''); store.setNIDBackKey('')
      store.setOCRResult(null as any)
      setFrontPreview(null); setBackPreview(null)
      setOcrError(''); setManualMode(false); setNid(''); setDob('')
    }

    async function handleValidate() {
      if (!nid || !dob || !appId) return
      setLoading(true); setError('')
      try {
        const res = await verificationAPI.validateNID(appId, { nid_number: nid, date_of_birth: dob })
        if (res.data.data) { store.setNIDRecord(res.data.data); setStep('fingerprint') }
      } catch (err) { setError(getErrorMessage(err)) }
      finally { setLoading(false) }
    }

    const confidence = store.ocrResult?.confidence_score ?? null
    const confidenceBadge = confidence === null ? null
      : confidence >= 0.8 ? <span className="text-xs font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full">Confidence {(confidence * 100).toFixed(0)}%</span>
      : confidence >= 0.5 ? <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">Confidence {(confidence * 100).toFixed(0)}%</span>
      : <span className="text-xs font-medium text-red-700 bg-red-50 px-2 py-0.5 rounded-full">Confidence {(confidence * 100).toFixed(0)}%</span>

    // Phase A
    if (!store.nidFrontKey || !store.nidBackKey) {
      return (
        <div className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-surface-900">NID Verification</h2>
            <p className="text-sm text-surface-500 mt-1">Upload customer's NID card — front and back</p>
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
                  <input type="file" accept="image/*" capture="environment" className="sr-only"
                    disabled={isUploading}
                    onChange={e => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0], side) }}
                  />
                  {preview
                    ? <img src={preview} alt={`NID ${side}`} className="w-full h-24 object-cover rounded-lg mb-2" />
                    : <Upload className={`h-8 w-8 mb-2 ${isDone ? 'text-green-500' : 'text-surface-400'}`} />
                  }
                  {isUploading ? <Spinner size="sm" />
                    : isDone ? <span className="text-xs font-medium text-green-700 flex items-center gap-1"><CheckCircle2 className="h-3 w-3" /> Uploaded</span>
                    : <span className="text-xs text-surface-500">NID {side === 'front' ? 'Front' : 'Back'}</span>
                  }
                </label>
              )
            })}
          </div>
          <div className="flex gap-3">
            {!urlAppId && (
              <button onClick={() => setStep('create')} className="btn-secondary flex-1"><ArrowLeft className="h-4 w-4" /> Back</button>
            )}
            <button className="btn-primary flex-1" disabled={!store.nidFrontKey || !store.nidBackKey}>
              <span>Next: Extract Data</span><ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )
    }

    // Phase B
    if (!store.ocrResult && !manualMode) {
      return (
        <div className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-surface-900">NID Verification</h2>
            <p className="text-sm text-surface-500 mt-1">Reading NID card…</p>
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

    // Phase C
    const ocrBlocked = (store.ocrResult?.confidence_score ?? 1) < 0.5
    return (
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-surface-900">NID Verification</h2>
            <p className="text-sm text-surface-500 mt-1">Review extracted information and validate</p>
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
          <Alert variant="warning">OCR confidence is low. Please verify the fields below carefully.</Alert>
        )}
        {store.nidRecord && (
          <Alert variant="success">NID verified — <strong>{store.nidRecord.full_name_en}</strong></Alert>
        )}
        {store.ocrResult && (
          <div className="bg-surface-50 rounded-xl p-4 space-y-2 text-sm">
            {store.ocrResult.extracted_name_en      && <div className="flex justify-between"><span className="text-surface-500">Name (EN)</span><span className="font-medium">{store.ocrResult.extracted_name_en}</span></div>}
            {store.ocrResult.extracted_name_bn      && <div className="flex justify-between"><span className="text-surface-500">Name (BN)</span><span className="font-medium">{store.ocrResult.extracted_name_bn}</span></div>}
            {store.ocrResult.extracted_fathers_name && <div className="flex justify-between"><span className="text-surface-500">Father</span><span className="font-medium">{store.ocrResult.extracted_fathers_name}</span></div>}
            {store.ocrResult.extracted_mothers_name && <div className="flex justify-between"><span className="text-surface-500">Mother</span><span className="font-medium">{store.ocrResult.extracted_mothers_name}</span></div>}
            {store.ocrResult.extracted_address      && <div className="flex justify-between"><span className="text-surface-500">Address</span><span className="font-medium text-right max-w-xs">{store.ocrResult.extracted_address}</span></div>}
          </div>
        )}
        {store.ocrResult && !store.ocrResult.extracted_nid && (
          <Alert variant="warning">NID number could not be read from the card. Enter it manually or retake photos.</Alert>
        )}
        {store.ocrResult && !store.ocrResult.extracted_dob && (
          <Alert variant="warning">Date of birth could not be read from the card. Enter it manually or retake photos.</Alert>
        )}
        <Field label="NID Number" required>
          <Input placeholder="10–17 digit NID number" value={nid} onChange={e => setNid(e.target.value)} />
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

  // ── Step 3: Fingerprint ────────────────────────────────────────────────────
  function FingerprintStep() {
    const [fingerPosition, setFingerPosition] = useState('right_index')
    const [template, setTemplate] = useState('')
    const [exhausted, setExhausted] = useState(false)
    const [fpLoading, setFpLoading] = useState(false)
    const [fpError, setFpError] = useState('')

    // Use store result so it survives parent re-renders
    const result = store.fingerprintResult

    function clearScan() {
      setTemplate('')
      store.clearFingerprintResult()
    }

    async function handleSubmit() {
      if (!appId || !store.nidRecord || !template) return
      setFpLoading(true); setFpError('')
      store.clearFingerprintResult()
      try {
        const res = await verificationAPI.fingerprint(appId, {
          nid_number: store.nidRecord.nid_number,
          fingerprint_template: template,
          finger_position: fingerPosition,
          date_of_birth: store.nidRecord.date_of_birth,
        })
        if (res.data.data) {
          store.setFingerprintResult(res.data.data)
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

        {!exhausted && !result?.matched && (
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
            <div className="flex gap-3">
              <button
                className="btn-secondary flex-1"
                onClick={() => setTemplate(btoa('mock-fp-scan-' + Date.now()))}
              >
                Simulate Scan
              </button>
              <button
                className="btn-secondary flex-1"
                onClick={clearScan}
                disabled={!template}
              >
                <RotateCcw className="h-4 w-4" /> Clear
              </button>
            </div>
          </>
        )}

        <div className="flex flex-col gap-3">
          {result?.matched && (
            <button className="btn-primary w-full" onClick={() => setStep('profile')}>
              <span>Continue to Profile</span><ArrowRight className="h-4 w-4" />
            </button>
          )}
          {result && !result.matched && !result.suggest_face_fallback && !exhausted && (
            <button className="btn-secondary w-full" onClick={clearScan}>
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
      } catch { setCameraError('Camera access denied. Please allow camera access.') }
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
      mobile_number: store.customerMobile ?? '',
      profession: '',
      source_of_fund: undefined,
      nationality: 'Bangladeshi',
      residency_status: 'resident_bangladeshi',
      is_pep: false, is_ip: false, is_nrb: false,
    })

    function setField(k: keyof CustomerProfileRequest, v: any) { setForm(f => ({ ...f, [k]: v })) }

    const biometricVerified =
      store.fingerprintResult?.matched === true ||
      store.faceMatchResult?.matched === true

    async function handle() {
      if (!appId) return
      if (!biometricVerified) {
        setError('Biometric verification is required. Please go back and complete fingerprint or face verification.')
        return
      }
      setLoading(true); setError('')
      try {
        await applicationsAPI.agentSaveProfile(appId, form as CustomerProfileRequest)
        store.markProfileSaved()
        await applicationsAPI.agentSubmit(appId)
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

        {store.fingerprintResult?.matched && (
          <Alert variant="success">
            Fingerprint verified — similarity {store.fingerprintResult.similarity_score?.toFixed(1)}%
          </Alert>
        )}
        {store.faceMatchResult?.matched && (
          <Alert variant="success">
            Face matched — similarity {store.faceMatchResult.similarity_score?.toFixed(1)}%
          </Alert>
        )}
        {!biometricVerified && (
          <Alert variant="error">
            Biometric verification not completed. Please go back and verify fingerprint or face.
          </Alert>
        )}

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
            disabled={loading || !form.full_name_en || !form.mobile_number || !biometricVerified}
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
