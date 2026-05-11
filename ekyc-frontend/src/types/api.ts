// ── Shared response wrappers ──────────────────────────────────────────────────
export interface APIResponse<T> {
  success: boolean
  message: string
  data: T | null
}

export interface PaginatedResponse<T> {
  success: boolean
  total: number
  page: number
  page_size: number
  data: T[]
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

// ── Enums ─────────────────────────────────────────────────────────────────────
export type UserStatus = 'active' | 'suspended' | 'locked'
export type AgentRole = 'maker' | 'checker' | 'compliance_officer' | 'system_admin' | 'system_auditor'
export type KYCType = 'simplified' | 'regular'
export type OnboardingChannel = 'self_checkin' | 'assisted' | 'branch' | 'internet'
export type ProductType = 'bo_account' | 'life_insurance' | 'non_life_insurance'
export type ApplicationStatus =
  | 'draft' | 'submitted' | 'screening' | 'risk_grading'
  | 'edd_pending' | 'pending_approval' | 'approved' | 'rejected' | 'cancelled'
export type Gender = 'M' | 'F' | 'T'
export type ResidencyStatus = 'resident_bangladeshi' | 'non_resident_bangladeshi'
export type SourceOfFund = 'salary' | 'business' | 'investment' | 'inheritance' | 'remittance' | 'pension' | 'other'
export type DocumentType = 'nid_front' | 'nid_back' | 'customer_photo' | 'nominee_photo' | 'signature' | 'edd_document' | 'guardian_nid' | 'other'
export type BiometricVerificationType = 'face_match' | 'fingerprint'
export type SignatureType = 'wet' | 'electronic' | 'digital' | 'pin'
export type NomineeRelation = 'spouse' | 'son' | 'daughter' | 'father' | 'mother' | 'brother' | 'sister' | 'other'
export type ScreenType = 'un_sanctions' | 'internal_blacklist' | 'adverse_media'
export type ScreenResult = 'clear' | 'potential_match' | 'confirmed_match' | 'requires_review'
export type RiskClassification = 'low' | 'medium' | 'high'
export type EDDStatus = 'in_progress' | 'pending' | 'documents_received' | 'under_review' | 'completed' | 'expired'
export type EDDTriggerReason = 'high_risk_score' | 'pep_match' | 'ip_match' | 'sanctions_match' | 'adverse_media' | 'manual_override' | 'risk_upgrade'
export type QueueType = 'standard' | 'high_risk' | 'failed_verification' | 'edd_pending'
export type QueueStatus = 'unassigned' | 'in_review' | 'completed' | 'escalated'
export type ApprovalAction = 'approve' | 'reject' | 'request_more_info' | 'escalate' | 'override_risk'
export type PreCheckDecision = 'simplified' | 'regular' | 'rejected'
export type RefreshStatus = 'scheduled' | 'reminder_sent' | 'in_progress' | 'completed' | 'overdue' | 'escalated'

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface SendOTPRequest {
  mobile_number: string
  email?: string
}

export interface VerifyOTPRequest {
  mobile_number: string
  otp: string
  device_fingerprint?: string
}

export interface AgentLoginRequest {
  employee_id: string
  password: string
  device_fingerprint: string
}

export interface Verify2FARequest {
  employee_id: string
  otp: string
  device_fingerprint: string
}

export interface AgentProfile {
  id: string
  employee_id: string
  full_name: string
  role: AgentRole
  branch_code: string | null
}

// ── Pre-check ─────────────────────────────────────────────────────────────────
export interface PreCheckRequest {
  product_type: ProductType
  expected_investment?: number
  annual_premium?: number
  is_pep: boolean
  is_ip: boolean
  residency: ResidencyStatus
}

export interface PreCheckResult {
  decision: PreCheckDecision
  kyc_type: KYCType
  decision_reason: string
  pre_check_log_id: string
  thresholds_applied: Record<string, number>
}

// ── KYC Application ───────────────────────────────────────────────────────────
export interface CreateApplicationRequest {
  kyc_type: KYCType
  onboarding_channel: OnboardingChannel
  product_type: ProductType
  product_code?: string
  expected_investment?: number
}

export interface ApplicationRead {
  id: string
  user_id: string
  agent_id: string | null
  kyc_type: string
  onboarding_channel: string
  product_type: string
  status: string
  application_ref: string | null
  submitted_at: string | null
  created_at: string
}

export interface CustomerProfileRequest {
  full_name_en: string
  full_name_bn?: string
  fathers_name_en?: string
  fathers_name_bn?: string
  mothers_name_en?: string
  mothers_name_bn?: string
  spouse_name_en?: string
  gender?: Gender
  tin_number?: string
  profession?: string
  business_activity?: string
  monthly_income?: number
  source_of_fund?: SourceOfFund
  source_of_fund_detail?: string
  mobile_number: string
  email?: string
  present_address?: string
  permanent_address?: string
  nationality: string
  residency_status: ResidencyStatus
  is_pep: boolean
  is_ip: boolean
  is_nrb: boolean
}

export interface NomineeRequest {
  full_name: string
  date_of_birth?: string
  relation: NomineeRelation
  contact_number?: string
  address?: string
  photo_storage_key?: string
  is_minor: boolean
  guardian_name?: string
  guardian_nid?: string
  guardian_address?: string
}

export interface SignatureRequest {
  signature_type: SignatureType
  storage_key?: string
  pin?: string
}

// ── Verification ──────────────────────────────────────────────────────────────
export interface NIDVerifyRequest {
  nid_number: string
  date_of_birth: string
}

export interface NIDRecord {
  nid_number: string
  full_name_en: string
  full_name_bn: string
  fathers_name_en: string
  fathers_name_bn: string
  mothers_name_en: string
  mothers_name_bn: string
  date_of_birth: string
  gender: string
  present_address: string
}

export interface FaceMatchRequest {
  nid_number: string
  selfie_storage_key: string
  date_of_birth: string
}

export interface FaceMatchResult {
  matched: boolean
  similarity_score: number
  attempt_number: number
  session_number: number
  attempts_remaining: number
}

export interface SelfieUploadUrlResponse {
  upload_url: string
  storage_key: string
  expires_in: number
}

export interface PresignedGetResponse {
  url: string
  expires_in: number
}

export interface FingerprintResult {
  matched: boolean
  similarity_score: number
  attempt_number: number
  session_number: number
  suggest_face_fallback: boolean
  fallback_message: string | null
}

export type OnboardingChannelValue = 'self_checkin' | 'assisted' | 'branch' | 'internet'

export interface DocumentUploadRequest {
  document_type: DocumentType
  storage_key: string
  original_filename?: string
  mime_type: string
  file_size_bytes: number
  checksum_sha256: string
}

export interface NIDUploadUrlResponse {
  upload_url: string
  storage_key: string
  expires_in: number
}

export interface NIDOCRRequest {
  nid_front_key: string
  nid_back_key: string
}

export interface OCRResult {
  id: string
  kyc_application_id: string
  document_id: string
  extracted_name_en: string | null
  extracted_name_bn: string | null
  extracted_nid: string | null
  extracted_dob: string | null
  extracted_address: string | null
  extracted_fathers_name: string | null
  extracted_mothers_name: string | null
  confidence_score: number | null
  raw_json: string
  created_at: string
  attempt_number?: number
  ocr_provider?: string
  field_confidence?: {
    name_en?: number
    name_bn?: number
    nid?: number
    dob?: number
    address?: number
    fathers_name?: number
    mothers_name?: number
  }
  quality_flags?: {
    glare_detected?: boolean
    blur_detected?: boolean
    rotation_detected?: boolean
    image_too_dark?: boolean
  }
}

export interface VerificationStatus {
  app_id: string
  total_attempts: number
  successful_attempts: number
  current_session: number
  is_verified: boolean
  face_matched: boolean
  fingerprint_matched: boolean
  nid_validated: boolean
  can_retry: boolean
}

// ── Compliance ────────────────────────────────────────────────────────────────
export interface ScreeningResultItem {
  id?: string
  screen_type: string
  list_source: string
  result: string
  match_score: number | null
  requires_review: boolean
  screened_at?: string
}

export interface PEPCheckRequest {
  is_pep: boolean
  is_ip: boolean
  is_family_of_pep: boolean
  is_family_of_ip: boolean
  is_high_official_intl_org: boolean
  match_detail?: string
}

export interface RiskScoreRequest {
  score_onboarding_channel: number
  score_geography: number
  score_customer_type: number
  score_product: number
  score_business_activity: number
  score_profession: number
  score_transaction_volume: number
  score_transparency: number
}

export interface RiskScoreResult {
  risk_score_id: string
  total_score: number
  risk_classification: RiskClassification
  edd_required: boolean
  score_breakdown: Record<string, number>
  version: number
  scored_at?: string
  matched_profession_category?: string
  matched_business_category?: string
}

export interface EDDRequestResult {
  edd_id: string
  trigger_reason: string
  deadline: string
  required_documents: string[]
}

export interface EDDDocument {
  document_type: string
  storage_key: string
  checksum_sha256: string
  uploaded_at?: string
}

export interface EDDStatus_t {
  edd_id: string
  status: EDDStatus
  trigger_reason: string
  deadline_at: string
  days_remaining: number
  responded_at: string | null
  uploaded_documents?: EDDDocument[]
}

// ── Admin ─────────────────────────────────────────────────────────────────────
export interface QueueEntry {
  id: string
  app_id: string
  queue_type: QueueType
  priority: string
  status: QueueStatus
  assigned_maker_id: string | null
  assigned_checker_id: string | null
  created_at: string
}

export interface ReviewSummary {
  app_id: string
  application_ref: string | null
  kyc_type: string
  status: string
  customer_name: string | null
  nid_number: string | null
  biometric_verified: boolean
  face_matched: boolean
  screening_clear: boolean
  pep_ip_flagged: boolean
  risk_classification: string | null
  risk_score: number | null
  edd_required: boolean
}

export interface ApplicationDocument {
  id: string
  document_type: string
  storage_key: string
  original_filename: string | null
  mime_type: string
  uploaded_at: string
}

export interface DecisionRequest {
  action: ApprovalAction
  notes?: string
  rejection_reason?: string
}

export interface AccountActivated {
  account_id: string
  account_number: string
  unique_account_number: string
  risk_tier: RiskClassification
  kyc_next_review_date: string
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
export interface RefreshSchedule {
  schedule_id: string
  risk_tier: string
  due_date: string
  status: RefreshStatus
  days_remaining: number
  is_overdue: boolean
  reminder_count: number
  last_reminder_at: string | null
}

export interface ScheduleListItem {
  schedule_id: string
  account_id: string
  user_id: string
  risk_tier: RiskClassification
  due_date: string
  status: RefreshStatus
  days_remaining: number
  is_overdue: boolean
  reminder_count: number
  last_reminder_at: string | null
}

// ── Notifications ──────────────────────────────────────────────────────────────
export interface NotificationRead {
  id: string
  user_id: string
  kyc_application_id: string | null
  channel: 'sms' | 'email' | 'push'
  notification_type: string
  recipient_address: string
  message_body: string
  status: 'pending' | 'sent' | 'delivered' | 'failed'
  retry_count: number
  gateway_message_id: string | null
  sent_at: string | null
  delivered_at: string | null
  error_message: string | null
  created_at: string
}
