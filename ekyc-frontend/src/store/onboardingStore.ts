import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { PreCheckResult, ApplicationRead, NIDRecord, FaceMatchResult, FingerprintResult, OnboardingChannelValue, VerificationStatus, OCRResult } from '@/types/api'

export type OnboardingStep =
  | 'pre_check'
  | 'create_application'
  | 'nid_capture'
  | 'fingerprint'
  | 'face_match'
  | 'profile'
  | 'nominee'
  | 'signature'
  | 'review'
  | 'submitted'

interface OnboardingState {
  currentStep: OnboardingStep
  preCheckResult: PreCheckResult | null
  application: ApplicationRead | null
  customerMobile: string | null
  nidRecord: NIDRecord | null
  faceMatchResult: FaceMatchResult | null
  fingerprintResult: FingerprintResult | null
  onboardingChannel: OnboardingChannelValue | null
  verificationStatus: VerificationStatus | null
  profileSaved: boolean
  nomineeSaved: boolean
  signatureSaved: boolean
  nidFrontKey:  string | null
  nidBackKey:   string | null
  ocrResult:    OCRResult | null

  setStep:                (step: OnboardingStep) => void
  setPreCheckResult:      (r: PreCheckResult) => void
  setApplication:         (a: ApplicationRead) => void
  setCustomerMobile:       (m: string) => void
  setNIDRecord:           (n: NIDRecord) => void
  setFaceMatchResult:     (f: FaceMatchResult) => void
  setFingerprintResult:   (r: FingerprintResult) => void
  clearFingerprintResult: () => void
  setOnboardingChannel:   (channel: OnboardingChannelValue) => void
  setVerificationStatus:  (v: VerificationStatus) => void
  markProfileSaved:       () => void
  markNomineeSaved:       () => void
  markSignatureSaved:     () => void
  setNIDFrontKey:         (key: string) => void
  setNIDBackKey:          (key: string) => void
  setOCRResult:           (r: OCRResult) => void
  reset:                  () => void
}

const initial = {
  currentStep: 'pre_check' as OnboardingStep,
  preCheckResult: null,
  application: null,
  customerMobile: null,
  nidRecord: null,
  faceMatchResult: null,
  fingerprintResult: null,
  onboardingChannel: null,
  verificationStatus: null,
  profileSaved: false,
  nomineeSaved: false,
  signatureSaved: false,
  nidFrontKey: null,
  nidBackKey:  null,
  ocrResult:   null,
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      ...initial,
      setStep:               (step) => set({ currentStep: step }),
      setPreCheckResult:     (r)    => set({ preCheckResult: r }),
      setApplication:        (a)    => set({ application: a }),
      setCustomerMobile:     (m)    => set({ customerMobile: m }),
      setNIDRecord:          (n)    => set({ nidRecord: n }),
      setFaceMatchResult:    (f)    => set({ faceMatchResult: f }),
      setFingerprintResult:  (r)    => set({ fingerprintResult: r }),
      clearFingerprintResult: ()    => set({ fingerprintResult: null }),
      setOnboardingChannel:  (ch)   => set({ onboardingChannel: ch }),
      setVerificationStatus: (v)    => set({ verificationStatus: v }),
      markProfileSaved:      ()     => set({ profileSaved: true }),
      markNomineeSaved:      ()     => set({ nomineeSaved: true }),
      markSignatureSaved:    ()     => set({ signatureSaved: true }),
      setNIDFrontKey:        (key)  => set({ nidFrontKey: key }),
      setNIDBackKey:         (key)  => set({ nidBackKey: key }),
      setOCRResult:          (r)    => set({ ocrResult: r }),
      reset:                 ()     => set({
    currentStep: 'pre_check' as OnboardingStep,
    preCheckResult: null,
    application: null,
    customerMobile: null,
    nidRecord: null,
    faceMatchResult: null,
    fingerprintResult: null,
    onboardingChannel: null,
    verificationStatus: null,
    profileSaved: false,
    nomineeSaved: false,
    signatureSaved: false,
    nidFrontKey: null,
    nidBackKey:  null,
    ocrResult:   null,
  }),
    }),
    { name: 'ekyc-onboarding' }
  )
)
