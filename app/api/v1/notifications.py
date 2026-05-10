"""Step 11 — Notification Delivery (API layer)"""
import uuid

from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentAgent, CurrentUser, DBSession
from app.crud.crud_notification import crud_notification
from app.models.enums import ActorType, AuditAction
from app.models.enums import NotificationStatus
from app.models.workflow import NotificationRead
from app.schemas.common import APIResponse, PaginatedResponse
from app.services.audit import record_event

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _to_read(n) -> NotificationRead:
    return NotificationRead(
        id=n.id,
        user_id=n.user_id,
        kyc_application_id=n.kyc_application_id,
        channel=n.channel,
        notification_type=n.notification_type,
        recipient_address=n.recipient_address,
        message_body=n.message_body,
        status=n.status,
        retry_count=n.retry_count,
        gateway_message_id=n.gateway_message_id,
        sent_at=n.sent_at,
        delivered_at=n.delivered_at,
        error_message=getattr(n, 'error_message', None),
        gateway_response=getattr(n, 'gateway_response', None),
        created_at=n.created_at,
    )


@router.get("/me", response_model=PaginatedResponse[NotificationRead])
async def list_my_notifications(
    current_user: CurrentUser,
    db: DBSession,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """List notifications for the current customer."""
    notifications, total = await crud_notification.list_by_user(
        db, current_user.id, status,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        data=[_to_read(n) for n in notifications],
    )


@router.get("", response_model=PaginatedResponse[NotificationRead])
async def list_all_notifications(
    current_agent: CurrentAgent,
    db: DBSession,
    status: str | None = None,
    notification_type: str | None = None,
    channel: str | None = None,
    user_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    """Admin: list all notifications with filters. Requires system_admin or system_auditor."""
    if current_agent.role not in ("system_admin", "system_auditor"):
        raise HTTPException(status_code=403, detail="Requires system_admin or system_auditor role")

    user_uuid = uuid.UUID(user_id) if user_id else None
    notifications, total = await crud_notification.list_all(
        db, status, notification_type, channel, user_uuid,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        data=[_to_read(n) for n in notifications],
    )


@router.post("/{notif_id}/retry", response_model=APIResponse[NotificationRead])
async def retry_notification(
    notif_id: uuid.UUID,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """Retry a failed notification. Requires system_admin or compliance_officer."""
    if current_agent.role not in ("system_admin", "compliance_officer"):
        raise HTTPException(status_code=403, detail="Requires system_admin or compliance_officer role")

    try:
        notif = await crud_notification.retry(db, notif_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.update,
        entity_type="notifications",
        entity_id=str(notif.id),
        new_value={"status": "pending", "action": "retry_by_agent"},
    )
    return APIResponse(message="Notification requeued for dispatch", data=_to_read(notif))