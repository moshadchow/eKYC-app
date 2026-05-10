"""
Notification Gateway — SMS and Email dispatch.
Supports mock mode for local development (NOTIFICATION_MOCK=true).
"""
import logging
import uuid
from typing import Optional

import httpx
from aiosmtplib import send
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationGateway:

    def __init__(self):
        self.mock = settings.NOTIFICATION_MOCK

    async def send_sms(self, phone: str, message: str) -> tuple[str, Optional[str]]:
        """Send SMS. Returns (gateway_message_id, error)."""
        if self.mock:
            msg_id = f"mock-{uuid.uuid4().hex[:12]}"
            logger.info(f"[MOCK SMS] to={phone} msg_id={msg_id} body={message[:80]}")
            return msg_id, None

        if not settings.SMS_GATEWAY_URL:
            return "", "SMS_GATEWAY_URL not configured"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    settings.SMS_GATEWAY_URL,
                    headers={
                        "Authorization": f"Bearer {settings.SMS_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={"to": phone, "message": message},
                )
                if response.is_success:
                    data = response.json()
                    msg_id = data.get("message_id", data.get("id", ""))
                    return msg_id, None
                else:
                    return "", f"Gateway error {response.status_code}: {response.text[:200]}"
        except Exception as e:
            return "", str(e)

    async def send_email(
        self, to: str, subject: str, body: str
    ) -> tuple[str, Optional[str]]:
        """Send email. Returns (gateway_message_id, error)."""
        if self.mock:
            msg_id = f"mock-email-{uuid.uuid4().hex[:12]}"
            logger.info(f"[MOCK EMAIL] to={to} msg_id={msg_id} subject={subject}")
            return msg_id, None

        if not settings.SMTP_HOST:
            return "", "SMTP_HOST not configured"

        try:
            msg = EmailMessage()
            msg["From"] = settings.SMTP_USER
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)

            await send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
            )
            return f"email-{uuid.uuid4().hex[:12]}", None
        except Exception as e:
            return "", str(e)


gateway = NotificationGateway()