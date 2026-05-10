"""
CRUD — Notification Management
Handles all DB operations for the notifications table.
"""
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.base import utcnow
from app.models.enums import NotificationStatus
from app.models.workflow import Notification


class CRUDNotification:

    async def create(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        kyc_application_id: Optional[uuid.UUID],
        channel: str,
        notification_type: str,
        recipient_address: str,
        message_body: str,
    ) -> Notification:
        notif = Notification(
            user_id=user_id,
            kyc_application_id=kyc_application_id,
            channel=channel,
            notification_type=notification_type,
            recipient_address=recipient_address,
            message_body=message_body,
            status=NotificationStatus.pending.value,
        )
        db.add(notif)
        await db.flush()
        return notif

    async def mark_sent(
        self, db: AsyncSession, notif_id: uuid.UUID, gateway_message_id: str
    ) -> Notification:
        result = await db.execute(select(Notification).where(Notification.id == notif_id))
        notif = result.scalar_one_or_none()
        if not notif:
            raise ValueError(f"Notification {notif_id} not found")
        notif.status = NotificationStatus.sent.value
        notif.gateway_message_id = gateway_message_id
        notif.sent_at = utcnow()
        return notif

    async def mark_delivered(self, db: AsyncSession, notif_id: uuid.UUID) -> Notification:
        result = await db.execute(select(Notification).where(Notification.id == notif_id))
        notif = result.scalar_one_or_none()
        if not notif:
            raise ValueError(f"Notification {notif_id} not found")
        notif.status = NotificationStatus.delivered.value
        notif.delivered_at = utcnow()
        return notif

    async def mark_failed(
        self,
        db: AsyncSession,
        notif_id: uuid.UUID,
        error_message: str,
        gateway_response: Optional[str] = None,
    ) -> Notification:
        result = await db.execute(select(Notification).where(Notification.id == notif_id))
        notif = result.scalar_one_or_none()
        if not notif:
            raise ValueError(f"Notification {notif_id} not found")
        notif.status = NotificationStatus.failed.value
        notif.retry_count += 1
        notif.error_message = error_message
        if gateway_response is not None:
            notif.gateway_response = gateway_response
        return notif

    async def get_pending_batch(
        self, db: AsyncSession, limit: int = 50
    ) -> list[Notification]:
        result = await db.execute(
            select(Notification)
            .where(Notification.status == NotificationStatus.pending.value)
            .order_by(Notification.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Notification], int]:
        query = select(Notification).where(Notification.user_id == user_id)
        count_query = select(Notification).where(Notification.user_id == user_id)
        if status:
            query = query.where(Notification.status == status)
            count_query = count_query.where(Notification.status == status)
        query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        total_result = await db.execute(count_query)
        return list(result.scalars().all()), total_result.scalar_one() or 0

    async def list_all(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        notification_type: Optional[str] = None,
        channel: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Notification], int]:
        query = select(Notification)
        count_query = select(Notification)
        if status:
            query = query.where(Notification.status == status)
            count_query = count_query.where(Notification.status == status)
        if notification_type:
            query = query.where(Notification.notification_type == notification_type)
            count_query = count_query.where(Notification.notification_type == notification_type)
        if channel:
            query = query.where(Notification.channel == channel)
            count_query = count_query.where(Notification.channel == channel)
        if user_id:
            query = query.where(Notification.user_id == user_id)
            count_query = count_query.where(Notification.user_id == user_id)
        query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        total_result = await db.execute(count_query)
        return list(result.scalars().all()), total_result.scalar_one() or 0

    async def get_by_id(self, db: AsyncSession, notif_id: uuid.UUID) -> Optional[Notification]:
        result = await db.execute(select(Notification).where(Notification.id == notif_id))
        return result.scalar_one_or_none()

    async def retry(self, db: AsyncSession, notif_id: uuid.UUID) -> Notification:
        result = await db.execute(select(Notification).where(Notification.id == notif_id))
        notif = result.scalar_one_or_none()
        if not notif:
            raise ValueError(f"Notification {notif_id} not found")
        if notif.status != NotificationStatus.failed.value:
            raise ValueError("Only failed notifications can be retried")
        # Reset to pending for dispatcher to pick up
        notif.status = NotificationStatus.pending.value
        return notif


crud_notification = CRUDNotification()