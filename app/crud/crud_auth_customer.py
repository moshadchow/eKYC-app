"""
CRUD — Customer Authentication
Handles: user lookup/creation, OTP lifecycle, session management.
"""

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_otp,
    hash_token,
    verify_otp,
)
from app.models.base import utcnow
from app.models.enums import OTPPurpose, UserStatus
from app.models.identity import OTPLog, Session, User


class CRUDAuthCustomer:

    # ── User ──────────────────────────────────────────────────────────────────

    async def get_user_by_mobile(
        self, db: AsyncSession, mobile_number: str
    ) -> Optional[User]:
        result = await db.execute(
            select(User).where(User.mobile_number == mobile_number)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> Optional[User]:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_user(
        self, db: AsyncSession, mobile_number: str, email: Optional[str]
    ) -> User:
        user = await self.get_user_by_mobile(db, mobile_number)
        if not user:
            user = User(mobile_number=mobile_number, email=email)
            db.add(user)
            await db.flush()
        elif email and not user.email:
            user.email = email
        return user

    def assert_user_not_locked(self, user: User) -> None:
        if user.status == UserStatus.locked:
            raise HTTPException(status_code=403, detail="Account is locked")

    # ── OTP ───────────────────────────────────────────────────────────────────

    async def check_otp_lockout(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> None:
        """Raise 429 if customer is within lockout window."""
        window = utcnow() - timedelta(minutes=settings.OTP_LOCKOUT_MINUTES)
        result = await db.execute(
            select(OTPLog).where(
                OTPLog.user_id == user_id,
                OTPLog.purpose == OTPPurpose.customer_login,
                OTPLog.is_verified == False,
                OTPLog.attempt_count >= settings.OTP_MAX_ATTEMPTS,
                OTPLog.created_at >= window,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many failed attempts. "
                    f"Try again after {settings.OTP_LOCKOUT_MINUTES} minutes."
                ),
            )

    async def create_otp(
        self, db: AsyncSession, user_id: uuid.UUID, purpose: OTPPurpose
    ) -> tuple[OTPLog, str]:
        """Create hashed OTP log entry. Returns (OTPLog, plaintext_otp)."""
        otp_plain = generate_otp()
        otp_log = OTPLog(
            user_id=user_id,
            otp_hash=hash_otp(otp_plain),
            purpose=purpose,
            expires_at=utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
        )
        db.add(otp_log)

        # ── DEV ONLY: print OTP to terminal ──────────────────────────────────
        print(f"\n{'='*50}")
        print(f"  📱 CUSTOMER OTP  [{purpose.value}]")
        print(f"  User ID : {user_id}")
        print(f"  OTP Code: \033[1;33m{otp_plain}\033[0m")
        print(f"  Expires : {settings.OTP_EXPIRE_MINUTES} minutes")
        print(f"{'='*50}\n")
        # ─────────────────────────────────────────────────────────────────────

        return otp_log, otp_plain

    async def get_active_otp(
        self, db: AsyncSession, user_id: uuid.UUID, purpose: OTPPurpose
    ) -> Optional[OTPLog]:
        result = await db.execute(
            select(OTPLog)
            .where(
                OTPLog.user_id == user_id,
                OTPLog.purpose == purpose,
                OTPLog.is_verified == False,
                OTPLog.expires_at > utcnow(),
            )
            .order_by(OTPLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def increment_otp_attempt(self, otp_log: OTPLog) -> None:
        otp_log.attempt_count += 1
        if otp_log.attempt_count > settings.OTP_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum OTP attempts reached. Request a new OTP.",
            )

    def verify_otp_value(self, otp_plain: str, otp_log: OTPLog) -> bool:
        return verify_otp(otp_plain, otp_log.otp_hash)

    def mark_otp_verified(self, otp_log: OTPLog) -> None:
        otp_log.is_verified = True

    # ── Session ───────────────────────────────────────────────────────────────

    async def create_customer_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        ip_address: str,
        device_fingerprint: Optional[str],
        user_agent: Optional[str],
    ) -> tuple[Session, str, str]:
        """
        Create session + tokens.
        Returns (session, access_token, refresh_token).
        """
        access_token = create_access_token(str(user_id), "customer")
        refresh_token = create_refresh_token(str(user_id), "customer")

        session = Session(
            user_id=user_id,
            jwt_token_hash=hash_token(access_token),
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            user_agent=user_agent,
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        db.add(session)
        return session, access_token, refresh_token

    async def invalidate_session(
        self, db: AsyncSession, user_id: uuid.UUID, token: str
    ) -> None:
        token_hash = hash_token(token)
        result = await db.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.jwt_token_hash == token_hash,
                Session.is_active == True,
            )
        )
        session = result.scalar_one_or_none()
        if session:
            session.is_active = False


crud_auth_customer = CRUDAuthCustomer()
