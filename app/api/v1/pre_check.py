"""
Phase 2 — Pre-Onboarding Assessment & KYC Type Decision
POST /onboarding/pre-check
GET  /onboarding/pre-check/{log_id}
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlmodel import select

from ...core.config import settings
from ...core.deps import CurrentUser, DBSession
from ...models.base import utcnow
from ...models.enums import (
    ActorType,
    AuditAction,
    KYCType,
    PreCheckDecision,
    ProductType,
    ResidencyStatus,
)
from ...models.workflow import PreCheckLog
from ...schemas.common import APIResponse
from ...services.audit import record_event

router = APIRouter(prefix="/onboarding", tags=["Pre-check & Decision"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PreCheckRequest(BaseModel):
    product_type: ProductType
    expected_investment: Decimal | None = Field(
        None,
        description="Expected investment or sum assured in BDT",
        example=1000000,
    )
    annual_premium: Decimal | None = Field(
        None,
        description="Annual premium in BDT (for insurance products)",
    )
    is_pep: bool = Field(False, description="Self-declaration: Politically Exposed Person")
    is_ip: bool = Field(False, description="Self-declaration: Influential Person")
    residency: ResidencyStatus = Field(ResidencyStatus.resident_bangladeshi)


class PreCheckResult(BaseModel):
    decision: PreCheckDecision
    kyc_type: KYCType
    decision_reason: str
    pre_check_log_id: uuid.UUID
    thresholds_applied: dict


# ── Decision engine ───────────────────────────────────────────────────────────

def _run_decision_engine(body: PreCheckRequest) -> tuple[PreCheckDecision, str, dict]:
    """
    BFIU eKYC Guidelines Section 2.3 decision logic.
    Returns (decision, reason, thresholds_used).
    """
    thresholds = {}
    reasons = []

    # Hard reject: PEP/IP always routes to Regular
    if body.is_pep or body.is_ip:
        reasons.append("PEP/IP declared — Enhanced Due Diligence required")

    investment = body.expected_investment or Decimal("0")
    premium = body.annual_premium or Decimal("0")

    if body.product_type == ProductType.bo_account:
        limit = Decimal(str(settings.SIMPLIFIED_BO_THRESHOLD_BDT))
        thresholds["bo_simplified_limit_bdt"] = float(limit)
        if investment > limit:
            reasons.append(
                f"Investment BDT {investment:,.0f} exceeds simplified BO threshold BDT {limit:,.0f}"
            )

    elif body.product_type == ProductType.life_insurance:
        sum_limit = Decimal(str(settings.SIMPLIFIED_LIFE_SUM_ASSURED_BDT))
        prem_limit = Decimal(str(settings.SIMPLIFIED_LIFE_PREMIUM_BDT))
        thresholds["simplified_sum_assured_bdt"] = float(sum_limit)
        thresholds["simplified_annual_premium_bdt"] = float(prem_limit)
        if investment > sum_limit:
            reasons.append(
                f"Sum assured BDT {investment:,.0f} exceeds simplified limit BDT {sum_limit:,.0f}"
            )
        if premium > prem_limit:
            reasons.append(
                f"Annual premium BDT {premium:,.0f} exceeds simplified limit BDT {prem_limit:,.0f}"
            )

    elif body.product_type == ProductType.non_life_insurance:
        prem_limit = Decimal(str(settings.SIMPLIFIED_NON_LIFE_PREMIUM_BDT))
        thresholds["simplified_premium_bdt"] = float(prem_limit)
        if premium > prem_limit:
            reasons.append(
                f"Premium BDT {premium:,.0f} exceeds simplified non-life limit BDT {prem_limit:,.0f}"
            )

    if reasons:
        return (
            PreCheckDecision.regular,
            "; ".join(reasons),
            thresholds,
        )

    return (
        PreCheckDecision.simplified,
        "All thresholds within simplified eKYC limits and no high-risk flags",
        thresholds,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/pre-check", response_model=APIResponse[PreCheckResult])
async def run_pre_check(
    body: PreCheckRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Run the BFIU decision engine to determine simplified vs regular eKYC.
    Must be called before creating a KYC application.
    """
    decision, reason, thresholds = _run_decision_engine(body)

    log = PreCheckLog(
        user_id=current_user.id,
        product_type=body.product_type.value,
        investment_amount=body.expected_investment,
        pep_declared=body.is_pep,
        ip_declared=body.is_ip,
        residency=body.residency.value,
        decision=decision,
        decision_reason=reason,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    await db.flush()

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.create,
        entity_type="pre_check_logs",
        entity_id=str(log.id),
        new_value={"decision": decision, "product_type": body.product_type},
        ip_address=request.client.host if request.client else None,
    )

    kyc_type = (
        KYCType.simplified if decision == PreCheckDecision.simplified else KYCType.regular
    )

    return APIResponse(
        message=f"Pre-check complete: {decision.value} eKYC",
        data=PreCheckResult(
            decision=decision,
            kyc_type=kyc_type,
            decision_reason=reason,
            pre_check_log_id=log.id,
            thresholds_applied=thresholds,
        ),
    )


@router.get("/pre-check/{log_id}", response_model=APIResponse[PreCheckResult])
async def get_pre_check(log_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    result = await db.execute(
        select(PreCheckLog).where(
            PreCheckLog.id == log_id,
            PreCheckLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Pre-check log not found")

    from fastapi import HTTPException
    kyc_type = (
        KYCType.simplified if log.decision == PreCheckDecision.simplified else KYCType.regular
    )
    return APIResponse(
        data=PreCheckResult(
            decision=log.decision,
            kyc_type=kyc_type,
            decision_reason=log.decision_reason or "",
            pre_check_log_id=log.id,
            thresholds_applied={},
        )
    )
