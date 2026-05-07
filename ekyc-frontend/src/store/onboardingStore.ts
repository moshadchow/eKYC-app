import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { PreCheckResult, ApplicationRead, NIDRecord, FaceMatchResult, VerificationStatus } from '@/types/api'

export type OnboardingStep =
  | 'pre_check'
  | 'create_application'
  | 'nid_capture'
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
  nidRecord: NIDRecord | null
  faceMatchResult: FaceMatchResult | null
  verificationStatus: VerificationStatus | null
  profileSaved: boolean
  nomineeSaved: boolean
  signatureSaved: boolean

  setStep:                (step: OnboardingStep) => void
  setPreCheckResult:      (r: PreCheckResult) => void
  setApplication:         (a: ApplicationRead) => void
  setNIDRecord:           (n: NIDRecord) => void
  setFaceMatchResult:     (f: FaceMatchResult) => void
  setVerificationStatus:  (v: VerificationStatus) => void
  markProfileSaved:       () => void
  markNomineeSaved:       () => void
  markSignatureSaved:     () => void
  reset:                  () => void
}

const initial = {
  currentStep: 'pre_check' as OnboardingStep,
  preCheckResult: null,
  application: null,
  nidRecord: null,
  faceMatchResult: null,
  verificationStatus: null,
  profileSaved: false,
  nomineeSaved: false,
  signatureSaved: false,
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      ...initial,
      setStep:               (step) => set({ currentStep: step }),
      setPreCheckResult:     (r)    => set({ preCheckResult: r }),
      setApplication:        (a)    => set({ application: a }),
      setNIDRecord:          (n)    => set({ nidRecord: n }),
      setFaceMatchResult:    (f)    => set({ faceMatchResult: f }),
      setVerificationStatus: (v)    => set({ verificationStatus: v }),
      markProfileSaved:      ()     => set({ profileSaved: true }),
      markNomineeSaved:      ()     => set({ nomineeSaved: true }),
      markSignatureSaved:    ()     => set({ signatureSaved: true }),
      reset:                 ()     => set(initial),
    }),
    { name: 'ekyc-onboarding' }
  )
)
