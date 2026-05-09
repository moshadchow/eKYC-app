"""Phase 3 & 4 — KYC Applications (API layer only)"""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.deps import CurrentAgent, CurrentUser, DBSession
from app.crud.crud_application import crud_application
from app.models.enums import (
    ActorType, ApplicationStatus, AuditAction, Gender, KYCType,
    NomineeRelation, OnboardingChannel, ProductType, ResidencyStatus,
    SignatureType, SourceOfFund,
)
from app.schemas.common import APIResponse, PaginatedResponse
from app.services.audit import record_event

router = APIRouter(prefix="/kyc", tags=["KYC Applications"])


# ── Request schemas ───────────────────────────────────────────────────────────

class CreateApplicationRequest(BaseModel):
    kyc_type: KYCType
    onboarding_channel: OnboardingChannel
    product_type: ProductType
    product_code: str | None = None
    expected_investment: Decimal | None = None


class CustomerProfileRequest(BaseModel):
    full_name_en: str = Field(..., max_length=255)
    full_name_bn: str | None = None
    fathers_name_en: str | None = None
    fathers_name_bn: str | None = None
    mothers_name_en: str | None = None
    mothers_name_bn: str | None = None
    spouse_name_en: str | None = None
    gender: Gender | None = None
    tin_number: str | None = None
    profession: str | None = None
    business_activity: str | None = None
    monthly_income: Decimal | None = None
    source_of_fund: SourceOfFund | None = None
    source_of_fund_detail: str | None = None
    mobile_number: str = Field(..., max_length=15)
    email: str | None = None
    present_address: str | None = None
    permanent_address: str | None = None
    nationality: str = "Bangladeshi"
    residency_status: ResidencyStatus = ResidencyStatus.resident_bangladeshi
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
    storage_key: str | None = Field(None, description="For wet/electronic signatures")
    pin: str | None = Field(None, min_length=4, max_length=6, description="Simplified eKYC only")


class ApplicationRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    agent_id: uuid.UUID | None
    kyc_type: str
    onboarding_channel: str
    product_type: str
    status: str
    application_ref: str | None
    submitted_at: str | None
    created_at: str


def _to_read(app) -> ApplicationRead:
    return ApplicationRead(
        id=app.id, user_id=app.user_id, agent_id=app.agent_id,
        kyc_type=app.kyc_type, onboarding_channel=app.onboarding_channel,
        product_type=app.product_type, status=app.status,
        application_ref=app.application_ref,
        submitted_at=str(app.submitted_at) if app.submitted_at else None,
        created_at=str(app.created_at),
    )


# ── Customer endpoints ────────────────────────────────────────────────────────

@router.post("/applications", response_model=APIResponse[ApplicationRead])
async def create_application(
    body: CreateApplicationRequest, request: Request,
    current_user: CurrentUser, db: DBSession,
):
    """Phase 3 Step 1: Create draft KYC application after pre-check."""
    app = await crud_application.create(
        db, current_user.id, body.kyc_type, body.onboarding_channel,
        body.product_type, body.product_code, body.expected_investment,
    )
    await record_event(
        db, actor_id=str(current_user.id), actor_type=ActorType.customer,
        action=AuditAction.create, entity_type="kyc_applications", entity_id=str(app.id),
        new_value={"kyc_type": body.kyc_type.value, "product_type": body.product_type.value},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="Application created", data=_to_read(app))


@router.get("/applications/{app_id}", response_model=APIResponse[ApplicationRead])
async def get_application(
    app_id: uuid.UUID, current_user: CurrentUser, db: DBSession,
):
    app = await crud_application.get_by_id(db, app_id, current_user.id)
    return APIResponse(data=_to_read(app))


@router.put("/applications/{app_id}/profile", response_model=APIResponse[dict])
async def save_customer_profile(
    app_id: uuid.UUID, body: CustomerProfileRequest, request: Request,
    current_user: CurrentUser, db: DBSession,
):
    """Phase 3 Step 3–4: Save customer personal information."""
    app = await crud_application.get_by_id(db, app_id, current_user.id)
    profile = await crud_application.upsert_profile(
        db, app_id, current_user.id, app.status,
        body.model_dump(exclude_none=True),
    )
    await record_event(
        db, actor_id=str(current_user.id), actor_type=ActorType.customer,
        action=AuditAction.update, entity_type="customer_profiles", entity_id=str(profile.id),
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="Profile saved", data={"profile_id": str(profile.id)})


@router.post("/applications/{app_id}/nominees", response_model=APIResponse[dict])
async def add_nominee(
    app_id: uuid.UUID, body: NomineeRequest, request: Request,
    current_user: CurrentUser, db: DBSession,
):
    """Phase 3 Step 4: Add nominee to application."""
    await crud_application.get_by_id(db, app_id, current_user.id)
    nominee = await crud_application.add_nominee(
        db, app_id, body.full_name, body.relation, body.date_of_birth,
        body.contact_number, body.address, body.photo_storage_key,
        body.is_minor, body.guardian_name, body.guardian_nid, body.guardian_address,
    )
    return APIResponse(message="Nominee added", data={"nominee_id": str(nominee.id)})


@router.post("/applications/{app_id}/signature", response_model=APIResponse[dict])
async def capture_signature(
    app_id: uuid.UUID, body: SignatureRequest, request: Request,
    current_user: CurrentUser, db: DBSession,
):
    """Phase 3 Step 5: Capture signature or PIN consent."""
    app = await crud_application.get_by_id(db, app_id, current_user.id)
    sig = await crud_application.capture_signature(
        db, app, body.signature_type, body.storage_key, body.pin,
    )
    return APIResponse(message="Signature captured", data={"signature_id": str(sig.id)})


@router.post("/applications/{app_id}/submit", response_model=APIResponse[ApplicationRead])
async def submit_application(
    app_id: uuid.UUID, request: Request, current_user: CurrentUser, db: DBSession,
):
    """Phase 3 Step 6: Validate and submit — moves draft → submitted."""
    app = await crud_application.get_by_id(db, app_id, current_user.id)
    app = await crud_application.submit(db, app)
    await record_event(
        db, actor_id=str(current_user.id), actor_type=ActorType.customer,
        action=AuditAction.update, entity_type="kyc_applications", entity_id=str(app.id),
        new_value={"status": "submitted"},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="Application submitted successfully", data=_to_read(app))


# ── Agent endpoints ───────────────────────────────────────────────────────────

@router.post("/applications/agent/create", response_model=APIResponse[ApplicationRead])
async def agent_create_application(
    body: CreateApplicationRequest, customer_mobile: str, request: Request,
    current_agent: CurrentAgent, db: DBSession,
):
    """Phase 4: Agent initiates application on behalf of a customer."""
    user = await crud_application.get_customer_by_mobile(db, customer_mobile)
    app = await crud_application.create(
        db, user.id, body.kyc_type, body.onboarding_channel,
        body.product_type, body.product_code, body.expected_investment,
        agent_id=current_agent.id,
    )
    await record_event(
        db, actor_id=str(current_agent.id), actor_type=ActorType.agent,
        action=AuditAction.create, entity_type="kyc_applications", entity_id=str(app.id),
        new_value={"agent_id": str(current_agent.id), "customer_id": str(user.id)},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="Application created by agent", data=_to_read(app))


@router.get("/applications", response_model=PaginatedResponse[ApplicationRead])
async def list_applications_agent(
    current_agent: CurrentAgent, db: DBSession,
    status_filter: ApplicationStatus | None = None,
    page: int = 1, page_size: int = 20,
):
    """Phase 4: Agent dashboard — list applications assigned to this agent."""
    apps = await crud_application.list_by_agent(
        db, current_agent.id, status_filter,
        offset=(page - 1) * page_size, limit=page_size,
    )
    return PaginatedResponse(
        total=len(apps), page=page, page_size=page_size,
        data=[_to_read(a) for a in apps],
    )
