"""
Phase 1 — Customer Authentication (thin API layer)
All DB operations delegated to crud_auth_customer.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import CurrentUser, DBSession
from app.crud.crud_auth_customer import crud_auth_customer
from app.models.enums import ActorType, AuditAction, OTPPurpose
from app.schemas.common import APIResponse, MessageResponse, TokenResponse
from app.services.audit import record_event

router = APIRouter(prefix="/auth/customer", tags=["Customer Auth"])


class SendOTPRequest(BaseModel):
    mobile_number: str = Field(..., min_length=11, max_length=15, example="+8801712345678")
    email: str | None = Field(None, example="user@example.com")


class VerifyOTPRequest(BaseModel):
    mobile_number: str = Field(..., min_length=11, max_length=15)
    otp: str = Field(..., min_length=6, max_length=6, example="123456")
    device_fingerprint: str | None = None


@router.post("/send-otp", response_model=APIResponse[dict])
async def send_otp(body: SendOTPRequest, request: Request, db: DBSession):
    """Generate OTP and send to customer mobile. Creates user if first time."""
    user = await crud_auth_customer.get_or_create_user(db, body.mobile_number, body.email)
    crud_auth_customer.assert_user_not_locked(user)
    await crud_auth_customer.check_otp_lockout(db, user.id)

    otp_log, otp_plain = await crud_auth_customer.create_otp(
        db, user.id, OTPPurpose.customer_login
    )
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
    return APIResponse(
        message="OTP sent successfully",
        data={
            "otp": otp_plain,          # Remove in production
            "expires_in_seconds": settings.OTP_EXPIRE_MINUTES * 60,
            "mobile_number": body.mobile_number,
        },
    )


@router.post("/verify-otp", response_model=APIResponse[TokenResponse])
async def verify_otp(body: VerifyOTPRequest, request: Request, db: DBSession):
    """Verify OTP and issue JWT access + refresh tokens."""
    user = await crud_auth_customer.get_user_by_mobile(db, body.mobile_number)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp_log = await crud_auth_customer.get_active_otp(
        db, user.id, OTPPurpose.customer_login
    )
    if not otp_log:
        raise HTTPException(
            status_code=400,
            detail="No active OTP found. Please request a new OTP.",
        )

    crud_auth_customer.increment_otp_attempt(otp_log)

    if not crud_auth_customer.verify_otp_value(body.otp, otp_log):
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

    crud_auth_customer.mark_otp_verified(otp_log)

    ip = request.client.host if request.client else "unknown"
    session, access_token, refresh_token = await crud_auth_customer.create_customer_session(
        db, user.id, ip, body.device_fingerprint, request.headers.get("user-agent")
    )
    await record_event(
        db,
        actor_id=str(user.id),
        actor_type=ActorType.customer,
        action=AuditAction.login,
        entity_type="sessions",
        entity_id=str(session.id),
        ip_address=ip,
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
    """Invalidate current session token."""
    token = request.headers.get("authorization", "").replace("Bearer ", "")
    await crud_auth_customer.invalidate_session(db, current_user.id, token)
    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.logout,
        entity_type="sessions",
        ip_address=request.client.host if request.client else None,
    )
    return MessageResponse(message="Logged out successfully")
