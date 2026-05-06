"""
Domain 3 — AML Compliance & Risk Grading
Tables: screening_results, pep_ip_checks, beneficial_owners,
        risk_scores, edd_requests, edd_documents
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlmodel import Field, SQLModel

from .base import TimestampMixin, new_uuid, utcnow
from .enums import (
    CDDStatus,
    EDDStatus,
    EDDTriggerReason,
    RiskClassification,
    ScreenResult,
    ScreenType,
)


# ── screening_results ─────────────────────────────────────────────────────────

class ScreeningResultBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )
    screen_type: ScreenType = Field(
        description="un_sanctions | internal_blacklist | adverse_media",
    )
    list_source: str = Field(
        max_length=100,
        description="e.g. 'UN SCSR', 'BFIU Internal', 'News API'",
    )

    # Match details
    matched_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Name that triggered the match, if any",
    )
    match_score: Optional[float] = Field(
        default=None,
        description="Fuzzy match similarity 0.0 – 1.0",
    )
    result: ScreenResult = Field(description="Outcome of this screening run")
    raw_response: Optional[str] = Field(
        default=None,
        description="Full JSON from external screening API — for audit",
    )

    # Review
    requires_review: bool = Field(
        default=False,
        description="True when result = potential_match or confirmed_match",
    )
    reviewed_by: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Agent/officer ID who reviewed the match",
    )
    reviewed_at: Optional[datetime] = Field(default=None)


class ScreeningResult(ScreeningResultBase, table=True):
    __tablename__ = "screening_results"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    screened_at: datetime = Field(default_factory=utcnow, nullable=False)

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
        foreign_key="kyc_applications.id",
        unique=True,
        index=True,
        description="One PEP/IP check record per application",
    )

    # PEP flags
    is_pep: bool = Field(default=False, description="Customer is a PEP")
    is_ip: bool = Field(
        default=False,
        description="Customer is an Influential Person per BFIU circular",
    )
    is_family_of_pep: bool = Field(
        default=False,
        description="Customer is a family member or close associate of a PEP",
    )
    is_family_of_ip: bool = Field(
        default=False,
        description="Customer is a family member or close associate of an IP",
    )
    is_high_official_intl_org: bool = Field(
        default=False,
        description="Chief or high official of an international organization",
    )

    match_detail: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Description of the match e.g. name, position, database source",
    )
    edd_required: bool = Field(
        default=False,
        description="True when any PEP/IP flag is set — triggers EDD",
    )


class PEPIPCheck(PEPIPCheckBase, table=True):
    __tablename__ = "pep_ip_checks"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    checked_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class PEPIPCheckCreate(PEPIPCheckBase):
    pass


class PEPIPCheckRead(PEPIPCheckBase):
    id: uuid.UUID
    checked_at: datetime


# ── beneficial_owners ─────────────────────────────────────────────────────────

class BeneficialOwnerBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )
    full_name: str = Field(max_length=255)
    nid_number: Optional[str] = Field(
        default=None,
        max_length=20,
        description="NID of the beneficial owner if available",
    )
    ownership_percentage: Optional[float] = Field(
        default=None,
        description="Ownership stake percentage — applicable for corporate accounts",
    )

    # Risk flags for this beneficial owner
    is_pep: bool = Field(default=False)
    is_ip: bool = Field(default=False)

    # CDD status — if BO is PEP, enhanced CDD must be conducted on them
    cdd_status: CDDStatus = Field(
        default=CDDStatus.pending,
        description="CDD status for this specific beneficial owner",
    )
    cdd_notes: Optional[str] = Field(default=None, max_length=1000)


class BeneficialOwner(BeneficialOwnerBase, table=True):
    __tablename__ = "beneficial_owners"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class BeneficialOwnerCreate(BeneficialOwnerBase):
    pass


class BeneficialOwnerRead(BeneficialOwnerBase):
    id: uuid.UUID
    created_at: datetime


# ── risk_scores ───────────────────────────────────────────────────────────────

class RiskScoreBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )

    # Individual factor scores — stored separately for full transparency
    # and to support per-field explanation in the admin review UI.
    # All scores are integers per the BFIU risk grading form (section 6.3).

    score_onboarding_channel: int = Field(
        description="Walk-in=3, internet/self=2, branch/agent=2",
    )
    score_geography: int = Field(
        description="Resident BD=1, NRB=3",
    )
    score_customer_type: int = Field(
        description="PEP=5, IP=5, family of PEP/IP=5, none=0 or 1",
    )
    score_product: int = Field(
        description="CMI: individual BO=2. Insurance: ordinary life=1, UL=2, term=3",
    )
    score_business_activity: int = Field(
        description="Business risk score from Annexure-1 (1–5)",
    )
    score_profession: int = Field(
        description="Profession risk score from Annexure-1 (1–5)",
    )
    score_transaction_volume: int = Field(
        description="<1M=1, 1–5M=2, 5–50M=3, >50M=5",
    )
    score_transparency: int = Field(
        description="Source of fund credible: yes=1, no=5",
    )

    # Derived
    total_score: int = Field(
        description="Sum of all factor scores. Regular < 15, High >= 15",
    )
    risk_classification: RiskClassification = Field(
        description="low | medium | high — derived from total_score",
    )
    edd_required: bool = Field(
        default=False,
        description="True when risk_classification = high or PEP/IP flag is set",
    )

    # Versioning — re-scoring on profile changes increments this
    version: int = Field(
        default=1,
        description="Score version — earlier versions are retained for audit",
    )


class RiskScore(RiskScoreBase, table=True):
    __tablename__ = "risk_scores"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    scored_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class RiskScoreCreate(RiskScoreBase):
    pass


class RiskScoreRead(RiskScoreBase):
    id: uuid.UUID
    scored_at: datetime


# ── edd_requests ──────────────────────────────────────────────────────────────

def _edd_deadline() -> datetime:
    """Default EDD deadline = now + 30 days (BFIU mandated response window)."""
    return datetime.now(timezone.utc) + timedelta(days=30)


class EDDRequestBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )
    risk_score_id: uuid.UUID = Field(
        foreign_key="risk_scores.id",
        description="FK → the risk_score that triggered this EDD",
    )
    trigger_reason: EDDTriggerReason = Field(
        description="Why EDD was triggered",
    )
    required_documents: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="JSON array of required document types",
    )
    status: EDDStatus = Field(
        default=EDDStatus.pending,
        index=True,
    )

    # Compliance officer details
    compliance_officer_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Agent ID of the reviewing compliance officer",
    )
    compliance_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    # Timestamps
    responded_at: Optional[datetime] = Field(
        default=None,
        description="When customer/agent submitted EDD documents",
    )
    deadline_at: datetime = Field(
        default_factory=_edd_deadline,
        description="30-day window — account may be temporarily closed after this",
    )


class EDDRequest(EDDRequestBase, table=True):
    __tablename__ = "edd_requests"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    requested_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class EDDRequestCreate(EDDRequestBase):
    pass


class EDDRequestRead(EDDRequestBase):
    id: uuid.UUID
    requested_at: datetime


# ── edd_documents ─────────────────────────────────────────────────────────────

class EDDDocumentBase(SQLModel):
    edd_request_id: uuid.UUID = Field(
        foreign_key="edd_requests.id",
        index=True,
    )
    document_type: str = Field(
        max_length=100,
        description="Type of EDD document e.g. 'bank_statement', 'income_proof'",
    )
    storage_key: str = Field(
        max_length=512,
        description="Object storage path — encrypted at rest",
    )
    checksum_sha256: str = Field(
        max_length=64,
        description="Integrity checksum of the unencrypted file",
    )


class EDDDocument(EDDDocumentBase, table=True):
    __tablename__ = "edd_documents"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    uploaded_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class EDDDocumentCreate(EDDDocumentBase):
    pass


class EDDDocumentRead(EDDDocumentBase):
    id: uuid.UUID
    uploaded_at: datetime
