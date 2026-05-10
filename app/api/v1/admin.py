"""Phase 9 — Admin Approval Workflow (API layer only)"""
import uuid
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from app.core.deps import CheckerAgent, CurrentAgent, DBSession
from app.crud.crud_admin import crud_admin
from app.models.enums import ActorType, ApprovalAction, AuditAction, QueueStatus, QueueType
from app.schemas.common import APIResponse, PaginatedResponse
from app.services.audit import record_event

router = APIRouter(prefix="/admin", tags=["Admin Approval"])


class DecisionRequest(BaseModel):
    action: ApprovalAction
    notes: str | None = None
    rejection_reason: str | None = Field(None, description="Required when action = reject")


class AssignRequest(BaseModel):
    maker_id: str | None = None
    checker_id: str | None = None


@router.get("/queue", response_model=PaginatedResponse[dict])
async def list_queue(
    current_agent: CurrentAgent, db: DBSession,
    queue_type: QueueType | None = None,
    status: QueueStatus | None = None,
    page: int = 1, page_size: int = 20,
):
    """Phase 9: List applications in review queues."""
    entries = await crud_admin.list_queue(
        db, queue_type, status,
        offset=(page - 1) * page_size, limit=page_size,
    )
    return PaginatedResponse(total=len(entries), page=page, page_size=page_size, data=[{
        "id": str(e.id), "app_id": str(e.kyc_application_id),
        "queue_type": e.queue_type, "priority": e.priority, "status": e.status,
        "assigned_maker_id": e.assigned_maker_id, "assigned_checker_id": e.assigned_checker_id,
        "created_at": str(e.created_at),
    } for e in entries])


@router.post("/queue/{entry_id}/assign", response_model=APIResponse[dict])
async def assign_queue_entry(
    entry_id: uuid.UUID, body: AssignRequest, current_agent: CurrentAgent, db: DBSession,
):
    """Assign maker and/or checker to a queue entry (4-eyes enforced)."""
    entry = await crud_admin.assign_queue_entry(db, entry_id, body.maker_id, body.checker_id)
    return APIResponse(message="Queue entry assigned", data={"entry_id": str(entry.id)})


@router.get("/applications/{app_id}/review-summary", response_model=APIResponse[dict])
async def get_review_summary(
    app_id: uuid.UUID, current_agent: CurrentAgent, db: DBSession,
):
    """Phase 9: Full review checklist for admin decision screen."""
    summary = await crud_admin.build_review_summary(db, app_id)
    return APIResponse(data=summary)


@router.get("/applications/{app_id}/documents", response_model=APIResponse[list[dict]])
async def get_application_documents(
    app_id: uuid.UUID, current_agent: CurrentAgent, db: DBSession,
):
    """Get all documents for a KYC application."""
    await crud_admin.get_application(db, app_id)  # Validate app exists
    docs = await crud_admin.get_documents(db, app_id)
    return APIResponse(data=[
        {
            "id": str(d.id),
            "document_type": d.document_type,
            "storage_key": d.storage_key,
            "original_filename": d.original_filename,
            "mime_type": d.mime_type,
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in docs
    ])


@router.post("/applications/{app_id}/decide", response_model=APIResponse[dict])
async def make_decision(
    app_id: uuid.UUID, body: DecisionRequest, request: Request,
    current_agent: CheckerAgent, db: DBSession,
):
    """Phase 9: Maker/checker decision. 4-eyes: checker must differ from maker."""
    app = await crud_admin.get_application(db, app_id)
    queue_entry = await crud_admin.get_or_create_queue_entry(db, app)
    decision = await crud_admin.create_decision(
        db, app, queue_entry, str(current_agent.id), current_agent.role,
        body.action, body.notes, body.rejection_reason,
    )
    await record_event(
        db, actor_id=str(current_agent.id), actor_type=ActorType.agent,
        action=AuditAction.approval_decision, entity_type="kyc_applications", entity_id=str(app_id),
        new_value={"action": body.action.value, "new_status": app.status},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message=f"Decision: {body.action.value}", data={
        "decision_id": str(decision.id), "action": body.action.value, "new_status": app.status,
    })


@router.post("/applications/{app_id}/activate", response_model=APIResponse[dict])
async def activate_account(
    app_id: uuid.UUID, request: Request, current_agent: CurrentAgent, db: DBSession,
):
    """Phase 9: Activate account post-approval. Creates account + refresh schedule."""
    app = await crud_admin.get_application(db, app_id)
    account = await crud_admin.activate_account(db, app)
    await record_event(
        db, actor_id=str(current_agent.id), actor_type=ActorType.agent,
        action=AuditAction.account_activated, entity_type="accounts", entity_id=str(account.id),
        new_value={"account_number": account.account_number, "risk_tier": account.risk_tier},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="Account activated successfully", data={
        "account_id": str(account.id), "account_number": account.account_number,
        "unique_account_number": account.unique_account_number,
        "risk_tier": account.risk_tier,
        "kyc_next_review_date": str(account.kyc_next_review_date),
    })
