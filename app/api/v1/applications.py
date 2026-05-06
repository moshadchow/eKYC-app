"""
Phase 3 & 4 — Self & Assisted Onboarding
POST   /kyc/applications
GET    /kyc/applications/{app_id}
PUT    /kyc/applications/{app_id}/profile
POST   /kyc/applications/{app_id}/nominees
POST   /kyc/applications/{app_id}/signature
POST   /kyc/applications/{app_id}/submit
GET    /kyc/applications                    (agent - list queue)
PUT    /kyc/applications/{app_id}/status    (agent)
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select

from ...core.config import settings
from ...core.deps import CurrentAgent, CurrentUser, DBSession
from ...core.security import generate_application_ref
from ...models.base import utcnow
from ...models.enums import (
    ActorType,
    ApplicationStatus,
    AuditAction,
    Gender,
    KYCType,
    NomineeRelation,
    OnboardingChannel,
    ProductType,
    ResidencyStatus,
    SignatureType,
    SourceOfFund,
)
from ...models.identity import User
from ...models.onboarding import (
    CustomerProfile,
    DigitalSignature,
    KYCApplication,
    Nominee,
)
from ...schemas.common import APIResponse, MessageResponse, PaginatedResponse
from ...services.audit import record_event

router = APIRouter(prefix="/kyc", tags=["KYC Applications"])


# ── Request schemas ───────────────────────────────────────────────────────────

class CreateApplicationRequest(BaseModel):
    kyc_type: KYCType
    onboarding_channel: OnboardingChannel
    product_type: ProductType
    product_code: str | None = None
    expected_investment: Decimal | None = None


class CustomerProfileRequest(BaseModel):
    # Identity (English - from OCR, agent may correct name spelling only)
    full_name_en: str = Field(..., max_length=255)
    full_name_bn: str | None = None
    fathers_name_en: str | None = None
    fathers_name_bn: str | None = None
    mothers_name_en: str | None = None
    mothers_name_bn: str | None = None
    spouse_name_en: str | None = None
    # NID and DOB are non-editable — captured from biometric verification
    gender: Gender | None = None
    tin_number: str | None = None

    # Financial
    profession: str | None = None
    monthly_income: Decimal | None = None
    source_of_fund: SourceOfFund | None = None
    source_of_fund_detail: str | None = None

    # Contact
    mobile_number: str = Field(..., max_length=15)
    email: str | None = None

    # Address
    present_address: str | None = None
    permanent_address: str | None = None
    nationality: str = "Bangladeshi"
    residency_status: ResidencyStatus = ResidencyStatus.resident_bangladeshi

    # Risk declarations
    is_pep: bool = False
    is_ip: bool = False
    is_nrb: bool = False


class NomineeRequest(BaseModel):
    full_name: str = Field(..., max_length=255)
    date_of_birth: date | None = None
    relation: NomineeRelation
    contact_number: str | None = None
    address: str | None = None
    photo_storage_key: str | None = None
    is_minor: bool = False
    guardian_name: str | None = None
    guardian_nid: str | None = None
    guardian_address: str | None = None


class SignatureRequest(BaseModel):
    signature_type: SignatureType
    storage_key: str | None = Field(
        None, description="Object storage key for wet/electronic signature image"
    )
    pin: str | None = Field(
        None, min_length=4, max_length=6, description="PIN — only for low-risk accounts"
    )


class ApplicationRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    agent_id: uuid.UUID | None
    kyc_type: KYCType
    onboarding_channel: OnboardingChannel
    product_type: ProductType
    status: ApplicationStatus
    application_ref: str | None
    submitted_at: str | None
    created_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_application_or_404(
    db: DBSession, app_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> KYCApplication:
    query = select(KYCApplication).where(KYCApplication.id == app_id)
    if user_id:
        query = query.where(KYCApplication.user_id == user_id)
    result = await db.execute(query)
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


def _app_to_read(app: KYCApplication) -> ApplicationRead:
    return ApplicationRead(
        id=app.id,
        user_id=app.user_id,
        agent_id=app.agent_id,
        kyc_type=app.kyc_type,
        onboarding_channel=app.onboarding_channel,
        product_type=app.product_type,
        status=app.status,
        application_ref=app.application_ref,
        submitted_at=str(app.submitted_at) if app.submitted_at else None,
        created_at=str(app.created_at),
    )


# ── Customer endpoints ────────────────────────────────────────────────────────

@router.post("/applications", response_model=APIResponse[ApplicationRead])
async def create_application(
    body: CreateApplicationRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Phase 3/4 Step 1: Create a new KYC application (draft state).
    Called after pre-check decision is made.
    """
    app = KYCApplication(
        user_id=current_user.id,
        kyc_type=body.kyc_type,
        onboarding_channel=body.onboarding_channel,
        product_type=body.product_type,
        product_code=body.product_code,
        expected_investment=body.expected_investment,
        status=ApplicationStatus.draft,
        application_ref=generate_application_ref(),
    )
    db.add(app)
    await db.flush()

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.create,
        entity_type="kyc_applications",
        entity_id=str(app.id),
        new_value={"kyc_type": body.kyc_type, "product_type": body.product_type},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(message="Application created", data=_app_to_read(app))


@router.get("/applications/{app_id}", response_model=APIResponse[ApplicationRead])
async def get_application(
    app_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    app = await _get_application_or_404(db, app_id, current_user.id)
    return APIResponse(data=_app_to_read(app))


@router.put("/applications/{app_id}/profile", response_model=APIResponse[dict])
async def save_customer_profile(
    app_id: uuid.UUID,
    body: CustomerProfileRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Phase 3 Step 3–4: Save customer personal information.
    NID and DOB are populated from biometric verification — not accepted here.
    """
    app = await _get_application_or_404(db, app_id, current_user.id)

    if app.status not in (ApplicationStatus.draft,):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update profile in status: {app.status}",
        )

    # Check if profile already exists
    existing = await db.execute(
        select(CustomerProfile).where(CustomerProfile.kyc_application_id == app_id)
    )
    profile = existing.scalar_one_or_none()

    if profile:
        for key, val in body.model_dump(exclude_none=True).items():
            setattr(profile, key, val)
    else:
        # Fetch NID and DOB from biometric verification record
        from ...models.onboarding import BiometricVerification
        bio_result = await db.execute(
            select(BiometricVerification).where(
                BiometricVerification.kyc_application_id == app_id,
                BiometricVerification.is_matched == True,
            ).order_by(BiometricVerification.verified_at.desc()).limit(1)
        )
        bio = bio_result.scalar_one_or_none()

        profile = CustomerProfile(
            kyc_application_id=app_id,
            user_id=current_user.id,
            nid_number=bio.nid_number if bio else "PENDING",
            date_of_birth=bio.dob_provided if bio else date.today(),
            **body.model_dump(exclude_none=True),
        )
        db.add(profile)
        await db.flush()

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.update,
        entity_type="customer_profiles",
        entity_id=str(profile.id),
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(message="Profile saved", data={"profile_id": str(profile.id)})


@router.post("/applications/{app_id}/nominees", response_model=APIResponse[dict])
async def add_nominee(
    app_id: uuid.UUID,
    body: NomineeRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Phase 3 Step 4: Add nominee to application."""
    app = await _get_application_or_404(db, app_id, current_user.id)

    if body.is_minor and not body.guardian_name:
        raise HTTPException(
            status_code=422,
            detail="Guardian name is required when nominee is a minor",
        )

    nominee = Nominee(
        kyc_application_id=app_id,
        **body.model_dump(exclude_none=True),
    )
    db.add(nominee)
    await db.flush()

    return APIResponse(message="Nominee added", data={"nominee_id": str(nominee.id)})


@router.post("/applications/{app_id}/signature", response_model=APIResponse[dict])
async def capture_signature(
    app_id: uuid.UUID,
    body: SignatureRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Phase 3 Step 5: Record customer signature or PIN consent.
    PIN only permitted for simplified/low-risk accounts.
    """
    app = await _get_application_or_404(db, app_id, current_user.id)

    if body.signature_type == SignatureType.pin:
        if app.kyc_type != KYCType.simplified:
            raise HTTPException(
                status_code=400,
                detail="PIN signature only permitted for simplified eKYC accounts",
            )
        if not body.pin:
            raise HTTPException(status_code=422, detail="PIN is required for PIN signature type")

    if body.signature_type in (SignatureType.wet, SignatureType.electronic):
        if not body.storage_key:
            raise HTTPException(status_code=422, detail="storage_key required for wet/electronic signature")

    from ...core.security import hash_password
    sig = DigitalSignature(
        kyc_application_id=app_id,
        signature_type=body.signature_type,
        storage_key=body.storage_key,
        pin_hash=hash_password(body.pin) if body.pin else None,
        is_low_risk_pin=body.signature_type == SignatureType.pin,
    )
    db.add(sig)
    await db.flush()

    return APIResponse(message="Signature captured", data={"signature_id": str(sig.id)})


@router.post("/applications/{app_id}/submit", response_model=APIResponse[ApplicationRead])
async def submit_application(
    app_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Phase 3 Step 6: Validate all required fields and submit application.
    Moves status from draft → submitted.
    """
    app = await _get_application_or_404(db, app_id, current_user.id)

    if app.status != ApplicationStatus.draft:
        raise HTTPException(
            status_code=400,
            detail=f"Only draft applications can be submitted. Current status: {app.status}",
        )

    # Validate profile exists
    profile_result = await db.execute(
        select(CustomerProfile).where(CustomerProfile.kyc_application_id == app_id)
    )
    if not profile_result.scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Customer profile not found. Complete profile before submitting.")

    # Validate biometric verification passed
    from ...models.onboarding import BiometricVerification
    bio_result = await db.execute(
        select(BiometricVerification).where(
            BiometricVerification.kyc_application_id == app_id,
            BiometricVerification.is_matched == True,
        )
    )
    if not bio_result.scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Biometric verification required before submission.")

    # Validate signature captured
    sig_result = await db.execute(
        select(DigitalSignature).where(DigitalSignature.kyc_application_id == app_id)
    )
    if not sig_result.scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Signature or consent required before submission.")

    app.status = ApplicationStatus.submitted
    app.submitted_at = utcnow()

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.update,
        entity_type="kyc_applications",
        entity_id=str(app.id),
        new_value={"status": "submitted"},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(message="Application submitted successfully", data=_app_to_read(app))


# ── Agent endpoints ───────────────────────────────────────────────────────────

@router.post("/applications/agent/create", response_model=APIResponse[ApplicationRead])
async def agent_create_application(
    body: CreateApplicationRequest,
    customer_mobile: str,
    request: Request,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """
    Phase 4: Agent initiates a new application on behalf of a customer.
    Customer must already have verified their mobile (OTP).
    """
    user_result = await db.execute(
        select(User).where(User.mobile_number == customer_mobile)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found. Customer must verify mobile first.")

    app = KYCApplication(
        user_id=user.id,
        agent_id=current_agent.id,
        kyc_type=body.kyc_type,
        onboarding_channel=body.onboarding_channel,
        product_type=body.product_type,
        product_code=body.product_code,
        expected_investment=body.expected_investment,
        status=ApplicationStatus.draft,
        application_ref=generate_application_ref(),
    )
    db.add(app)
    await db.flush()

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.create,
        entity_type="kyc_applications",
        entity_id=str(app.id),
        new_value={"agent_id": str(current_agent.id), "customer_id": str(user.id)},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(message="Application created by agent", data=_app_to_read(app))


@router.get("/applications", response_model=PaginatedResponse[ApplicationRead])
async def list_applications_agent(
    current_agent: CurrentAgent,
    db: DBSession,
    status_filter: ApplicationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """Phase 4: Agent dashboard — list applications assigned to this agent."""
    query = select(KYCApplication).where(KYCApplication.agent_id == current_agent.id)
    if status_filter:
        query = query.where(KYCApplication.status == status_filter)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    apps = result.scalars().all()

    return PaginatedResponse(
        total=len(apps),
        page=page,
        page_size=page_size,
        data=[_app_to_read(a) for a in apps],
    )
