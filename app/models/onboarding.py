"""
Domain 2 — Onboarding & KYC Profile
Tables: kyc_applications, customer_profiles, nominees,
        kyc_documents, biometric_verifications,
        ocr_extractions, digital_signatures
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlmodel import Field, SQLModel

from .base import TimestampMixin, new_uuid, utcnow
from .enums import (
    ApplicationStatus,
    BiometricFailureReason,
    BiometricVerificationType,
    DocumentType,
    Gender,
    KYCType,
    NomineeRelation,
    OnboardingChannel,
    ProductType,
    ResidencyStatus,
    SignatureType,
    SourceOfFund,
)


# ── kyc_applications ──────────────────────────────────────────────────────────

class KYCApplicationBase(SQLModel):
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="FK → users.id — the applicant",
    )
    agent_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="agents.id",
        index=True,
        description="FK → agents.id — null for self check-in",
    )
    kyc_type: KYCType = Field(
        description="simplified or regular, set by decision engine",
    )
    onboarding_channel: OnboardingChannel = Field(
        description="How the customer is being onboarded",
    )
    product_type: ProductType = Field(
        description="BO account, life insurance, or non-life insurance",
    )
    product_code: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Institution-specific product identifier",
    )
    expected_investment: Optional[Decimal] = Field(
        default=None,
        decimal_places=2,
        max_digits=18,
        description="Expected investment/sum assured in BDT",
    )
    status: ApplicationStatus = Field(
        default=ApplicationStatus.draft,
        index=True,
        description="State machine status of the application",
    )
    application_ref: Optional[str] = Field(
        default=None,
        max_length=30,
        unique=True,
        index=True,
        description="Human-readable reference e.g. EKYC-2026-000001",
    )
    submitted_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when customer submitted the application",
    )


class KYCApplication(KYCApplicationBase, TimestampMixin, table=True):
    __tablename__ = "kyc_applications"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    class Config:
        arbitrary_types_allowed = True


class KYCApplicationCreate(KYCApplicationBase):
    pass


class KYCApplicationRead(KYCApplicationBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime]


# ── customer_profiles ─────────────────────────────────────────────────────────

class CustomerProfileBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        unique=True,
        index=True,
        description="FK → kyc_applications.id (one profile per application)",
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
    )

    # Personal information (English)
    full_name_en: str = Field(max_length=255, description="Name from NID — English")
    fathers_name_en: Optional[str] = Field(default=None, max_length=255)
    mothers_name_en: Optional[str] = Field(default=None, max_length=255)
    spouse_name_en: Optional[str] = Field(default=None, max_length=255)

    # Personal information (Bangla — from OCR)
    full_name_bn: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Name from NID — Bangla script",
    )
    fathers_name_bn: Optional[str] = Field(default=None, max_length=255)
    mothers_name_bn: Optional[str] = Field(default=None, max_length=255)

    # Identity fields
    date_of_birth: date = Field(description="Non-editable after biometric verification")
    gender: Optional[Gender] = Field(default=None)
    nid_number: str = Field(
        max_length=20,
        index=True,
        description="National ID number — non-editable after biometric verification",
    )
    tin_number: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Tax Identification Number — required for regular eKYC",
    )

    # Financial profile
    profession: Optional[str] = Field(default=None, max_length=255)
    monthly_income: Optional[Decimal] = Field(
        default=None,
        decimal_places=2,
        max_digits=18,
        description="Monthly income in BDT",
    )
    source_of_fund: Optional[SourceOfFund] = Field(default=None)
    source_of_fund_detail: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Free-text description when source_of_fund = other",
    )

    # Contact
    mobile_number: str = Field(max_length=15, description="Verified mobile number")
    email: Optional[str] = Field(default=None, max_length=255)

    # Address
    present_address: Optional[str] = Field(default=None, max_length=500)
    permanent_address: Optional[str] = Field(default=None, max_length=500)
    nationality: str = Field(default="Bangladeshi", max_length=100)
    residency_status: ResidencyStatus = Field(
        default=ResidencyStatus.resident_bangladeshi,
    )

    # Risk flags — populated by Phase 2 questionnaire and Phase 7 screening
    is_pep: bool = Field(default=False, description="Politically Exposed Person")
    is_ip: bool = Field(default=False, description="Influential Person per BFIU")
    is_nrb: bool = Field(default=False, description="Non-Resident Bangladeshi")


class CustomerProfile(CustomerProfileBase, TimestampMixin, table=True):
    __tablename__ = "customer_profiles"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    class Config:
        arbitrary_types_allowed = True


class CustomerProfileCreate(CustomerProfileBase):
    pass


class CustomerProfileRead(CustomerProfileBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime]


# ── nominees ──────────────────────────────────────────────────────────────────

class NomineeBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )
    full_name: str = Field(max_length=255)
    date_of_birth: Optional[date] = Field(default=None)
    relation: NomineeRelation = Field(description="Relationship to the applicant")
    contact_number: Optional[str] = Field(default=None, max_length=15)
    address: Optional[str] = Field(default=None, max_length=500)
    photo_storage_key: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Object storage key for nominee photo",
    )

    # Minor nominee fields
    is_minor: bool = Field(default=False)
    guardian_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Guardian name — required when is_minor = true",
    )
    guardian_nid: Optional[str] = Field(default=None, max_length=20)
    guardian_address: Optional[str] = Field(default=None, max_length=500)
    guardian_photo_storage_key: Optional[str] = Field(default=None, max_length=512)


class Nominee(NomineeBase, table=True):
    __tablename__ = "nominees"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class NomineeCreate(NomineeBase):
    pass


class NomineeRead(NomineeBase):
    id: uuid.UUID
    created_at: datetime


# ── kyc_documents ─────────────────────────────────────────────────────────────

class KYCDocumentBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )
    document_type: DocumentType = Field(description="Type of document stored")
    storage_key: str = Field(
        max_length=512,
        description="Object storage path — AES-256 encrypted at rest",
    )
    original_filename: Optional[str] = Field(default=None, max_length=255)
    mime_type: str = Field(max_length=100, description="e.g. image/jpeg, image/png")
    file_size_bytes: int = Field(description="File size for quota tracking")
    checksum_sha256: str = Field(
        max_length=64,
        description="SHA-256 of the unencrypted file — for integrity verification",
    )
    is_encrypted: bool = Field(default=True)
    version: int = Field(
        default=1,
        description="Incremented on document replacement; previous rows are kept",
    )


class KYCDocument(KYCDocumentBase, table=True):
    __tablename__ = "kyc_documents"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    uploaded_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class KYCDocumentCreate(KYCDocumentBase):
    pass


class KYCDocumentRead(KYCDocumentBase):
    id: uuid.UUID
    uploaded_at: datetime


# ── biometric_verifications ───────────────────────────────────────────────────

class BiometricVerificationBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )
    verification_type: BiometricVerificationType = Field(
        description="face_match or fingerprint",
    )
    nid_number: str = Field(
        max_length=20,
        description="NID number submitted for matching",
    )
    dob_provided: date = Field(
        description="DOB submitted along with NID for first-factor check",
    )

    # Result
    similarity_score: Optional[float] = Field(
        default=None,
        description="0.0 – 100.0 similarity from EC mock API",
    )
    is_matched: bool = Field(
        default=False,
        description="True when similarity_score exceeds configured threshold",
    )

    # Retry tracking — enforce 10 tries/session, 2 sessions/day, 3 sessions total
    attempt_number: int = Field(
        description="1-based attempt counter within the session",
    )
    session_number: int = Field(
        description="1-based session counter for this application (max 3)",
    )

    # Contextual metadata for audit
    ip_address: Optional[str] = Field(default=None, max_length=45)
    device_info: Optional[str] = Field(default=None, max_length=512)

    # Raw response from mock EC API — stored for audit trail
    mock_api_response: Optional[str] = Field(
        default=None,
        description="Full JSON response from the biometric verification API",
    )
    failure_reason: Optional[BiometricFailureReason] = Field(default=None)


class BiometricVerification(BiometricVerificationBase, table=True):
    __tablename__ = "biometric_verifications"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    verified_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class BiometricVerificationCreate(BiometricVerificationBase):
    pass


class BiometricVerificationRead(BiometricVerificationBase):
    id: uuid.UUID
    verified_at: datetime


# ── ocr_extractions ───────────────────────────────────────────────────────────

class OCRExtractionBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )
    document_id: uuid.UUID = Field(
        foreign_key="kyc_documents.id",
        description="FK → the NID image that was processed",
    )

    # Raw output — always preserved regardless of what fields were corrected
    raw_json: str = Field(
        description="Full JSON string from OCR engine — immutable after creation",
    )

    # Parsed fields (English)
    extracted_name_en: Optional[str] = Field(default=None, max_length=255)
    extracted_name_bn: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Bangla name extracted from NID front",
    )
    extracted_nid: Optional[str] = Field(default=None, max_length=20)
    extracted_dob: Optional[date] = Field(default=None)
    extracted_address: Optional[str] = Field(default=None, max_length=500)
    extracted_fathers_name: Optional[str] = Field(default=None, max_length=255)
    extracted_mothers_name: Optional[str] = Field(default=None, max_length=255)

    # Quality
    confidence_score: Optional[float] = Field(
        default=None,
        description="Overall OCR confidence 0.0 – 1.0",
    )


class OCRExtraction(OCRExtractionBase, table=True):
    __tablename__ = "ocr_extractions"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class OCRExtractionCreate(OCRExtractionBase):
    pass


class OCRExtractionRead(OCRExtractionBase):
    id: uuid.UUID
    created_at: datetime


# ── digital_signatures ────────────────────────────────────────────────────────

class DigitalSignatureBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        unique=True,
        index=True,
        description="One signature record per application",
    )
    signature_type: SignatureType = Field(
        description="wet | electronic | digital | pin",
    )
    storage_key: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Object storage key for wet/electronic signature image",
    )
    pin_hash: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Bcrypt hash of PIN — only set when signature_type = pin",
    )
    is_low_risk_pin: bool = Field(
        default=False,
        description="PIN/digital signature only permitted for low-risk accounts",
    )


class DigitalSignature(DigitalSignatureBase, table=True):
    __tablename__ = "digital_signatures"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    captured_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class DigitalSignatureCreate(DigitalSignatureBase):
    pass


class DigitalSignatureRead(DigitalSignatureBase):
    id: uuid.UUID
    captured_at: datetime
