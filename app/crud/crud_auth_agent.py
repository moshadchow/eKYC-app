"""
CRUD — Agent Authentication
Handles: agent lookup, device authorization, 2FA OTP, agent session management.
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
    verify_password,
)
from app.models.base import utcnow
from app.models.enums import OTPPurpose
from app.models.identity import Agent, AgentDevice, AgentSession, OTPLog


class CRUDAuthAgent:

    # ── Agent lookup ──────────────────────────────────────────────────────────

    async def get_agent_by_employee_id(
        self, db: AsyncSession, employee_id: str
    ) -> Optional[Agent]:
        result = await db.execute(
            select(Agent).where(Agent.employee_id == employee_id)
        )
        return result.scalar_one_or_none()

    async def get_agent_by_id(
        self, db: AsyncSession, agent_id: uuid.UUID
    ) -> Optional[Agent]:
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    def assert_agent_active(self, agent: Optional[Agent]) -> None:
        if not agent or not agent.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

    def assert_password_valid(self, plain: str, agent: Agent) -> None:
        if not verify_password(plain, agent.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

    # ── Device authorization ──────────────────────────────────────────────────

    async def assert_device_authorized(
        self, db: AsyncSession, agent_id: uuid.UUID, device_fingerprint: str
    ) -> None:
        result = await db.execute(
            select(AgentDevice).where(
                AgentDevice.agent_id == agent_id,
                AgentDevice.device_fingerprint == device_fingerprint,
                AgentDevice.is_authorized == True,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device not authorized. Contact your system administrator.",
            )

    async def register_device(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        device_fingerprint: str,
        device_name: Optional[str] = None,
    ) -> AgentDevice:
        device = AgentDevice(
            agent_id=agent_id,
            device_fingerprint=device_fingerprint,
            device_name=device_name,
            is_authorized=False,
        )
        db.add(device)
        await db.flush()
        return device

    async def authorize_device(
        self, db: AsyncSession, agent_id: uuid.UUID, device_fingerprint: str
    ) -> Optional[AgentDevice]:
        result = await db.execute(
            select(AgentDevice).where(
                AgentDevice.agent_id == agent_id,
                AgentDevice.device_fingerprint == device_fingerprint,
            )
        )
        device = result.scalar_one_or_none()
        if device:
            device.is_authorized = True
            device.authorized_at = utcnow()
        return device

    # ── 2FA OTP ───────────────────────────────────────────────────────────────

    async def create_agent_2fa_otp(
        self, db: AsyncSession, agent_id: uuid.UUID
    ) -> tuple[OTPLog, str]:
        otp_plain = generate_otp()
        otp_log = OTPLog(
            user_id=agent_id,  # reuses user_id FK for agent ID
            otp_hash=hash_otp(otp_plain),
            purpose=OTPPurpose.agent_2fa,
            expires_at=utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
        )
        db.add(otp_log)

        # DEV ONLY: print OTP to terminal
        print(f"\n{'='*50}")
        print(f"  🔐 AGENT 2FA OTP")
        print(f"  Agent ID: {agent_id}")
        print(f"  OTP Code: \033[1;33m{otp_plain}\033[0m")
        print(f"  Expires : {settings.OTP_EXPIRE_MINUTES} minutes")
        print(f"{'='*50}\n")

        return otp_log, otp_plain

    async def get_active_agent_otp(
        self, db: AsyncSession, agent_id: uuid.UUID
    ) -> Optional[OTPLog]:
        result = await db.execute(
            select(OTPLog)
            .where(
                OTPLog.user_id == agent_id,
                OTPLog.purpose == OTPPurpose.agent_2fa,
                OTPLog.is_verified == False,
                OTPLog.expires_at > utcnow(),
            )
            .order_by(OTPLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def verify_agent_otp(self, otp_plain: str, otp_log: Optional[OTPLog]) -> None:
        if not otp_log or not verify_otp(otp_plain, otp_log.otp_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired 2FA OTP",
            )
        otp_log.is_verified = True

    # ── Session ───────────────────────────────────────────────────────────────

    async def create_agent_session(
        self,
        db: AsyncSession,
        agent: Agent,
        ip_address: str,
        device_fingerprint: str,
    ) -> tuple[AgentSession, str, str]:
        access_token = create_access_token(
            str(agent.id),
            "agent",
            extra={"role": agent.role, "branch": agent.branch_code},
        )
        refresh_token = create_refresh_token(str(agent.id), "agent")

        session = AgentSession(
            agent_id=agent.id,
            jwt_token_hash=hash_token(access_token),
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            twofa_verified=True,
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        db.add(session)
        return session, access_token, refresh_token

    async def invalidate_agent_session(
        self, db: AsyncSession, agent_id: uuid.UUID, token: str
    ) -> None:
        token_hash = hash_token(token)
        result = await db.execute(
            select(AgentSession).where(
                AgentSession.agent_id == agent_id,
                AgentSession.jwt_token_hash == token_hash,
                AgentSession.is_active == True,
            )
        )
        session = result.scalar_one_or_none()
        if session:
            session.is_active = False


crud_auth_agent = CRUDAuthAgent()
