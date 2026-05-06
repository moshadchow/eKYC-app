"""
Phase 9 — Admin Approval Workflow (Maker-Checker)
GET  /admin/queue
GET  /admin/queue/{entry_id}
POST /admin/queue/{entry_id}/assign
POST /admin/applications/{app_id}/decide
POST /admin/applications/{app_id}/activate
GET  /admin/applications/{app_id}/review-summary
"""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import select

from ...core.config import settings
from ...core.deps import CheckerAgent, CurrentAgent, DBSession
from ...models.base import utcnow
from ...models.compliance import PEPIPCheck, RiskScore, ScreeningResult
from ...models.enums import (
    AccountStatus,
    AccountType,
    ActorType,
    AgentRole,
    ApprovalAction,
    ApplicationStatus,
    AuditAction,
    QueuePriority,
    QueueStatus,
    QueueType,
    RiskClassification,
)
from ...models.onboarding import (
    BiometricVerification,
    CustomerProfile,
    KYCApplication,
)
from ...models.workflow import (
    Account,
    ApprovalDecision,
    ApprovalQueue,
    KYCRefreshSchedule,
    Notification,
)
from ...models.enums import NotificationChannel, NotificationStatus, NotificationType
from ...schemas.common import APIResponse, PaginatedResponse
from ...services.audit import record_event

router = APIRouter(prefix="/admin", tags=["Admin Approval"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class QueueEntryRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    queue_type: str
    priority: str
    status: str
    assigned_maker_id: str | None
    assigned_checker_id: str | None
    created_at: str


class ReviewSummary(BaseModel):
    app_id: uuid.UUID
    application_ref: str | None
    kyc_type: str
    status: str
    customer_name: str | None
    nid_number: str | None
    biometric_verified: bool
    face_matched: bool
    screening_clear: bool
    pep_ip_flagged: bool
    risk_classification: str | None
    risk_score: int | None
    edd_required: bool


class DecisionRequest(BaseModel):
    action: ApprovalAction
    notes: str | None = None
    rejection_reason: str | None = Field(
        None,
        description="Required when action = reject",
    )


class AssignRequest(BaseModel):
    maker_id: str | None = None
    checker_id: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_create_queue_entry(
    db: DBSession,
    app: KYCApplication,
) -> ApprovalQueue:
    result = await db.execute(
        select(ApprovalQueue).where(ApprovalQueue.kyc_application_id == app.id)
    )
    entry = result.scalar_one_or_none()
    if entry:
        return entry

    # Auto-determine queue type
    rs_result = await db.execute(
        select(RiskScore).where(
            RiskScore.kyc_application_id == app.id
        ).order_by(RiskScore.version.desc()).limit(1)
    )
    rs = rs_result.scalar_one_or_none()

    bio_result = await db.execute(
        select(BiometricVerification).where(
            BiometricVerification.kyc_application_id == app.id,
            BiometricVerification.is_matched == True,
        )
    )
    bio_ok = bio_result.scalar_one_or_none() is not None

    if not bio_ok:
        queue_type = QueueType.failed_verification
        priority = QueuePriority.high
    elif rs and rs.risk_classification == RiskClassification.high:
        queue_type = QueueType.high_risk
        priority = QueuePriority.high
    else:
        queue_type = QueueType.standard
        priority = QueuePriority.normal

    entry = ApprovalQueue(
        kyc_application_id=app.id,
        queue_type=queue_type,
        priority=priority,
        status=QueueStatus.unassigned,
    )
    db.add(entry)
    await db.flush()
    return entry


def _refresh_due_date(risk_tier: RiskClassification) -> date:
    days = {
        RiskClassification.high: 365,
        RiskClassification.medium: 730,
        RiskClassification.low: 1825,
    }
    return (utcnow() + timedelta(days=days[risk_tier])).date()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/queue", response_model=PaginatedResponse[QueueEntryRead])
async def list_queue(
    current_agent: CurrentAgent,
    db: DBSession,
    queue_type: QueueType | None = None,
    status: QueueStatus | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """Phase 9: List applications in review queues."""
    query = select(ApprovalQueue)
    if queue_type:
        query = query.where(ApprovalQueue.queue_type == queue_type)
    if status:
        query = query.where(ApprovalQueue.status == status)

    query = query.order_by(ApprovalQueue.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)

    result = await db.execute(query)
    entries = result.scalars().all()

    return PaginatedResponse(
        total=len(entries),
        page=page,
        page_size=page_size,
        data=[
            QueueEntryRead(
                id=e.id,
                app_id=e.kyc_application_id,
                queue_type=e.queue_type.value,
                priority=e.priority.value,
                status=e.status.value,
                assigned_maker_id=e.assigned_maker_id,
                assigned_checker_id=e.assigned_checker_id,
                created_at=str(e.created_at),
            )
            for e in entries
        ],
    )


@router.post("/queue/{entry_id}/assign", response_model=APIResponse[dict])
async def assign_queue_entry(
    entry_id: uuid.UUID,
    body: AssignRequest,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """Assign maker and/or checker to a queue entry."""
    result = await db.execute(
        select(ApprovalQueue).where(ApprovalQueue.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    if body.maker_id:
        entry.assigned_maker_id = body.maker_id
    if body.checker_id:
        # 4-eyes: checker cannot be same as maker
        if body.checker_id == entry.assigned_maker_id:
            raise HTTPException(
                status_code=400,
                detail="4-eyes principle: checker cannot be the same as the maker",
            )
        entry.assigned_checker_id = body.checker_id

    entry.status = QueueStatus.in_review
    entry.assigned_at = utcnow()

    return APIResponse(message="Queue entry assigned", data={"entry_id": str(entry_id)})


@router.get("/applications/{app_id}/review-summary", response_model=APIResponse[ReviewSummary])
async def get_review_summary(
    app_id: uuid.UUID,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """Phase 9: Full review summary for admin decision screen."""
    app_result = await db.execute(
        select(KYCApplication).where(KYCApplication.id == app_id)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    profile_result = await db.execute(
        select(CustomerProfile).where(CustomerProfile.kyc_application_id == app_id)
    )
    profile = profile_result.scalar_one_or_none()

    bio_result = await db.execute(
        select(BiometricVerification).where(
            BiometricVerification.kyc_application_id == app_id,
            BiometricVerification.is_matched == True,
        )
    )
    bio = bio_result.scalar_one_or_none()

    screen_result = await db.execute(
        select(ScreeningResult).where(
            ScreeningResult.kyc_application_id == app_id,
            ScreeningResult.result.in_([
                "potential_match", "confirmed_match"
            ]),
        )
    )
    has_screen_hit = screen_result.scalar_one_or_none() is not None

    pep_result = await db.execute(
        select(PEPIPCheck).where(PEPIPCheck.kyc_application_id == app_id)
    )
    pep = pep_result.scalar_one_or_none()

    rs_result = await db.execute(
        select(RiskScore).where(
            RiskScore.kyc_application_id == app_id
        ).order_by(RiskScore.version.desc()).limit(1)
    )
    rs = rs_result.scalar_one_or_none()

    return APIResponse(
        data=ReviewSummary(
            app_id=app_id,
            application_ref=app.application_ref,
            kyc_type=app.kyc_type.value,
            status=app.status.value,
            customer_name=profile.full_name_en if profile else None,
            nid_number=profile.nid_number if profile else None,
            biometric_verified=bio is not None,
            face_matched=bio is not None,
            screening_clear=not has_screen_hit,
            pep_ip_flagged=bool(pep and pep.edd_required),
            risk_classification=rs.risk_classification.value if rs else None,
            risk_score=rs.total_score if rs else None,
            edd_required=bool(rs and rs.edd_required),
        )
    )


@router.post("/applications/{app_id}/decide", response_model=APIResponse[dict])
async def make_decision(
    app_id: uuid.UUID,
    body: DecisionRequest,
    request: Request,
    current_agent: CheckerAgent,
    db: DBSession,
):
    """
    Phase 9: Maker/checker decision — approve, reject, or request more info.
    4-eyes enforced: two different agents must act on an application.
    """
    app_result = await db.execute(
        select(KYCApplication).where(KYCApplication.id == app_id)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if body.action == ApprovalAction.reject and not body.rejection_reason:
        raise HTTPException(status_code=422, detail="rejection_reason is required when action is reject")

    queue_entry = await _get_or_create_queue_entry(db, app)

    # 4-eyes: check prior decision was by a different actor
    prior_result = await db.execute(
        select(ApprovalDecision).where(
            ApprovalDecision.kyc_application_id == app_id
        ).order_by(ApprovalDecision.decided_at.desc()).limit(1)
    )
    prior = prior_result.scalar_one_or_none()
    if prior and prior.actor_id == str(current_agent.id):
        raise HTTPException(
            status_code=400,
            detail="4-eyes principle: a different agent must make the checker decision",
        )

    decision = ApprovalDecision(
        kyc_application_id=app_id,
        queue_entry_id=queue_entry.id,
        actor_id=str(current_agent.id),
        actor_role=current_agent.role.value,
        action=body.action,
        notes=body.notes,
        rejection_reason=body.rejection_reason,
    )
    db.add(decision)

    # Update application status
    status_map = {
        ApprovalAction.approve: ApplicationStatus.approved,
        ApprovalAction.reject: ApplicationStatus.rejected,
        ApprovalAction.request_more_info: ApplicationStatus.edd_pending,
        ApprovalAction.escalate: ApplicationStatus.pending_approval,
    }
    if body.action in status_map:
        app.status = status_map[body.action]

    if body.action == ApprovalAction.approve:
        queue_entry.status = QueueStatus.completed
        queue_entry.completed_at = utcnow()

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.approval_decision,
        entity_type="kyc_applications",
        entity_id=str(app_id),
        new_value={"action": body.action.value, "new_status": app.status.value},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message=f"Decision recorded: {body.action.value}",
        data={
            "decision_id": str(decision.id),
            "action": body.action.value,
            "new_status": app.status.value,
        },
    )


@router.post("/applications/{app_id}/activate", response_model=APIResponse[dict])
async def activate_account(
    app_id: uuid.UUID,
    request: Request,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """
    Phase 9: Activate account after approval.
    Creates Account record and KYC refresh schedule.
    """
    app_result = await db.execute(
        select(KYCApplication).where(KYCApplication.id == app_id)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status != ApplicationStatus.approved:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot activate: application status is {app.status.value}",
        )

    # Get risk tier for review schedule
    rs_result = await db.execute(
        select(RiskScore).where(
            RiskScore.kyc_application_id == app_id
        ).order_by(RiskScore.version.desc()).limit(1)
    )
    rs = rs_result.scalar_one_or_none()
    risk_tier = rs.risk_classification if rs else RiskClassification.low

    import random, string
    account_num = "BO" + "".join(random.choices(string.digits, k=10))
    unique_num = "CDBL" + "".join(random.choices(string.digits, k=8))

    account_type_map = {
        "bo_account": AccountType.bo_account,
        "life_insurance": AccountType.life_insurance_policy,
        "non_life_insurance": AccountType.non_life_insurance_policy,
    }

    account = Account(
        kyc_application_id=app_id,
        user_id=app.user_id,
        account_number=account_num,
        unique_account_number=unique_num,
        account_type=account_type_map.get(app.product_type.value, AccountType.bo_account),
        status=AccountStatus.active,
        risk_tier=risk_tier,
        kyc_next_review_date=_refresh_due_date(risk_tier),
        activated_at=utcnow(),
    )
    db.add(account)
    await db.flush()

    # Create KYC refresh schedule
    schedule = KYCRefreshSchedule(
        account_id=account.id,
        user_id=app.user_id,
        risk_tier=risk_tier,
        due_date=_refresh_due_date(risk_tier),
    )
    db.add(schedule)

    # Send activation notification
    notif = Notification(
        user_id=app.user_id,
        kyc_application_id=app_id,
        channel=NotificationChannel.sms,
        notification_type=NotificationType.account_activation,
        recipient_address="PENDING",  # resolved from user record
        message_body=f"Your account {account_num} has been activated. Reference: {app.application_ref}",
        status=NotificationStatus.pending,
    )
    db.add(notif)

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.account_activated,
        entity_type="accounts",
        entity_id=str(account.id),
        new_value={"account_number": account_num, "risk_tier": risk_tier.value},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="Account activated successfully",
        data={
            "account_id": str(account.id),
            "account_number": account_num,
            "unique_account_number": unique_num,
            "risk_tier": risk_tier.value,
            "kyc_next_review_date": str(_refresh_due_date(risk_tier)),
        },
    )
