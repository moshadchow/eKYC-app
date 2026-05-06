"""
Phase 7 — AML Compliance Screening
Phase 8 — Risk Grading Engine

POST /compliance/{app_id}/screening/run
GET  /compliance/{app_id}/screening/results
POST /compliance/{app_id}/pep-check
POST /compliance/{app_id}/beneficial-owners
GET  /compliance/{app_id}/beneficial-owners
POST /compliance/{app_id}/risk-score
GET  /compliance/{app_id}/risk-score
POST /compliance/{app_id}/edd/request
GET  /compliance/{app_id}/edd/status
POST /compliance/{app_id}/edd/{edd_id}/documents
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import select

from ...core.config import settings
from ...core.deps import CurrentAgent, DBSession, require_roles
from ...models.base import utcnow
from ...models.compliance import (
    BeneficialOwner,
    EDDDocument,
    EDDRequest,
    PEPIPCheck,
    RiskScore,
    ScreeningResult,
)
from ...models.enums import (
    ActorType,
    AgentRole,
    AuditAction,
    CDDStatus,
    EDDStatus,
    EDDTriggerReason,
    RiskClassification,
    ScreenResult,
    ScreenType,
)
from ...models.onboarding import CustomerProfile, KYCApplication
from ...schemas.common import APIResponse
from ...services.audit import record_event

router = APIRouter(prefix="/compliance", tags=["Compliance & Risk"])

ComplianceAgent = Annotated[
    object,
    Depends(
        require_roles(
            AgentRole.maker,
            AgentRole.checker,
            AgentRole.compliance_officer,
            AgentRole.system_admin,
        )
    ),
]


# ── Schemas ───────────────────────────────────────────────────────────────────

class PEPCheckRequest(BaseModel):
    is_pep: bool = False
    is_ip: bool = False
    is_family_of_pep: bool = False
    is_family_of_ip: bool = False
    is_high_official_intl_org: bool = False
    match_detail: str | None = None


class BeneficialOwnerRequest(BaseModel):
    full_name: str = Field(..., max_length=255)
    nid_number: str | None = None
    ownership_percentage: float | None = Field(None, ge=0, le=100)
    is_pep: bool = False
    is_ip: bool = False


class RiskScoreRequest(BaseModel):
    """
    Manual override of auto-calculated scores.
    Normally populated by the system from profile data.
    """
    score_onboarding_channel: int = Field(..., ge=1, le=5)
    score_geography: int = Field(..., ge=1, le=5)
    score_customer_type: int = Field(..., ge=0, le=10)
    score_product: int = Field(..., ge=1, le=5)
    score_business_activity: int = Field(..., ge=1, le=5)
    score_profession: int = Field(..., ge=1, le=5)
    score_transaction_volume: int = Field(..., ge=1, le=5)
    score_transparency: int = Field(..., ge=1, le=5)


class EDDDocumentRequest(BaseModel):
    document_type: str
    storage_key: str
    checksum_sha256: str = Field(..., min_length=64, max_length=64)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_app(db: DBSession, app_id: uuid.UUID) -> KYCApplication:
    result = await db.execute(
        select(KYCApplication).where(KYCApplication.id == app_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


def _calculate_risk_classification(total: int) -> RiskClassification:
    """BFIU section 6.2: Regular < 15, High >= 15."""
    if total >= settings.HIGH_RISK_SCORE_THRESHOLD:
        return RiskClassification.high
    if total >= 8:
        return RiskClassification.medium
    return RiskClassification.low


async def _auto_score_from_profile(
    db: DBSession, app: KYCApplication
) -> dict:
    """
    Auto-calculate risk factor scores from customer profile and application data.
    Based on BFIU risk grading forms (section 6.3.1 and 6.3.2).
    """
    profile_result = await db.execute(
        select(CustomerProfile).where(
            CustomerProfile.kyc_application_id == app.id
        )
    )
    profile = profile_result.scalar_one_or_none()

    # Onboarding channel score
    channel_scores = {
        "self_checkin": 2,
        "internet": 2,
        "assisted": 2,
        "branch": 3,
    }
    score_channel = channel_scores.get(app.onboarding_channel.value, 2)

    # Geography score
    score_geo = 3 if (profile and profile.is_nrb) else 1

    # Customer type score (PEP/IP = 5, else 0–1)
    pep_result = await db.execute(
        select(PEPIPCheck).where(PEPIPCheck.kyc_application_id == app.id)
    )
    pep_check = pep_result.scalar_one_or_none()
    score_customer = 0
    if pep_check:
        if pep_check.is_pep or pep_check.is_ip:
            score_customer = 5
        elif pep_check.is_family_of_pep or pep_check.is_family_of_ip:
            score_customer = 5
        else:
            score_customer = 1

    # Product score
    product_scores = {
        "bo_account": 2,
        "life_insurance": 1,
        "non_life_insurance": 3,
    }
    score_product = product_scores.get(app.product_type.value, 2)

    # Business + profession — default medium if not assessed
    score_business = 3
    score_profession = 3

    # Transaction volume score
    investment = float(app.expected_investment or 0)
    if investment < 1_000_000:
        score_txn = 1
    elif investment < 5_000_000:
        score_txn = 2
    elif investment < 50_000_000:
        score_txn = 3
    else:
        score_txn = 5

    # Transparency (source of fund)
    score_transparency = 1 if (profile and profile.source_of_fund) else 5

    return {
        "score_onboarding_channel": score_channel,
        "score_geography": score_geo,
        "score_customer_type": score_customer,
        "score_product": score_product,
        "score_business_activity": score_business,
        "score_profession": score_profession,
        "score_transaction_volume": score_txn,
        "score_transparency": score_transparency,
    }


# ── Screening endpoints ───────────────────────────────────────────────────────

@router.post("/{app_id}/screening/run", response_model=APIResponse[list])
async def run_screening(
    app_id: uuid.UUID,
    request: Request,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """
    Phase 7: Run all compliance screenings against UN sanctions,
    internal blacklist, and adverse media sources.
    """
    app = await _get_app(db, app_id)

    profile_result = await db.execute(
        select(CustomerProfile).where(CustomerProfile.kyc_application_id == app_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=422, detail="Customer profile required before screening")

    screen_results = []

    # Screen against each source
    screening_sources = [
        (ScreenType.un_sanctions, "UN SCSR", 0.12),
        (ScreenType.internal_blacklist, "BFIU Internal", 0.08),
        (ScreenType.adverse_media, "News API", 0.05),
    ]

    for screen_type, source, hit_probability in screening_sources:
        import random
        # Simulate screening — replace with real API calls
        is_hit = random.random() < hit_probability
        match_score = round(random.uniform(0.7, 0.95), 2) if is_hit else None

        sr = ScreeningResult(
            kyc_application_id=app_id,
            screen_type=screen_type,
            list_source=source,
            matched_name=profile.full_name_en if is_hit else None,
            match_score=match_score,
            result=ScreenResult.potential_match if is_hit else ScreenResult.clear,
            requires_review=is_hit,
        )
        db.add(sr)
        screen_results.append({
            "screen_type": screen_type.value,
            "list_source": source,
            "result": sr.result.value,
            "match_score": match_score,
            "requires_review": is_hit,
        })

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.screening_run,
        entity_type="kyc_applications",
        entity_id=str(app_id),
        new_value={"screens_run": len(screen_results)},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(message="Screening complete", data=screen_results)


@router.get("/{app_id}/screening/results", response_model=APIResponse[list])
async def get_screening_results(
    app_id: uuid.UUID,
    current_agent: CurrentAgent,
    db: DBSession,
):
    result = await db.execute(
        select(ScreeningResult).where(ScreeningResult.kyc_application_id == app_id)
    )
    results = result.scalars().all()
    return APIResponse(
        data=[
            {
                "id": str(r.id),
                "screen_type": r.screen_type.value,
                "list_source": r.list_source,
                "result": r.result.value,
                "match_score": r.match_score,
                "requires_review": r.requires_review,
                "screened_at": str(r.screened_at),
            }
            for r in results
        ]
    )


# ── PEP/IP check ──────────────────────────────────────────────────────────────

@router.post("/{app_id}/pep-check", response_model=APIResponse[dict])
async def run_pep_check(
    app_id: uuid.UUID,
    body: PEPCheckRequest,
    request: Request,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """Phase 7: Record PEP/IP screening results."""
    await _get_app(db, app_id)

    edd_required = any([
        body.is_pep, body.is_ip,
        body.is_family_of_pep, body.is_family_of_ip,
        body.is_high_official_intl_org,
    ])

    check = PEPIPCheck(
        kyc_application_id=app_id,
        is_pep=body.is_pep,
        is_ip=body.is_ip,
        is_family_of_pep=body.is_family_of_pep,
        is_family_of_ip=body.is_family_of_ip,
        is_high_official_intl_org=body.is_high_official_intl_org,
        match_detail=body.match_detail,
        edd_required=edd_required,
    )
    db.add(check)
    await db.flush()

    return APIResponse(
        message="PEP/IP check recorded",
        data={
            "check_id": str(check.id),
            "edd_required": edd_required,
        },
    )


# ── Beneficial owners ─────────────────────────────────────────────────────────

@router.post("/{app_id}/beneficial-owners", response_model=APIResponse[dict])
async def add_beneficial_owner(
    app_id: uuid.UUID,
    body: BeneficialOwnerRequest,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """Phase 7: Add a beneficial owner for the application."""
    await _get_app(db, app_id)

    bo = BeneficialOwner(
        kyc_application_id=app_id,
        full_name=body.full_name,
        nid_number=body.nid_number,
        ownership_percentage=body.ownership_percentage,
        is_pep=body.is_pep,
        is_ip=body.is_ip,
        cdd_status=CDDStatus.pending,
    )
    db.add(bo)
    await db.flush()

    return APIResponse(message="Beneficial owner added", data={"bo_id": str(bo.id)})


@router.get("/{app_id}/beneficial-owners", response_model=APIResponse[list])
async def list_beneficial_owners(
    app_id: uuid.UUID,
    current_agent: CurrentAgent,
    db: DBSession,
):
    result = await db.execute(
        select(BeneficialOwner).where(BeneficialOwner.kyc_application_id == app_id)
    )
    bos = result.scalars().all()
    return APIResponse(
        data=[
            {
                "id": str(bo.id),
                "full_name": bo.full_name,
                "ownership_percentage": bo.ownership_percentage,
                "is_pep": bo.is_pep,
                "is_ip": bo.is_ip,
                "cdd_status": bo.cdd_status.value,
            }
            for bo in bos
        ]
    )


# ── Risk scoring ──────────────────────────────────────────────────────────────

@router.post("/{app_id}/risk-score", response_model=APIResponse[dict])
async def calculate_risk_score(
    app_id: uuid.UUID,
    request: Request,
    current_agent: CurrentAgent,
    db: DBSession,
    manual_scores: RiskScoreRequest | None = None,
):
    """
    Phase 8: Calculate customer risk score.
    Auto-derives scores from profile if manual_scores not provided.
    Score >= 15 = High risk, triggers EDD per BFIU section 6.2.
    """
    app = await _get_app(db, app_id)

    # Get score version
    version_result = await db.execute(
        select(RiskScore).where(
            RiskScore.kyc_application_id == app_id
        ).order_by(RiskScore.version.desc()).limit(1)
    )
    latest = version_result.scalar_one_or_none()
    version = (latest.version + 1) if latest else 1

    if manual_scores:
        scores = manual_scores.model_dump()
    else:
        scores = await _auto_score_from_profile(db, app)

    total = sum(scores.values())
    risk_class = _calculate_risk_classification(total)

    # Check PEP/IP — always high risk
    pep_result = await db.execute(
        select(PEPIPCheck).where(PEPIPCheck.kyc_application_id == app_id)
    )
    pep_check = pep_result.scalar_one_or_none()
    edd_required = (
        risk_class == RiskClassification.high
        or (pep_check and pep_check.edd_required)
    )

    risk_score = RiskScore(
        kyc_application_id=app_id,
        **scores,
        total_score=total,
        risk_classification=risk_class,
        edd_required=edd_required,
        version=version,
    )
    db.add(risk_score)
    await db.flush()

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.risk_scored,
        entity_type="risk_scores",
        entity_id=str(risk_score.id),
        new_value={
            "total_score": total,
            "risk_classification": risk_class.value,
            "edd_required": edd_required,
        },
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message=f"Risk score calculated: {risk_class.value.upper()} (score: {total})",
        data={
            "risk_score_id": str(risk_score.id),
            "total_score": total,
            "risk_classification": risk_class.value,
            "edd_required": edd_required,
            "score_breakdown": scores,
            "threshold": settings.HIGH_RISK_SCORE_THRESHOLD,
            "version": version,
        },
    )


@router.get("/{app_id}/risk-score", response_model=APIResponse[dict])
async def get_risk_score(
    app_id: uuid.UUID,
    current_agent: CurrentAgent,
    db: DBSession,
):
    result = await db.execute(
        select(RiskScore).where(
            RiskScore.kyc_application_id == app_id
        ).order_by(RiskScore.version.desc()).limit(1)
    )
    rs = result.scalar_one_or_none()
    if not rs:
        raise HTTPException(status_code=404, detail="No risk score found for this application")

    return APIResponse(
        data={
            "risk_score_id": str(rs.id),
            "total_score": rs.total_score,
            "risk_classification": rs.risk_classification.value,
            "edd_required": rs.edd_required,
            "version": rs.version,
            "scored_at": str(rs.scored_at),
            "score_breakdown": {
                "onboarding_channel": rs.score_onboarding_channel,
                "geography": rs.score_geography,
                "customer_type": rs.score_customer_type,
                "product": rs.score_product,
                "business_activity": rs.score_business_activity,
                "profession": rs.score_profession,
                "transaction_volume": rs.score_transaction_volume,
                "transparency": rs.score_transparency,
            },
        }
    )


# ── EDD ───────────────────────────────────────────────────────────────────────

@router.post("/{app_id}/edd/request", response_model=APIResponse[dict])
async def create_edd_request(
    app_id: uuid.UUID,
    request: Request,
    current_agent: CurrentAgent,
    db: DBSession,
    trigger_reason: EDDTriggerReason = EDDTriggerReason.high_risk_score,
):
    """Phase 8: Create EDD request for high-risk customers."""
    await _get_app(db, app_id)

    rs_result = await db.execute(
        select(RiskScore).where(
            RiskScore.kyc_application_id == app_id
        ).order_by(RiskScore.version.desc()).limit(1)
    )
    risk_score = rs_result.scalar_one_or_none()
    if not risk_score:
        raise HTTPException(status_code=422, detail="Risk score must be calculated before EDD request")

    deadline = utcnow() + timedelta(days=settings.EDD_DEADLINE_DAYS)
    edd = EDDRequest(
        kyc_application_id=app_id,
        risk_score_id=risk_score.id,
        trigger_reason=trigger_reason,
        required_documents='["bank_statement", "income_proof", "source_of_fund_declaration"]',
        status=EDDStatus.pending,
        deadline_at=deadline,
    )
    db.add(edd)
    await db.flush()

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.edd_triggered,
        entity_type="edd_requests",
        entity_id=str(edd.id),
        new_value={"trigger_reason": trigger_reason.value, "deadline": str(deadline)},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="EDD request created",
        data={
            "edd_id": str(edd.id),
            "trigger_reason": trigger_reason.value,
            "deadline": str(deadline),
            "required_documents": ["bank_statement", "income_proof", "source_of_fund_declaration"],
        },
    )


@router.get("/{app_id}/edd/status", response_model=APIResponse[dict])
async def get_edd_status(
    app_id: uuid.UUID,
    current_agent: CurrentAgent,
    db: DBSession,
):
    result = await db.execute(
        select(EDDRequest).where(
            EDDRequest.kyc_application_id == app_id
        ).order_by(EDDRequest.requested_at.desc()).limit(1)
    )
    edd = result.scalar_one_or_none()
    if not edd:
        raise HTTPException(status_code=404, detail="No EDD request found")

    return APIResponse(
        data={
            "edd_id": str(edd.id),
            "status": edd.status.value,
            "trigger_reason": edd.trigger_reason.value,
            "requested_at": str(edd.requested_at),
            "deadline_at": str(edd.deadline_at),
            "responded_at": str(edd.responded_at) if edd.responded_at else None,
            "days_remaining": max(0, (edd.deadline_at - utcnow()).days),
        }
    )


@router.post("/{app_id}/edd/{edd_id}/documents", response_model=APIResponse[dict])
async def upload_edd_document(
    app_id: uuid.UUID,
    edd_id: uuid.UUID,
    body: EDDDocumentRequest,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """Attach a supporting document to an EDD request."""
    result = await db.execute(
        select(EDDRequest).where(
            EDDRequest.id == edd_id,
            EDDRequest.kyc_application_id == app_id,
        )
    )
    edd = result.scalar_one_or_none()
    if not edd:
        raise HTTPException(status_code=404, detail="EDD request not found")

    doc = EDDDocument(
        edd_request_id=edd_id,
        document_type=body.document_type,
        storage_key=body.storage_key,
        checksum_sha256=body.checksum_sha256,
    )
    db.add(doc)

    if edd.status == EDDStatus.pending:
        edd.status = EDDStatus.documents_received
        edd.responded_at = utcnow()

    return APIResponse(message="EDD document uploaded", data={"doc_id": str(doc.id)})
