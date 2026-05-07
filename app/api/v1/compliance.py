"""Phase 7 & 8 — Compliance & Risk (API layer only)"""
import uuid
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from app.core.deps import CurrentAgent, DBSession
from app.crud.crud_compliance import crud_compliance
from app.models.enums import ActorType, AuditAction, EDDTriggerReason, RiskClassification
from app.schemas.common import APIResponse
from app.services.audit import record_event

router = APIRouter(prefix="/compliance", tags=["Compliance & Risk"])


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
    """Manual override of auto-calculated scores."""
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


@router.post("/{app_id}/screening/run", response_model=APIResponse[list])
async def run_screening(
    app_id: uuid.UUID, request: Request, current_agent: CurrentAgent, db: DBSession,
):
    """Phase 7: Run UN sanctions, internal blacklist, and adverse media screening."""
    profile = await crud_compliance.get_customer_profile(db, app_id)
    results = await crud_compliance.run_all_screenings(db, app_id, profile.full_name_en)
    await record_event(
        db, actor_id=str(current_agent.id), actor_type=ActorType.agent,
        action=AuditAction.screening_run, entity_type="kyc_applications", entity_id=str(app_id),
        new_value={"screens_run": len(results)},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="Screening complete", data=[{
        "screen_type": r.screen_type, "list_source": r.list_source,
        "result": r.result, "match_score": r.match_score, "requires_review": r.requires_review,
    } for r in results])


@router.get("/{app_id}/screening/results", response_model=APIResponse[list])
async def get_screening_results(
    app_id: uuid.UUID, current_agent: CurrentAgent, db: DBSession,
):
    results = await crud_compliance.list_screening_results(db, app_id)
    return APIResponse(data=[{
        "id": str(r.id), "screen_type": r.screen_type, "list_source": r.list_source,
        "result": r.result, "match_score": r.match_score,
        "requires_review": r.requires_review, "screened_at": str(r.screened_at),
    } for r in results])


@router.post("/{app_id}/pep-check", response_model=APIResponse[dict])
async def run_pep_check(
    app_id: uuid.UUID, body: PEPCheckRequest, current_agent: CurrentAgent, db: DBSession,
):
    """Phase 7: Record PEP/IP screening result."""
    check = await crud_compliance.create_pep_ip_check(
        db, app_id, body.is_pep, body.is_ip, body.is_family_of_pep,
        body.is_family_of_ip, body.is_high_official_intl_org, body.match_detail,
    )
    return APIResponse(message="PEP/IP check recorded", data={
        "check_id": str(check.id), "edd_required": check.edd_required,
    })


@router.post("/{app_id}/beneficial-owners", response_model=APIResponse[dict])
async def add_beneficial_owner(
    app_id: uuid.UUID, body: BeneficialOwnerRequest, current_agent: CurrentAgent, db: DBSession,
):
    """Phase 7: Add a beneficial owner."""
    await crud_compliance.get_application(db, app_id)
    bo = await crud_compliance.add_beneficial_owner(
        db, app_id, body.full_name, body.nid_number,
        body.ownership_percentage, body.is_pep, body.is_ip,
    )
    return APIResponse(message="Beneficial owner added", data={"bo_id": str(bo.id)})


@router.get("/{app_id}/beneficial-owners", response_model=APIResponse[list])
async def list_beneficial_owners(
    app_id: uuid.UUID, current_agent: CurrentAgent, db: DBSession,
):
    bos = await crud_compliance.list_beneficial_owners(db, app_id)
    return APIResponse(data=[{
        "id": str(b.id), "full_name": b.full_name,
        "ownership_percentage": b.ownership_percentage,
        "is_pep": b.is_pep, "is_ip": b.is_ip, "cdd_status": b.cdd_status,
    } for b in bos])


@router.post("/{app_id}/risk-score", response_model=APIResponse[dict])
async def calculate_risk_score(
    app_id: uuid.UUID, request: Request, current_agent: CurrentAgent, db: DBSession,
    manual_scores: RiskScoreRequest | None = None,
):
    """Phase 8: Calculate customer risk score. Score >= 15 = high risk (BFIU section 6.2)."""
    app = await crud_compliance.get_application(db, app_id)
    scores = manual_scores.model_dump() if manual_scores else await crud_compliance.auto_calculate_scores(db, app)
    pep_check = await crud_compliance.get_pep_ip_check(db, app_id)
    rs = await crud_compliance.create_risk_score(db, app_id, scores, pep_check)
    await record_event(
        db, actor_id=str(current_agent.id), actor_type=ActorType.agent,
        action=AuditAction.risk_scored, entity_type="risk_scores", entity_id=str(rs.id),
        new_value={"total": rs.total_score, "classification": rs.risk_classification},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(
        message=f"Risk score: {str(rs.risk_classification).upper()} (score: {rs.total_score})",
        data={
            "risk_score_id": str(rs.id), "total_score": rs.total_score,
            "risk_classification": rs.risk_classification, "edd_required": rs.edd_required,
            "score_breakdown": scores, "version": rs.version,
        },
    )


@router.get("/{app_id}/risk-score", response_model=APIResponse[dict])
async def get_risk_score(
    app_id: uuid.UUID, current_agent: CurrentAgent, db: DBSession,
):
    from fastapi import HTTPException
    rs = await crud_compliance.get_latest_risk_score(db, app_id)
    if not rs:
        raise HTTPException(status_code=404, detail="No risk score found for this application")
    return APIResponse(data={
        "risk_score_id": str(rs.id), "total_score": rs.total_score,
        "risk_classification": rs.risk_classification, "edd_required": rs.edd_required,
        "version": rs.version, "scored_at": str(rs.scored_at),
        "score_breakdown": {
            "onboarding_channel": rs.score_onboarding_channel,
            "geography": rs.score_geography, "customer_type": rs.score_customer_type,
            "product": rs.score_product, "business_activity": rs.score_business_activity,
            "profession": rs.score_profession, "transaction_volume": rs.score_transaction_volume,
            "transparency": rs.score_transparency,
        },
    })


@router.post("/{app_id}/edd/request", response_model=APIResponse[dict])
async def create_edd_request(
    app_id: uuid.UUID, request: Request, current_agent: CurrentAgent, db: DBSession,
    trigger_reason: EDDTriggerReason = EDDTriggerReason.high_risk_score,
):
    """Phase 8: Create EDD request for high-risk customers."""
    edd = await crud_compliance.create_edd_request(db, app_id, trigger_reason)
    await record_event(
        db, actor_id=str(current_agent.id), actor_type=ActorType.agent,
        action=AuditAction.edd_triggered, entity_type="edd_requests", entity_id=str(edd.id),
        new_value={"trigger_reason": trigger_reason.value, "deadline": str(edd.deadline_at)},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="EDD request created", data={
        "edd_id": str(edd.id), "trigger_reason": trigger_reason.value,
        "deadline": str(edd.deadline_at),
        "required_documents": ["bank_statement", "income_proof", "source_of_fund_declaration"],
    })


@router.get("/{app_id}/edd/status", response_model=APIResponse[dict])
async def get_edd_status(
    app_id: uuid.UUID, current_agent: CurrentAgent, db: DBSession,
):
    from app.models.base import utcnow
    edd = await crud_compliance.get_latest_edd_request(db, app_id)
    return APIResponse(data={
        "edd_id": str(edd.id), "status": edd.status,
        "trigger_reason": edd.trigger_reason,
        "deadline_at": str(edd.deadline_at),
        "days_remaining": max(0, (edd.deadline_at - utcnow()).days),
        "responded_at": str(edd.responded_at) if edd.responded_at else None,
    })


@router.post("/{app_id}/edd/{edd_id}/documents", response_model=APIResponse[dict])
async def upload_edd_document(
    app_id: uuid.UUID, edd_id: uuid.UUID, body: EDDDocumentRequest,
    current_agent: CurrentAgent, db: DBSession,
):
    """Attach a supporting document to an EDD request."""
    doc = await crud_compliance.attach_edd_document(
        db, edd_id, app_id, body.document_type, body.storage_key, body.checksum_sha256,
    )
    return APIResponse(message="EDD document uploaded", data={"doc_id": str(doc.id)})
