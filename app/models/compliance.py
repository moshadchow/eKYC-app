"""
Domain 3 — AML Compliance & Risk Grading
All enum fields use sa_column=sa.Column(sa.String) to prevent
SQLAlchemy from generating Postgres native ENUM types.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.models.base import new_uuid, utcnow
from app.models.enums import (
    CDDStatus,
    EDDStatus,
    EDDTriggerReason,
    RiskClassification,
    ScreenResult,
    ScreenType,
)


# ── screening_results ─────────────────────────────────────────────────────────

class ScreeningResultBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    screen_type: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    list_source: str = Field(max_length=100)
    matched_name: Optional[str] = Field(default=None, max_length=255)
    match_score: Optional[float] = Field(default=None)
    result: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    raw_response: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    requires_review: bool = Field(default=False)
    reviewed_by: Optional[str] = Field(default=None, max_length=100)
    reviewed_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )


class ScreeningResult(ScreeningResultBase, table=True):
    __tablename__ = "screening_results"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    screened_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class ScreeningResultCreate(ScreeningResultBase):
    pass


class ScreeningResultRead(ScreeningResultBase):
    id: uuid.UUID
    screened_at: datetime


# ── pep_ip_checks ─────────────────────────────────────────────────────────────

class PEPIPCheckBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id", unique=True, index=True
    )
    is_pep: bool = Field(default=False)
    is_ip: bool = Field(default=False)
    is_family_of_pep: bool = Field(default=False)
    is_family_of_ip: bool = Field(default=False)
    is_high_official_intl_org: bool = Field(default=False)
    match_detail: Optional[str] = Field(default=None, max_length=1000)
    edd_required: bool = Field(default=False)


class PEPIPCheck(PEPIPCheckBase, table=True):
    __tablename__ = "pep_ip_checks"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    checked_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class PEPIPCheckCreate(PEPIPCheckBase):
    pass


class PEPIPCheckRead(PEPIPCheckBase):
    id: uuid.UUID
    checked_at: datetime


# ── beneficial_owners ─────────────────────────────────────────────────────────

class BeneficialOwnerBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    full_name: str = Field(max_length=255)
    nid_number: Optional[str] = Field(default=None, max_length=20)
    ownership_percentage: Optional[float] = Field(default=None)
    is_pep: bool = Field(default=False)
    is_ip: bool = Field(default=False)
    cdd_status: str = Field(
        default=CDDStatus.pending,
        sa_column=sa.Column(sa.String(20), nullable=False, server_default="pending"),
    )
    cdd_notes: Optional[str] = Field(default=None, max_length=1000)


class BeneficialOwner(BeneficialOwnerBase, table=True):
    __tablename__ = "beneficial_owners"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class BeneficialOwnerCreate(BeneficialOwnerBase):
    pass


class BeneficialOwnerRead(BeneficialOwnerBase):
    id: uuid.UUID
    created_at: datetime


# ── risk_scores ───────────────────────────────────────────────────────────────

class RiskScoreBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    score_onboarding_channel: int = Field()
    score_geography: int = Field()
    score_customer_type: int = Field()
    score_product: int = Field()
    score_business_activity: int = Field()
    score_profession: int = Field()
    score_transaction_volume: int = Field()
    score_transparency: int = Field()
    total_score: int = Field()
    risk_classification: str = Field(
        sa_column=sa.Column(sa.String(10), nullable=False),
    )
    edd_required: bool = Field(default=False)
    version: int = Field(default=1)


class RiskScore(RiskScoreBase, table=True):
    __tablename__ = "risk_scores"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    scored_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class RiskScoreCreate(RiskScoreBase):
    pass


class RiskScoreRead(RiskScoreBase):
    id: uuid.UUID
    scored_at: datetime


# ── edd_requests ──────────────────────────────────────────────────────────────

def _edd_deadline() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=30)


class EDDRequestBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    risk_score_id: uuid.UUID = Field(foreign_key="risk_scores.id")
    trigger_reason: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    required_documents: Optional[str] = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    status: str = Field(
        default=EDDStatus.pending,
        sa_column=sa.Column(sa.String(30), nullable=False, server_default="pending"),
    )
    compliance_officer_id: Optional[str] = Field(default=None, max_length=100)
    compliance_notes: Optional[str] = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    responded_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )
    deadline_at: datetime = Field(
        default_factory=_edd_deadline,
        nullable=False,
    )


class EDDRequest(EDDRequestBase, table=True):
    __tablename__ = "edd_requests"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    requested_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class EDDRequestCreate(EDDRequestBase):
    pass


class EDDRequestRead(EDDRequestBase):
    id: uuid.UUID
    requested_at: datetime


# ── edd_documents ─────────────────────────────────────────────────────────────

class EDDDocumentBase(SQLModel):
    edd_request_id: uuid.UUID = Field(foreign_key="edd_requests.id", index=True)
    document_type: str = Field(max_length=100)
    storage_key: str = Field(max_length=512)
    checksum_sha256: str = Field(max_length=64)


class EDDDocument(EDDDocumentBase, table=True):
    __tablename__ = "edd_documents"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    uploaded_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class EDDDocumentCreate(EDDDocumentBase):
    pass


class EDDDocumentRead(EDDDocumentBase):
    id: uuid.UUID
    uploaded_at: datetime
