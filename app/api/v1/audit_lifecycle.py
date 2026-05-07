"""Phase 11 & 12 — Audit Trail & KYC Lifecycle (API layer only)"""
import uuid
from datetime import date
from fastapi import APIRouter, HTTPException, Request
from app.core.deps import CurrentAgent, CurrentUser, DBSession
from app.crud.crud_audit import crud_audit, crud_lifecycle
from app.models.enums import ActorType, AuditAction, RiskClassification
from app.schemas.common import APIResponse, PaginatedResponse
from app.services.audit import record_event

audit_router = APIRouter(prefix="/audit", tags=["Audit Trail"])
lifecycle_router = APIRouter(prefix="/lifecycle", tags=["KYC Lifecycle"])


@audit_router.get("/logs", response_model=PaginatedResponse[dict])
async def list_audit_logs(
    current_agent: CurrentAgent, db: DBSession,
    actor_id: str | None = None, entity_type: str | None = None,
    action: str | None = None, page: int = 1, page_size: int = 50,
):
    """Phase 11: Immutable audit trail. Requires system_admin or system_auditor role."""
    if current_agent.role not in ("system_admin", "system_auditor"):
        raise HTTPException(status_code=403, detail="Requires system_admin or system_auditor role")
    logs = await crud_audit.list_logs(
        db, actor_id, entity_type, action,
        offset=(page - 1) * page_size, limit=page_size,
    )
    return PaginatedResponse(total=len(logs), page=page, page_size=page_size, data=[{
        "id": str(l.id), "actor_id": l.actor_id, "actor_type": l.actor_type,
        "entity_type": l.entity_type, "entity_id": l.entity_id,
        "action": l.action, "ip_address": l.ip_address, "created_at": str(l.created_at),
    } for l in logs])


@audit_router.get("/logs/{entity_type}/{entity_id}", response_model=APIResponse[list])
async def get_entity_audit_trail(
    entity_type: str, entity_id: str, current_agent: CurrentAgent, db: DBSession,
):
    """Full audit trail for a specific entity."""
    logs = await crud_audit.list_by_entity(db, entity_type, entity_id)
    return APIResponse(data=[{
        "id": str(l.id), "actor_id": l.actor_id, "actor_type": l.actor_type,
        "action": l.action, "old_value": l.old_value_json,
        "new_value": l.new_value_json, "ip_address": l.ip_address, "created_at": str(l.created_at),
    } for l in logs])


@lifecycle_router.get("/accounts/{account_id}/refresh-schedule", response_model=APIResponse[dict])
async def get_refresh_schedule(
    account_id: uuid.UUID, current_user: CurrentUser, db: DBSession,
):
    """Phase 12: Get KYC refresh schedule for an account."""
    schedule = await crud_lifecycle.get_schedule(db, account_id, current_user.id)
    days_remaining = (schedule.due_date - date.today()).days
    return APIResponse(data={
        "schedule_id": str(schedule.id), "risk_tier": schedule.risk_tier,
        "due_date": str(schedule.due_date), "status": schedule.status,
        "days_remaining": days_remaining, "is_overdue": days_remaining < 0,
        "reminder_count": schedule.reminder_count,
        "last_reminder_at": str(schedule.last_reminder_at) if schedule.last_reminder_at else None,
    })


@lifecycle_router.post("/accounts/{account_id}/refresh/initiate", response_model=APIResponse[dict])
async def initiate_kyc_refresh(
    account_id: uuid.UUID, request: Request, current_user: CurrentUser, db: DBSession,
):
    """Phase 12: Customer initiates KYC refresh."""
    schedule = await crud_lifecycle.get_schedule(db, account_id, current_user.id)
    schedule = await crud_lifecycle.initiate_refresh(db, schedule)
    await record_event(
        db, actor_id=str(current_user.id), actor_type=ActorType.customer,
        action=AuditAction.kyc_refresh_completed, entity_type="kyc_refresh_schedules",
        entity_id=str(schedule.id), ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="KYC refresh initiated", data={
        "schedule_id": str(schedule.id), "status": schedule.status,
    })


@lifecycle_router.post("/accounts/{account_id}/refresh/complete", response_model=APIResponse[dict])
async def complete_kyc_refresh(
    account_id: uuid.UUID, request: Request, current_agent: CurrentAgent, db: DBSession,
    new_risk_tier: RiskClassification | None = None,
):
    """Phase 12: Mark KYC refresh complete. Recalculates next review date."""
    schedule, account, new_schedule = await crud_lifecycle.complete_refresh(
        db, account_id, new_risk_tier,
    )
    await record_event(
        db, actor_id=str(current_agent.id), actor_type=ActorType.agent,
        action=AuditAction.kyc_refresh_completed, entity_type="accounts", entity_id=str(account_id),
        new_value={"new_risk_tier": account.risk_tier, "next_review_date": str(account.kyc_next_review_date)},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="KYC refresh completed", data={
        "next_review_date": str(account.kyc_next_review_date),
        "risk_tier": account.risk_tier, "new_schedule_id": str(new_schedule.id),
    })


@lifecycle_router.get("/accounts/overdue", response_model=APIResponse[list])
async def get_overdue_refreshes(current_agent: CurrentAgent, db: DBSession):
    """Phase 12: All accounts with overdue KYC refresh — for scheduler."""
    overdue = await crud_lifecycle.list_overdue(db)
    today = date.today()
    return APIResponse(data=[{
        "schedule_id": str(s.id), "account_id": str(s.account_id),
        "user_id": str(s.user_id), "risk_tier": s.risk_tier,
        "due_date": str(s.due_date), "days_overdue": (today - s.due_date).days,
        "reminder_count": s.reminder_count,
    } for s in overdue])
