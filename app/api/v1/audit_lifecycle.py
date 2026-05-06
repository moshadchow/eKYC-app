"""
Phase 11 — Audit Trail
Phase 12 — KYC Lifecycle Management

GET  /audit/logs
GET  /audit/logs/{entity_type}/{entity_id}
GET  /lifecycle/accounts/{account_id}/refresh-schedule
POST /lifecycle/accounts/{account_id}/refresh/initiate
POST /lifecycle/accounts/{account_id}/refresh/complete
GET  /lifecycle/accounts/overdue
"""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from ...core.config import settings
from ...core.deps import CurrentAgent, CurrentUser, DBSession
from ...models.base import utcnow
from ...models.enums import (
    ActorType,
    AuditAction,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    RefreshEventType,
    RefreshStatus,
    RiskClassification,
)
from ...models.workflow import (
    Account,
    AuditLog,
    KYCRefreshEvent,
    KYCRefreshSchedule,
    Notification,
)
from ...schemas.common import APIResponse, PaginatedResponse
from ...services.audit import record_event

audit_router = APIRouter(prefix="/audit", tags=["Audit Trail"])
lifecycle_router = APIRouter(prefix="/lifecycle", tags=["KYC Lifecycle"])


# ── Audit endpoints ───────────────────────────────────────────────────────────

@audit_router.get("/logs", response_model=PaginatedResponse[dict])
async def list_audit_logs(
    current_agent: CurrentAgent,
    db: DBSession,
    actor_id: str | None = None,
    entity_type: str | None = None,
    action: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    """
    Phase 11: Query immutable audit trail.
    Accessible by system_admin and system_auditor only.
    """
    if current_agent.role not in ("system_admin", "system_auditor"):
        raise HTTPException(status_code=403, detail="Audit log access requires system_admin or system_auditor role")

    query = select(AuditLog)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if action:
        query = query.where(AuditLog.action == action)

    query = query.order_by(AuditLog.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return PaginatedResponse(
        total=len(logs),
        page=page,
        page_size=page_size,
        data=[
            {
                "id": str(l.id),
                "actor_id": l.actor_id,
                "actor_type": l.actor_type.value,
                "entity_type": l.entity_type,
                "entity_id": l.entity_id,
                "action": l.action.value,
                "ip_address": l.ip_address,
                "created_at": str(l.created_at),
            }
            for l in logs
        ],
    )


@audit_router.get("/logs/{entity_type}/{entity_id}", response_model=APIResponse[list])
async def get_entity_audit_trail(
    entity_type: str,
    entity_id: str,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """Get full audit trail for a specific entity (application, account, etc.)."""
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        ).order_by(AuditLog.created_at.asc())
    )
    logs = result.scalars().all()

    return APIResponse(
        data=[
            {
                "id": str(l.id),
                "actor_id": l.actor_id,
                "actor_type": l.actor_type.value,
                "action": l.action.value,
                "old_value": l.old_value_json,
                "new_value": l.new_value_json,
                "ip_address": l.ip_address,
                "created_at": str(l.created_at),
            }
            for l in logs
        ]
    )


# ── Lifecycle endpoints ───────────────────────────────────────────────────────

@lifecycle_router.get("/accounts/{account_id}/refresh-schedule", response_model=APIResponse[dict])
async def get_refresh_schedule(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """Phase 12: Get KYC refresh schedule for an account."""
    result = await db.execute(
        select(KYCRefreshSchedule).where(
            KYCRefreshSchedule.account_id == account_id,
            KYCRefreshSchedule.user_id == current_user.id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="No refresh schedule found")

    today = date.today()
    days_remaining = (schedule.due_date - today).days

    return APIResponse(
        data={
            "schedule_id": str(schedule.id),
            "risk_tier": schedule.risk_tier.value,
            "due_date": str(schedule.due_date),
            "status": schedule.status.value,
            "days_remaining": days_remaining,
            "is_overdue": days_remaining < 0,
            "reminder_count": schedule.reminder_count,
            "last_reminder_at": str(schedule.last_reminder_at) if schedule.last_reminder_at else None,
        }
    )


@lifecycle_router.post("/accounts/{account_id}/refresh/initiate", response_model=APIResponse[dict])
async def initiate_kyc_refresh(
    account_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Phase 12: Customer initiates KYC refresh (self-declaration or full re-kyc).
    Called when due_date is approaching or overdue.
    """
    result = await db.execute(
        select(KYCRefreshSchedule).where(
            KYCRefreshSchedule.account_id == account_id,
            KYCRefreshSchedule.user_id == current_user.id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Refresh schedule not found")

    schedule.status = RefreshStatus.in_progress

    event = KYCRefreshEvent(
        schedule_id=schedule.id,
        event_type=RefreshEventType.customer_response,
        notes="Customer initiated KYC refresh",
    )
    db.add(event)

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.kyc_refresh_completed,
        entity_type="kyc_refresh_schedules",
        entity_id=str(schedule.id),
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="KYC refresh initiated",
        data={"schedule_id": str(schedule.id), "status": schedule.status.value},
    )


@lifecycle_router.post("/accounts/{account_id}/refresh/complete", response_model=APIResponse[dict])
async def complete_kyc_refresh(
    account_id: uuid.UUID,
    request: Request,
    current_agent: CurrentAgent,
    db: DBSession,
    new_risk_tier: RiskClassification | None = None,
):
    """
    Phase 12: Mark KYC refresh as complete. Recalculate next review date.
    If risk tier changed, update account and create new risk score.
    """
    schedule_result = await db.execute(
        select(KYCRefreshSchedule).where(
            KYCRefreshSchedule.account_id == account_id
        )
    )
    schedule = schedule_result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    account_result = await db.execute(
        select(Account).where(Account.id == account_id)
    )
    account = account_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    effective_tier = new_risk_tier or schedule.risk_tier

    # Calculate next review date
    days_map = {
        RiskClassification.high: 365,
        RiskClassification.medium: 730,
        RiskClassification.low: 1825,
    }
    next_due = (utcnow() + timedelta(days=days_map[effective_tier])).date()

    schedule.status = RefreshStatus.completed
    schedule.completed_at = utcnow()
    schedule.risk_tier = effective_tier
    schedule.due_date = next_due

    account.kyc_next_review_date = next_due
    account.risk_tier = effective_tier

    event = KYCRefreshEvent(
        schedule_id=schedule.id,
        event_type=RefreshEventType.completed,
        notes=f"KYC refresh completed. Next due: {next_due}. Risk tier: {effective_tier.value}",
    )
    db.add(event)

    # Create new schedule for next cycle
    new_schedule = KYCRefreshSchedule(
        account_id=account_id,
        user_id=schedule.user_id,
        risk_tier=effective_tier,
        due_date=next_due,
        status=RefreshStatus.scheduled,
    )
    db.add(new_schedule)

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.kyc_refresh_completed,
        entity_type="accounts",
        entity_id=str(account_id),
        new_value={"new_risk_tier": effective_tier.value, "next_review_date": str(next_due)},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="KYC refresh completed",
        data={
            "next_review_date": str(next_due),
            "risk_tier": effective_tier.value,
            "new_schedule_id": str(new_schedule.id),
        },
    )


@lifecycle_router.get("/accounts/overdue", response_model=APIResponse[list])
async def get_overdue_refreshes(
    current_agent: CurrentAgent,
    db: DBSession,
):
    """Phase 12: Get all accounts with overdue KYC refresh — for scheduler/admin."""
    today = date.today()
    result = await db.execute(
        select(KYCRefreshSchedule).where(
            KYCRefreshSchedule.due_date < today,
            KYCRefreshSchedule.status.in_([
                RefreshStatus.scheduled.value,
                RefreshStatus.reminder_sent.value,
            ]),
        )
    )
    overdue = result.scalars().all()

    return APIResponse(
        data=[
            {
                "schedule_id": str(s.id),
                "account_id": str(s.account_id),
                "user_id": str(s.user_id),
                "risk_tier": s.risk_tier.value,
                "due_date": str(s.due_date),
                "days_overdue": (today - s.due_date).days,
                "reminder_count": s.reminder_count,
            }
            for s in overdue
        ]
    )
