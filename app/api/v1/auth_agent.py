"""
Phase 1 — Agent Authentication
POST /auth/agent/login
POST /auth/agent/verify-2fa
POST /auth/agent/logout
GET  /auth/agent/me
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select

from ...core.config import settings
from ...core.deps import CurrentAgent, DBSession
from ...core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_otp,
    hash_token,
    verify_otp,
    verify_password,
)
from ...models.base import utcnow
from ...models.enums import ActorType, AuditAction, OTPPurpose
from ...models.identity import Agent, AgentDevice, AgentSession, OTPLog, User
from ...schemas.common import APIResponse, MessageResponse, TokenResponse
from ...services.audit import record_event

router = APIRouter(prefix="/auth/agent", tags=["Agent Auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AgentLoginRequest(BaseModel):
    employee_id: str
    password: str
    device_fingerprint: str = Field(..., description="Hashed device identifier")


class Verify2FARequest(BaseModel):
    employee_id: str
    otp: str = Field(..., min_length=6, max_length=6)
    device_fingerprint: str


class AgentReadPublic(BaseModel):
    id: uuid.UUID
    employee_id: str
    full_name: str
    role: str
    branch_code: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=APIResponse[dict])
async def agent_login(body: AgentLoginRequest, request: Request, db: DBSession):
    """
    Step 1: Validate agent credentials and trigger 2FA OTP.
    Device must be pre-authorized by admin.
    """
    result = await db.execute(select(Agent).where(Agent.employee_id == body.employee_id))
    agent = result.scalar_one_or_none()

    if not agent or not agent.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(body.password, agent.password_hash):
        await record_event(
            db,
            actor_id=str(agent.id),
            actor_type=ActorType.agent,
            action=AuditAction.login_failed,
            entity_type="agents",
            entity_id=str(agent.id),
            ip_address=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Device authorization check
    dev_result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.agent_id == agent.id,
            AgentDevice.device_fingerprint == body.device_fingerprint,
            AgentDevice.is_authorized == True,
        )
    )
    if not dev_result.scalar_one_or_none():
        raise HTTPException(
            status_code=403,
            detail="Device not authorized. Contact your system administrator.",
        )

    # Issue 2FA OTP
    otp = generate_otp()
    otp_log = OTPLog(
        user_id=agent.id,  # Reuse user_id field for agent ID
        otp_hash=hash_otp(otp),
        purpose=OTPPurpose.agent_2fa,
        expires_at=utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(otp_log)

    await record_event(
        db,
        actor_id=str(agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.otp_sent,
        entity_type="otp_logs",
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="Credentials verified. OTP sent for 2FA.",
        data={
            "otp": otp,  # Remove in production
            "employee_id": agent.employee_id,
            "expires_in_seconds": settings.OTP_EXPIRE_MINUTES * 60,
        },
    )


@router.post("/verify-2fa", response_model=APIResponse[TokenResponse])
async def verify_2fa(body: Verify2FARequest, request: Request, db: DBSession):
    """
    Step 2: Verify 2FA OTP and issue agent JWT tokens.
    """
    result = await db.execute(select(Agent).where(Agent.employee_id == body.employee_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    otp_result = await db.execute(
        select(OTPLog).where(
            OTPLog.user_id == agent.id,
            OTPLog.purpose == OTPPurpose.agent_2fa,
            OTPLog.is_verified == False,
            OTPLog.expires_at > utcnow(),
        ).order_by(OTPLog.created_at.desc()).limit(1)
    )
    otp_log = otp_result.scalar_one_or_none()

    if not otp_log or not verify_otp(body.otp, otp_log.otp_hash):
        raise HTTPException(status_code=400, detail="Invalid or expired 2FA OTP")

    otp_log.is_verified = True

    access_token = create_access_token(
        str(agent.id), "agent", extra={"role": agent.role, "branch": agent.branch_code}
    )
    refresh_token = create_refresh_token(str(agent.id), "agent")

    session = AgentSession(
        agent_id=agent.id,
        jwt_token_hash=hash_token(access_token),
        ip_address=request.client.host if request.client else "unknown",
        device_fingerprint=body.device_fingerprint,
        twofa_verified=True,
        expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)

    await record_event(
        db,
        actor_id=str(agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.login,
        entity_type="agent_sessions",
        entity_id=str(session.id),
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="Agent authentication successful",
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


@router.get("/me", response_model=APIResponse[AgentReadPublic])
async def get_me(current_agent: CurrentAgent):
    return APIResponse(
        data=AgentReadPublic(
            id=current_agent.id,
            employee_id=current_agent.employee_id,
            full_name=current_agent.full_name,
            role=current_agent.role,
            branch_code=current_agent.branch_code,
        )
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, current_agent: CurrentAgent, db: DBSession):
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "")
    token_hash = hash_token(token)

    result = await db.execute(
        select(AgentSession).where(
            AgentSession.agent_id == current_agent.id,
            AgentSession.jwt_token_hash == token_hash,
            AgentSession.is_active == True,
        )
    )
    session = result.scalar_one_or_none()
    if session:
        session.is_active = False

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.logout,
        entity_type="agent_sessions",
        ip_address=request.client.host if request.client else None,
    )
    return MessageResponse(message="Logged out successfully")
