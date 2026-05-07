"""
Domain 2 — Onboarding & KYC Profile
All enum fields use sa_column=sa.Column(sa.String) to prevent
SQLAlchemy from generating Postgres native ENUM types.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.models.base import TimestampMixin, new_uuid, utcnow
from app.models.enums import (
    ApplicationStatus,
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
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    agent_id: Optional[uuid.UUID] = Field(default=None, foreign_key="agents.id", index=True)
    kyc_type: str = Field(
        sa_column=sa.Column(sa.String(20), nullable=False),
    )
    onboarding_channel: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    product_type: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    product_code: Optional[str] = Field(default=None, max_length=50)
    expected_investment: Optional[Decimal] = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(18, 2), nullable=True),
    )
    status: str = Field(
        default=ApplicationStatus.draft,
        sa_column=sa.Column(sa.String(30), nullable=False, server_default="draft"),
    )
    application_ref: Optional[str] = Field(default=None, max_length=30, unique=True, index=True)
    submitted_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
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
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", unique=True, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    full_name_en: str = Field(max_length=255)
    full_name_bn: Optional[str] = Field(default=None, max_length=255)
    fathers_name_en: Optional[str] = Field(default=None, max_length=255)
    fathers_name_bn: Optional[str] = Field(default=None, max_length=255)
    mothers_name_en: Optional[str] = Field(default=None, max_length=255)
    mothers_name_bn: Optional[str] = Field(default=None, max_length=255)
    spouse_name_en: Optional[str] = Field(default=None, max_length=255)
    date_of_birth: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    gender: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(1), nullable=True),
    )
    nid_number: str = Field(max_length=20, index=True)
    tin_number: Optional[str] = Field(default=None, max_length=20)
    profession: Optional[str] = Field(default=None, max_length=255)
    monthly_income: Optional[Decimal] = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(18, 2), nullable=True),
    )
    source_of_fund: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(30), nullable=True),
    )
    source_of_fund_detail: Optional[str] = Field(default=None, max_length=500)
    mobile_number: str = Field(max_length=15)
    email: Optional[str] = Field(default=None, max_length=255)
    present_address: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    permanent_address: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    nationality: str = Field(default="Bangladeshi", max_length=100)
    residency_status: str = Field(
        default=ResidencyStatus.resident_bangladeshi,
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    is_pep: bool = Field(default=False)
    is_ip: bool = Field(default=False)
    is_nrb: bool = Field(default=False)


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
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    full_name: str = Field(max_length=255)
    date_of_birth: Optional[date] = Field(default=None, sa_column=sa.Column(sa.Date, nullable=True))
    relation: str = Field(
        sa_column=sa.Column(sa.String(20), nullable=False),
    )
    contact_number: Optional[str] = Field(default=None, max_length=15)
    address: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    photo_storage_key: Optional[str] = Field(default=None, max_length=512)
    is_minor: bool = Field(default=False)
    guardian_name: Optional[str] = Field(default=None, max_length=255)
    guardian_nid: Optional[str] = Field(default=None, max_length=20)
    guardian_address: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    guardian_photo_storage_key: Optional[str] = Field(default=None, max_length=512)


class Nominee(NomineeBase, table=True):
    __tablename__ = "nominees"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class NomineeCreate(NomineeBase):
    pass


class NomineeRead(NomineeBase):
    id: uuid.UUID
    created_at: datetime


# ── kyc_documents ─────────────────────────────────────────────────────────────

class KYCDocumentBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    document_type: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    storage_key: str = Field(max_length=512)
    original_filename: Optional[str] = Field(default=None, max_length=255)
    mime_type: str = Field(max_length=100)
    file_size_bytes: int = Field()
    checksum_sha256: str = Field(max_length=64)
    is_encrypted: bool = Field(default=True)
    version: int = Field(default=1)


class KYCDocument(KYCDocumentBase, table=True):
    __tablename__ = "kyc_documents"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    uploaded_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class KYCDocumentCreate(KYCDocumentBase):
    pass


class KYCDocumentRead(KYCDocumentBase):
    id: uuid.UUID
    uploaded_at: datetime


# ── biometric_verifications ───────────────────────────────────────────────────

class BiometricVerificationBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    verification_type: str = Field(
        sa_column=sa.Column(sa.String(20), nullable=False),
    )
    nid_number: str = Field(max_length=20)
    dob_provided: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    similarity_score: Optional[float] = Field(default=None)
    is_matched: bool = Field(default=False)
    attempt_number: int = Field()
    session_number: int = Field()
    ip_address: Optional[str] = Field(default=None, max_length=45)
    device_info: Optional[str] = Field(default=None, max_length=512)
    mock_api_response: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )
    failure_reason: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(50), nullable=True),
    )


class BiometricVerification(BiometricVerificationBase, table=True):
    __tablename__ = "biometric_verifications"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    verified_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class BiometricVerificationCreate(BiometricVerificationBase):
    pass


class BiometricVerificationRead(BiometricVerificationBase):
    id: uuid.UUID
    verified_at: datetime


# ── ocr_extractions ───────────────────────────────────────────────────────────

class OCRExtractionBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    document_id: uuid.UUID = Field(foreign_key="kyc_documents.id")
    raw_json: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    extracted_name_en: Optional[str] = Field(default=None, max_length=255)
    extracted_name_bn: Optional[str] = Field(default=None, max_length=255)
    extracted_nid: Optional[str] = Field(default=None, max_length=20)
    extracted_dob: Optional[date] = Field(default=None, sa_column=sa.Column(sa.Date, nullable=True))
    extracted_address: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    extracted_fathers_name: Optional[str] = Field(default=None, max_length=255)
    extracted_mothers_name: Optional[str] = Field(default=None, max_length=255)
    confidence_score: Optional[float] = Field(default=None)


class OCRExtraction(OCRExtractionBase, table=True):
    __tablename__ = "ocr_extractions"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

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
        foreign_key="kyc_applications.id", unique=True, index=True
    )
    signature_type: str = Field(
        sa_column=sa.Column(sa.String(20), nullable=False),
    )
    storage_key: Optional[str] = Field(default=None, max_length=512)
    pin_hash: Optional[str] = Field(default=None, max_length=128)
    is_low_risk_pin: bool = Field(default=False)


class DigitalSignature(DigitalSignatureBase, table=True):
    __tablename__ = "digital_signatures"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    captured_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class DigitalSignatureCreate(DigitalSignatureBase):
    pass


class DigitalSignatureRead(DigitalSignatureBase):
    id: uuid.UUID
    captured_at: datetime
