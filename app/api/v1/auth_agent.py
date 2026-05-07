"""
Phase 1 — Agent Authentication (thin API layer)
All DB operations delegated to crud_auth_agent.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import CurrentAgent, DBSession
from app.crud.crud_auth_agent import crud_auth_agent
from app.models.enums import ActorType, AuditAction
from app.schemas.common import APIResponse, MessageResponse, TokenResponse
from app.services.audit import record_event

router = APIRouter(prefix="/auth/agent", tags=["Agent Auth"])


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


@router.post("/login", response_model=APIResponse[dict])
async def agent_login(body: AgentLoginRequest, request: Request, db: DBSession):
    """Validate agent credentials + device, then send 2FA OTP."""
    agent = await crud_auth_agent.get_agent_by_employee_id(db, body.employee_id)
    crud_auth_agent.assert_agent_active(agent)
    crud_auth_agent.assert_password_valid(body.password, agent)
    await crud_auth_agent.assert_device_authorized(db, agent.id, body.device_fingerprint)

    otp_log, otp_plain = await crud_auth_agent.create_agent_2fa_otp(db, agent.id)
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
            "otp": otp_plain,          # Remove in production
            "employee_id": agent.employee_id,
            "expires_in_seconds": settings.OTP_EXPIRE_MINUTES * 60,
        },
    )


@router.post("/verify-2fa", response_model=APIResponse[TokenResponse])
async def verify_2fa(body: Verify2FARequest, request: Request, db: DBSession):
    """Verify 2FA OTP and issue agent JWT tokens."""
    agent = await crud_auth_agent.get_agent_by_employee_id(db, body.employee_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    otp_log = await crud_auth_agent.get_active_agent_otp(db, agent.id)
    crud_auth_agent.verify_agent_otp(body.otp, otp_log)

    ip = request.client.host if request.client else "unknown"
    session, access_token, refresh_token = await crud_auth_agent.create_agent_session(
        db, agent, ip, body.device_fingerprint
    )
    await record_event(
        db,
        actor_id=str(agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.login,
        entity_type="agent_sessions",
        entity_id=str(session.id),
        ip_address=ip,
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
    token = request.headers.get("authorization", "").replace("Bearer ", "")
    await crud_auth_agent.invalidate_agent_session(db, current_agent.id, token)
    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.logout,
        entity_type="agent_sessions",
        ip_address=request.client.host if request.client else None,
    )
    return MessageResponse(message="Logged out successfully")
