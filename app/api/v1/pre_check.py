"""Phase 2 — Pre-Onboarding Assessment (API layer only)"""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DBSession
from app.crud.crud_pre_check import crud_pre_check
from app.models.enums import (
    ActorType, AuditAction, KYCType, PreCheckDecision, ProductType, ResidencyStatus,
)
from app.schemas.common import APIResponse
from app.services.audit import record_event

router = APIRouter(prefix="/onboarding", tags=["Pre-check & Decision"])


class PreCheckRequest(BaseModel):
    product_type: ProductType
    expected_investment: Decimal | None = Field(None, example=1000000)
    annual_premium: Decimal | None = None
    is_pep: bool = False
    is_ip: bool = False
    residency: ResidencyStatus = ResidencyStatus.resident_bangladeshi


class PreCheckResult(BaseModel):
    decision: PreCheckDecision
    kyc_type: KYCType
    decision_reason: str
    pre_check_log_id: uuid.UUID
    thresholds_applied: dict


@router.post("/pre-check", response_model=APIResponse[PreCheckResult])
async def run_pre_check(
    body: PreCheckRequest, request: Request, current_user: CurrentUser, db: DBSession
):
    """Run BFIU decision engine to determine simplified vs regular eKYC."""
    decision, reason, thresholds = crud_pre_check.run_decision_engine(
        body.product_type, body.expected_investment,
        body.annual_premium, body.is_pep, body.is_ip,
    )
    log = await crud_pre_check.create_pre_check_log(
        db, current_user.id, body.product_type, body.expected_investment,
        body.is_pep, body.is_ip, body.residency, decision, reason,
        request.client.host if request.client else None,
    )
    await record_event(
        db, actor_id=str(current_user.id), actor_type=ActorType.customer,
        action=AuditAction.create, entity_type="pre_check_logs", entity_id=str(log.id),
        new_value={"decision": decision.value, "product_type": body.product_type.value},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(
        message=f"Pre-check complete: {decision.value} eKYC",
        data=PreCheckResult(
            decision=decision,
            kyc_type=crud_pre_check.decision_to_kyc_type(decision),
            decision_reason=reason,
            pre_check_log_id=log.id,
            thresholds_applied=thresholds,
        ),
    )


@router.get("/pre-check/{log_id}", response_model=APIResponse[PreCheckResult])
async def get_pre_check(
    log_id: uuid.UUID, current_user: CurrentUser, db: DBSession
):
    """Retrieve a previous pre-check decision by log ID."""
    log = await crud_pre_check.get_pre_check_log(db, log_id, current_user.id)
    decision = PreCheckDecision(log.decision)
    return APIResponse(
        data=PreCheckResult(
            decision=decision,
            kyc_type=crud_pre_check.decision_to_kyc_type(decision),
            decision_reason=log.decision_reason or "",
            pre_check_log_id=log.id,
            thresholds_applied={},
        )
    )
