"""
Phase 1 — Customer Authentication
POST /auth/customer/send-otp
POST /auth/customer/verify-otp
POST /auth/customer/refresh
POST /auth/customer/logout
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select

from ...core.config import settings
from ...core.deps import CurrentUser, DBSession
from ...core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_otp,
    hash_token,
    verify_otp,
)
from ...models.base import utcnow
from ...models.enums import ActorType, AuditAction, OTPPurpose, UserStatus
from ...models.identity import OTPLog, Session, User
from ...schemas.common import APIResponse, MessageResponse, TokenResponse
from ...services.audit import record_event

router = APIRouter(prefix="/auth/customer", tags=["Customer Auth"])


# ── Request / Response schemas ────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    mobile_number: str = Field(
        ..., min_length=11, max_length=15,
        example="+8801712345678",
        description="BD mobile number in E.164 format",
    )
    email: str | None = Field(None, example="user@example.com")


class VerifyOTPRequest(BaseModel):
    mobile_number: str = Field(..., min_length=11, max_length=15)
    otp: str = Field(..., min_length=6, max_length=6, example="123456")
    device_fingerprint: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_create_user(db: DBSession, mobile: str, email: str | None) -> User:
    result = await db.execute(select(User).where(User.mobile_number == mobile))
    user = result.scalar_one_or_none()
    if not user:
        user = User(mobile_number=mobile, email=email)
        db.add(user)
        await db.flush()
    elif email and not user.email:
        user.email = email
    return user


async def _check_lockout(db: DBSession, user_id: uuid.UUID) -> None:
    """Raise 429 if user has too many recent failed OTP attempts."""
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
            detail=f"Too many failed attempts. Try again after {settings.OTP_LOCKOUT_MINUTES} minutes.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/send-otp", response_model=APIResponse[dict])
async def send_otp(body: SendOTPRequest, request: Request, db: DBSession):
    """
    Generate and send OTP to customer mobile.
    Creates a new user record if first time.
    """
    user = await _get_or_create_user(db, body.mobile_number, body.email)

    if user.status == UserStatus.locked:
        raise HTTPException(status_code=403, detail="Account is locked")

    await _check_lockout(db, user.id)

    otp = generate_otp()
    otp_log = OTPLog(
        user_id=user.id,
        otp_hash=hash_otp(otp),
        purpose=OTPPurpose.customer_login,
        expires_at=utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(otp_log)

    await record_event(
        db,
        actor_id=str(user.id),
        actor_type=ActorType.customer,
        action=AuditAction.otp_sent,
        entity_type="otp_logs",
        entity_id=str(otp_log.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # TODO: Integrate SMS gateway here. In dev, OTP is returned in response.
    return APIResponse(
        message="OTP sent successfully",
        data={
            "otp": otp,  # Remove in production — for dev/testing only
            "expires_in_seconds": settings.OTP_EXPIRE_MINUTES * 60,
            "mobile_number": body.mobile_number,
        },
    )


@router.post("/verify-otp", response_model=APIResponse[TokenResponse])
async def verify_otp_endpoint(body: VerifyOTPRequest, request: Request, db: DBSession):
    """
    Verify OTP and issue JWT access + refresh tokens.
    Creates a session record capturing device and IP.
    """
    result = await db.execute(select(User).where(User.mobile_number == body.mobile_number))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get latest unverified OTP
    otp_result = await db.execute(
        select(OTPLog).where(
            OTPLog.user_id == user.id,
            OTPLog.purpose == OTPPurpose.customer_login,
            OTPLog.is_verified == False,
            OTPLog.expires_at > utcnow(),
        ).order_by(OTPLog.created_at.desc()).limit(1)
    )
    otp_log = otp_result.scalar_one_or_none()

    if not otp_log:
        raise HTTPException(status_code=400, detail="No active OTP found. Please request a new OTP.")

    otp_log.attempt_count += 1

    if otp_log.attempt_count > settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail=f"Maximum OTP attempts reached. Request a new OTP.",
        )

    if not verify_otp(body.otp, otp_log.otp_hash):
        await record_event(
            db,
            actor_id=str(user.id),
            actor_type=ActorType.customer,
            action=AuditAction.login_failed,
            entity_type="otp_logs",
            entity_id=str(otp_log.id),
            ip_address=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=400, detail="Invalid OTP")

    otp_log.is_verified = True

    access_token = create_access_token(str(user.id), "customer")
    refresh_token = create_refresh_token(str(user.id), "customer")

    session = Session(
        user_id=user.id,
        jwt_token_hash=hash_token(access_token),
        ip_address=request.client.host if request.client else "unknown",
        device_fingerprint=body.device_fingerprint,
        user_agent=request.headers.get("user-agent"),
        expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)

    await record_event(
        db,
        actor_id=str(user.id),
        actor_type=ActorType.customer,
        action=AuditAction.login,
        entity_type="sessions",
        entity_id=str(session.id),
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="Authentication successful",
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, current_user: CurrentUser, db: DBSession):
    """Invalidate current session."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "")
    token_hash = hash_token(token)

    result = await db.execute(
        select(Session).where(
            Session.user_id == current_user.id,
            Session.jwt_token_hash == token_hash,
            Session.is_active == True,
        )
    )
    session = result.scalar_one_or_none()
    if session:
        session.is_active = False

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.logout,
        entity_type="sessions",
        ip_address=request.client.host if request.client else None,
    )
    return MessageResponse(message="Logged out successfully")
