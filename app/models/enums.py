from enum import Enum


# ── Auth / Session ────────────────────────────────────────────────────────────

class UserStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    locked = "locked"


class OTPPurpose(str, Enum):
    customer_login = "customer_login"
    agent_2fa = "agent_2fa"
    customer_mobile_ownership = "customer_mobile_ownership"
    kyc_refresh = "kyc_refresh"


class AgentRole(str, Enum):
    maker = "maker"
    checker = "checker"
    compliance_officer = "compliance_officer"
    system_admin = "system_admin"
    system_auditor = "system_auditor"


# ── Onboarding / KYC ─────────────────────────────────────────────────────────

class KYCType(str, Enum):
    simplified = "simplified"
    regular = "regular"


class OnboardingChannel(str, Enum):
    self_checkin = "self_checkin"
    assisted = "assisted"
    branch = "branch"
    internet = "internet"


class ProductType(str, Enum):
    bo_account = "bo_account"
    life_insurance = "life_insurance"
    non_life_insurance = "non_life_insurance"


class ApplicationStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    screening = "screening"
    risk_grading = "risk_grading"
    edd_pending = "edd_pending"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class Gender(str, Enum):
    male = "M"
    female = "F"
    third_gender = "T"


class ResidencyStatus(str, Enum):
    resident_bangladeshi = "resident_bangladeshi"
    non_resident_bangladeshi = "non_resident_bangladeshi"


class SourceOfFund(str, Enum):
    salary = "salary"
    business = "business"
    investment = "investment"
    inheritance = "inheritance"
    remittance = "remittance"
    pension = "pension"
    other = "other"


class DocumentType(str, Enum):
    nid_front = "nid_front"
    nid_back = "nid_back"
    customer_photo = "customer_photo"
    nominee_photo = "nominee_photo"
    signature = "signature"
    edd_document = "edd_document"
    guardian_nid = "guardian_nid"
    other = "other"


class BiometricVerificationType(str, Enum):
    face_match = "face_match"
    fingerprint = "fingerprint"


class BiometricFailureReason(str, Enum):
    low_similarity = "low_similarity"
    liveness_failed = "liveness_failed"
    poor_image_quality = "poor_image_quality"
    nid_not_found = "nid_not_found"
    api_error = "api_error"
    max_attempts_reached = "max_attempts_reached"


class SignatureType(str, Enum):
    wet = "wet"
    electronic = "electronic"
    digital = "digital"
    pin = "pin"


class NomineeRelation(str, Enum):
    spouse = "spouse"
    son = "son"
    daughter = "daughter"
    father = "father"
    mother = "mother"
    brother = "brother"
    sister = "sister"
    other = "other"


# ── Compliance / Risk ─────────────────────────────────────────────────────────

class ScreenType(str, Enum):
    un_sanctions = "un_sanctions"
    internal_blacklist = "internal_blacklist"
    adverse_media = "adverse_media"


class ScreenResult(str, Enum):
    clear = "clear"
    potential_match = "potential_match"
    confirmed_match = "confirmed_match"
    requires_review = "requires_review"


class RiskClassification(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class EDDTriggerReason(str, Enum):
    high_risk_score = "high_risk_score"
    pep_match = "pep_match"
    ip_match = "ip_match"
    sanctions_match = "sanctions_match"
    adverse_media = "adverse_media"
    manual_override = "manual_override"
    risk_upgrade = "risk_upgrade"


class EDDStatus(str, Enum):
    pending = "pending"
    documents_received = "documents_received"
    under_review = "under_review"
    completed = "completed"
    expired = "expired"


class CDDStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    not_required = "not_required"


# ── Approval / Workflow ───────────────────────────────────────────────────────

class QueueType(str, Enum):
    standard = "standard"
    high_risk = "high_risk"
    failed_verification = "failed_verification"
    edd_pending = "edd_pending"


class QueuePriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class QueueStatus(str, Enum):
    unassigned = "unassigned"
    in_review = "in_review"
    completed = "completed"
    escalated = "escalated"


class ApprovalAction(str, Enum):
    approve = "approve"
    reject = "reject"
    request_more_info = "request_more_info"
    escalate = "escalate"
    override_risk = "override_risk"


class ActorType(str, Enum):
    customer = "customer"
    agent = "agent"
    system = "system"


class AccountStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    closed = "closed"
    pending_kyc_refresh = "pending_kyc_refresh"


class AccountType(str, Enum):
    bo_account = "bo_account"
    life_insurance_policy = "life_insurance_policy"
    non_life_insurance_policy = "non_life_insurance_policy"


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationChannel(str, Enum):
    sms = "sms"
    email = "email"
    push = "push"


class NotificationType(str, Enum):
    otp = "otp"
    submission_confirmation = "submission_confirmation"
    approval = "approval"
    rejection = "rejection"
    edd_request = "edd_request"
    kyc_refresh_reminder = "kyc_refresh_reminder"
    account_activation = "account_activation"
    failed_ekyc = "failed_ekyc"


class NotificationStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditAction(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"
    login = "login"
    logout = "logout"
    login_failed = "login_failed"
    otp_sent = "otp_sent"
    otp_verified = "otp_verified"
    biometric_attempt = "biometric_attempt"
    biometric_success = "biometric_success"
    biometric_failure = "biometric_failure"
    screening_run = "screening_run"
    risk_scored = "risk_scored"
    edd_triggered = "edd_triggered"
    approval_decision = "approval_decision"
    account_activated = "account_activated"
    kyc_refresh_completed = "kyc_refresh_completed"


# ── KYC Lifecycle ─────────────────────────────────────────────────────────────

class RefreshStatus(str, Enum):
    scheduled = "scheduled"
    reminder_sent = "reminder_sent"
    in_progress = "in_progress"
    completed = "completed"
    overdue = "overdue"
    escalated = "escalated"


class RefreshEventType(str, Enum):
    scheduled = "scheduled"
    reminder_sent = "reminder_sent"
    customer_response = "customer_response"
    completed = "completed"
    upgraded_to_regular = "upgraded_to_regular"
    risk_reclassified = "risk_reclassified"


class PreCheckDecision(str, Enum):
    simplified = "simplified"
    regular = "regular"
    rejected = "rejected"
