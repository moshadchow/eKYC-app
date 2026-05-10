"""
Notification Dispatcher — background worker that dispatches pending notifications.
Runs on a 30-second interval during app lifespan.
"""
import asyncio
import logging
from typing import Optional

from app.core.config import settings
from app.crud.crud_notification import crud_notification
from app.services.notification_gateway import gateway

logger = logging.getLogger(__name__)

_loop: Optional[asyncio.Task] = None
_shutdown = False


async def _dispatch_tick():
    """One dispatch cycle — fetch pending, send, update status."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        pending = await crud_notification.get_pending_batch(db, limit=50)
        for notif in pending:
            if notif.channel == "sms":
                msg_id, err = await gateway.send_sms(notif.recipient_address, notif.message_body)
            elif notif.channel == "email":
                msg_id, err = await gateway.send_email(
                    notif.recipient_address, "[eKYC] Notification", notif.message_body
                )
            else:
                msg_id, err = "", f"Unknown channel: {notif.channel}"

            if err:
                await crud_notification.mark_failed(db, notif.id, err)
                logger.warning(f"Notification {notif.id} failed: {err}")
            else:
                await crud_notification.mark_sent(db, notif.id, msg_id)
                logger.info(f"Notification {notif.id} sent, gateway_id={msg_id}")


async def _dispatcher_loop():
    """Background loop: dispatch every 30 seconds."""
    logger.info("Notification dispatcher started (mock=%s)", settings.NOTIFICATION_MOCK)
    while not _shutdown:
        try:
            await _dispatch_tick()
        except Exception as e:
            logger.error("Dispatcher tick error: %s", e)
        await asyncio.sleep(30)
    logger.info("Notification dispatcher stopped")


def start_dispatcher():
    global _loop, _shutdown
    _shutdown = False
    _loop = asyncio.create_task(_dispatcher_loop())


def stop_dispatcher():
    global _loop, _shutdown
    _shutdown = True
    if _loop:
        _loop.cancel()