import api, { apiClient } from './client'
import type {
  APIResponse, PaginatedResponse, TokenResponse,
  SendOTPRequest, VerifyOTPRequest, AgentLoginRequest, Verify2FARequest,
  AgentProfile, PreCheckRequest, PreCheckResult,
  CreateApplicationRequest, ApplicationRead, CustomerProfileRequest,
  NomineeRequest, SignatureRequest, NIDVerifyRequest, NIDRecord,
  FaceMatchRequest, FaceMatchResult, FingerprintResult, SelfieUploadUrlResponse, DocumentUploadRequest, VerificationStatus,
  ScreeningResultItem, PEPCheckRequest, RiskScoreRequest, RiskScoreResult,
  EDDRequestResult, EDDStatus_t, QueueEntry, ReviewSummary,
  DecisionRequest, AccountActivated, RefreshSchedule, ScheduleListItem,
  NotificationRead,
} from '@/types/api'

// ── Auth — Customer ───────────────────────────────────────────────────────────
export const authAPI = {
  sendOTP:   (body: SendOTPRequest)   => apiClient.post<APIResponse<{ otp: string; expires_in_seconds: number; mobile_number: string }>>('/auth/customer/send-otp', body),
  verifyOTP: (body: VerifyOTPRequest) => apiClient.post<APIResponse<TokenResponse>>('/auth/customer/verify-otp', body),
  logout:    ()                       => apiClient.post<{ message: string }>('/auth/customer/logout'),
}

// ── Auth — Agent ──────────────────────────────────────────────────────────────
export const agentAuthAPI = {
  login:     (body: AgentLoginRequest) => apiClient.post<APIResponse<{ otp: string; employee_id: string }>>('/auth/agent/login', body),
  verify2FA: (body: Verify2FARequest)  => apiClient.post<APIResponse<TokenResponse>>('/auth/agent/verify-2fa', body),
  me:        ()                        => apiClient.get<APIResponse<AgentProfile>>('/auth/agent/me'),
  logout:    ()                        => apiClient.post<{ message: string }>('/auth/agent/logout'),
}

// ── Pre-check ─────────────────────────────────────────────────────────────────
export const preCheckAPI = {
  run: (body: PreCheckRequest) => apiClient.post<APIResponse<PreCheckResult>>('/onboarding/pre-check', body),
  get: (logId: string)         => apiClient.get<APIResponse<PreCheckResult>>(`/onboarding/pre-check/${logId}`),
}

// ── KYC Applications ──────────────────────────────────────────────────────────
export const applicationsAPI = {
  create:         (body: CreateApplicationRequest)                => apiClient.post<APIResponse<ApplicationRead>>('/kyc/applications', body),
  get:            (appId: string)                                 => apiClient.get<APIResponse<ApplicationRead>>(`/kyc/applications/${appId}`),
  list:           (params?: { status_filter?: string; page?: number; page_size?: number }) => apiClient.get<PaginatedResponse<ApplicationRead>>('/kyc/applications', { params }),
  saveProfile:    (appId: string, body: CustomerProfileRequest)  => apiClient.put<APIResponse<{ profile_id: string }>>(`/kyc/applications/${appId}/profile`, body),
  addNominee:     (appId: string, body: NomineeRequest)          => apiClient.post<APIResponse<{ nominee_id: string }>>(`/kyc/applications/${appId}/nominees`, body),
  captureSignature:(appId: string, body: SignatureRequest)       => apiClient.post<APIResponse<{ signature_id: string }>>(`/kyc/applications/${appId}/signature`, body),
  submit:         (appId: string)                                => apiClient.post<APIResponse<ApplicationRead>>(`/kyc/applications/${appId}/submit`),
  agentCreate:    (body: CreateApplicationRequest, customerMobile: string) =>
    apiClient.post<APIResponse<ApplicationRead>>('/kyc/applications/agent/create', body, { params: { customer_mobile: customerMobile } }),
  agentSaveProfile: (appId: string, body: CustomerProfileRequest) =>
    apiClient.put<APIResponse<{ profile_id: string }>>(`/kyc/applications/agent/${appId}/profile`, body),
  agentSubmit:    (appId: string) =>
    apiClient.post<APIResponse<ApplicationRead>>(`/kyc/applications/agent/${appId}/submit`),
}

// ── Verification ──────────────────────────────────────────────────────────────
export const verificationAPI = {
  validateNID:    (appId: string, body: NIDVerifyRequest)    => apiClient.post<APIResponse<NIDRecord>>(`/kyc/applications/${appId}/verify/nid`, body),
  faceMatch:      (appId: string, body: FaceMatchRequest)    => apiClient.post<APIResponse<FaceMatchResult>>(`/kyc/applications/${appId}/verify/face`, body),
  fingerprint:    (appId: string, body: { nid_number: string; fingerprint_template: string; finger_position?: string; date_of_birth: string }) =>
    apiClient.post<APIResponse<FingerprintResult>>(`/kyc/applications/${appId}/verify/fingerprint`, body),
  getSelfieUploadUrl: (appId: string, contentType = 'image/jpeg') =>
    apiClient.get<APIResponse<SelfieUploadUrlResponse>>(`/kyc/applications/${appId}/selfie-upload-url`, { params: { content_type: contentType } }),
  status:         (appId: string)                            => apiClient.get<APIResponse<VerificationStatus>>(`/kyc/applications/${appId}/verify/status`),
  uploadDocument: (appId: string, body: DocumentUploadRequest) => apiClient.post<APIResponse<{ document_id: string; version: number }>>(`/kyc/applications/${appId}/documents/upload`, body),
}

// ── Selfie Upload (direct PUT to object storage — no auth header) ─────────────
export async function uploadSelfieBlob(uploadUrl: string, blob: Blob): Promise<void> {
  const res = await fetch(uploadUrl, {
    method: 'PUT',
    body: blob,
    headers: { 'Content-Type': blob.type || 'image/jpeg' },
  })
  if (!res.ok) throw new Error(`Selfie upload failed: ${res.status} ${res.statusText}`)
}

// ── Compliance ────────────────────────────────────────────────────────────────
export const complianceAPI = {
  runScreening:       (appId: string)                            => apiClient.post<APIResponse<ScreeningResultItem[]>>(`/compliance/${appId}/screening/run`),
  getScreening:       (appId: string)                            => apiClient.get<APIResponse<ScreeningResultItem[]>>(`/compliance/${appId}/screening/results`),
  pepCheck:           (appId: string, body: PEPCheckRequest)     => apiClient.post<APIResponse<{ check_id: string; edd_required: boolean }>>(`/compliance/${appId}/pep-check`, body),
  addBO:              (appId: string, body: { full_name: string; nid_number?: string; ownership_percentage?: number; is_pep: boolean; is_ip: boolean }) =>
    apiClient.post<APIResponse<{ bo_id: string }>>(`/compliance/${appId}/beneficial-owners`, body),
  listBO:             (appId: string)                            => apiClient.get<APIResponse<unknown[]>>(`/compliance/${appId}/beneficial-owners`),
  calculateRisk:      (appId: string, manual?: RiskScoreRequest) => apiClient.post<APIResponse<RiskScoreResult>>(`/compliance/${appId}/risk-score`, manual || null),
  getRisk:            (appId: string)                            => apiClient.get<APIResponse<RiskScoreResult>>(`/compliance/${appId}/risk-score`),
  createEDD:          (appId: string, trigger?: string)          => apiClient.post<APIResponse<EDDRequestResult>>(`/compliance/${appId}/edd/request`, null, { params: trigger ? { trigger_reason: trigger } : {} }),
  getEDDStatus:       (appId: string)                            => apiClient.get<APIResponse<EDDStatus_t>>(`/compliance/${appId}/edd/status`),
  uploadEDDDocument:  (appId: string, eddId: string, body: { document_type: string; storage_key: string; checksum_sha256: string }) =>
    apiClient.post<APIResponse<{ doc_id: string }>>(`/compliance/${appId}/edd/${eddId}/documents`, body),
}

// ── Admin ─────────────────────────────────────────────────────────────────────
export const adminAPI = {
  listQueue:      (params?: { queue_type?: string; status?: string; page?: number }) => apiClient.get<PaginatedResponse<QueueEntry>>('/admin/queue', { params }),
  assignQueue:    (entryId: string, body: { maker_id?: string; checker_id?: string }) => apiClient.post<APIResponse<{ entry_id: string }>>(`/admin/queue/${entryId}/assign`, body),
  reviewSummary:  (appId: string)                                                     => apiClient.get<APIResponse<ReviewSummary>>(`/admin/applications/${appId}/review-summary`),
  decide:         (appId: string, body: DecisionRequest)                              => apiClient.post<APIResponse<{ decision_id: string; action: string; new_status: string }>>(`/admin/applications/${appId}/decide`, body),
  activate:       (appId: string)                                                     => apiClient.post<APIResponse<AccountActivated>>(`/admin/applications/${appId}/activate`),
}

// ── Audit ─────────────────────────────────────────────────────────────────────
export const auditAPI = {
  listLogs:    (params?: { actor_id?: string; entity_type?: string; action?: string; page?: number }) => apiClient.get<PaginatedResponse<Record<string, unknown>>>('/audit/logs', { params }),
  entityTrail: (entityType: string, entityId: string) => apiClient.get<APIResponse<unknown[]>>(`/audit/logs/${entityType}/${entityId}`),
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
export const lifecycleAPI = {
  getSchedule:  (accountId: string)                        => apiClient.get<APIResponse<RefreshSchedule>>(`/lifecycle/accounts/${accountId}/refresh-schedule`),
  initiate:     (accountId: string)                        => apiClient.post<APIResponse<{ schedule_id: string; status: string }>>(`/lifecycle/accounts/${accountId}/refresh/initiate`),
  complete:     (accountId: string, tier?: string)         => apiClient.post<APIResponse<{ next_review_date: string; risk_tier: string }>>(`/lifecycle/accounts/${accountId}/refresh/complete`, null, { params: tier ? { new_risk_tier: tier } : {} }),
  overdue:      ()                                         => apiClient.get<APIResponse<ScheduleListItem[]>>('/lifecycle/accounts/overdue'),
  listAll:      (params?: { risk_tier?: string; status?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<ScheduleListItem>>('/lifecycle/accounts', { params }),
  sendReminder: (accountId: string)                        =>
    apiClient.post<APIResponse<{ schedule_id: string; reminder_count: number; last_reminder_at: string }>>(`/lifecycle/accounts/${accountId}/reminder`),
}

// ── Notifications ───────────────────────────────────────────────────────────────
export const notificationAPI = {
  listByUser: (params?: { status?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<NotificationRead>>('/notifications/me', { params }),
  listAll: (params?: { status?: string; notification_type?: string; channel?: string; user_id?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<NotificationRead>>('/notifications', { params }),
  retry: (notifId: string) =>
    apiClient.post<APIResponse<NotificationRead>>(`/notifications/${notifId}/retry`),
}
