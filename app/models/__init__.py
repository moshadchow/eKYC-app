"""
eKYC Models Package
Exports all SQLModel table classes and their Create/Read schemas.
Import from here in routers, services, and migrations.
"""

from .enums import (
    AccountStatus,
    AccountType,
    ActorType,
    AgentRole,
    ApprovalAction,
    ApplicationStatus,
    AuditAction,
    BiometricFailureReason,
    BiometricVerificationType,
    CDDStatus,
    DocumentType,
    EDDStatus,
    EDDTriggerReason,
    Gender,
    KYCType,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    NomineeRelation,
    OnboardingChannel,
    OTPPurpose,
    PreCheckDecision,
    ProductType,
    QueuePriority,
    QueueStatus,
    QueueType,
    RefreshEventType,
    RefreshStatus,
    ResidencyStatus,
    RiskClassification,
    ScreenResult,
    ScreenType,
    SignatureType,
    SourceOfFund,
    UserStatus,
)

from .identity import (
    User, UserCreate, UserRead,
    OTPLog, OTPLogCreate,
    Session, SessionCreate,
    Agent, AgentCreate, AgentRead,
    AgentDevice, AgentDeviceCreate,
    AgentSession, AgentSessionCreate,
)

from .onboarding import (
    KYCApplication, KYCApplicationCreate, KYCApplicationRead,
    CustomerProfile, CustomerProfileCreate, CustomerProfileRead,
    Nominee, NomineeCreate, NomineeRead,
    KYCDocument, KYCDocumentCreate, KYCDocumentRead,
    BiometricVerification, BiometricVerificationCreate, BiometricVerificationRead,
    OCRExtraction, OCRExtractionCreate, OCRExtractionRead,
    DigitalSignature, DigitalSignatureCreate, DigitalSignatureRead,
)

from .compliance import (
    ScreeningResult, ScreeningResultCreate, ScreeningResultRead,
    PEPIPCheck, PEPIPCheckCreate, PEPIPCheckRead,
    BeneficialOwner, BeneficialOwnerCreate, BeneficialOwnerRead,
    RiskScore, RiskScoreCreate, RiskScoreRead,
    EDDRequest, EDDRequestCreate, EDDRequestRead,
    EDDDocument, EDDDocumentCreate, EDDDocumentRead,
)

from .workflow import (
    PreCheckLog, PreCheckLogCreate, PreCheckLogRead,
    ApprovalQueue, ApprovalQueueCreate, ApprovalQueueRead,
    ApprovalDecision, ApprovalDecisionCreate, ApprovalDecisionRead,
    Account, AccountCreate, AccountRead,
    AuditLog, AuditLogRead,
    Notification, NotificationCreate, NotificationRead,
    KYCRefreshSchedule, KYCRefreshScheduleCreate, KYCRefreshScheduleRead,
    KYCRefreshEvent, KYCRefreshEventCreate, KYCRefreshEventRead,
)

__all__ = [
    # Enums
    "AccountStatus", "AccountType", "ActorType", "AgentRole",
    "ApprovalAction", "ApplicationStatus", "AuditAction",
    "BiometricFailureReason", "BiometricVerificationType", "CDDStatus",
    "DocumentType", "EDDStatus", "EDDTriggerReason", "Gender",
    "KYCType", "NotificationChannel", "NotificationStatus", "NotificationType",
    "NomineeRelation", "OnboardingChannel", "OTPPurpose", "PreCheckDecision",
    "ProductType", "QueuePriority", "QueueStatus", "QueueType",
    "RefreshEventType", "RefreshStatus", "ResidencyStatus", "RiskClassification",
    "ScreenResult", "ScreenType", "SignatureType", "SourceOfFund", "UserStatus",

    # Domain 1 — Identity
    "User", "UserCreate", "UserRead",
    "OTPLog", "OTPLogCreate",
    "Session", "SessionCreate",
    "Agent", "AgentCreate", "AgentRead",
    "AgentDevice", "AgentDeviceCreate",
    "AgentSession", "AgentSessionCreate",

    # Domain 2 — Onboarding
    "KYCApplication", "KYCApplicationCreate", "KYCApplicationRead",
    "CustomerProfile", "CustomerProfileCreate", "CustomerProfileRead",
    "Nominee", "NomineeCreate", "NomineeRead",
    "KYCDocument", "KYCDocumentCreate", "KYCDocumentRead",
    "BiometricVerification", "BiometricVerificationCreate", "BiometricVerificationRead",
    "OCRExtraction", "OCRExtractionCreate", "OCRExtractionRead",
    "DigitalSignature", "DigitalSignatureCreate", "DigitalSignatureRead",

    # Domain 3 — Compliance
    "ScreeningResult", "ScreeningResultCreate", "ScreeningResultRead",
    "PEPIPCheck", "PEPIPCheckCreate", "PEPIPCheckRead",
    "BeneficialOwner", "BeneficialOwnerCreate", "BeneficialOwnerRead",
    "RiskScore", "RiskScoreCreate", "RiskScoreRead",
    "EDDRequest", "EDDRequestCreate", "EDDRequestRead",
    "EDDDocument", "EDDDocumentCreate", "EDDDocumentRead",

    # Domain 4 — Workflow
    "PreCheckLog", "PreCheckLogCreate", "PreCheckLogRead",
    "ApprovalQueue", "ApprovalQueueCreate", "ApprovalQueueRead",
    "ApprovalDecision", "ApprovalDecisionCreate", "ApprovalDecisionRead",
    "Account", "AccountCreate", "AccountRead",
    "AuditLog", "AuditLogRead",
    "Notification", "NotificationCreate", "NotificationRead",
    "KYCRefreshSchedule", "KYCRefreshScheduleCreate", "KYCRefreshScheduleRead",
    "KYCRefreshEvent", "KYCRefreshEventCreate", "KYCRefreshEventRead",
]
