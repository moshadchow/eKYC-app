"""
Domain 1 — Identity & Access Control
Tables: users, otp_logs, sessions, agents, agent_devices, agent_sessions
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from .base import TimestampMixin, new_uuid, utcnow
from .enums import AgentRole, OTPPurpose, UserStatus


# ── users ─────────────────────────────────────────────────────────────────────

class UserBase(SQLModel):
    mobile_number: str = Field(
        max_length=15,
        index=True,
        description="BD mobile number, E.164 format e.g. +8801XXXXXXXXX",
    )
    email: Optional[str] = Field(
        default=None,
        max_length=255,
        index=True,
        description="Optional email address",
    )
    status: UserStatus = Field(
        default=UserStatus.active,
        description="Account lifecycle status",
    )


class User(UserBase, TimestampMixin, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(
        default_factory=new_uuid,
        primary_key=True,
        description="Primary key",
    )

    class Config:
        arbitrary_types_allowed = True


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime]


# ── otp_logs ──────────────────────────────────────────────────────────────────

class OTPLogBase(SQLModel):
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="FK → users.id",
    )
    otp_hash: str = Field(
        max_length=128,
        description="Bcrypt hash of the 6-digit OTP — never store plaintext",
    )
    purpose: OTPPurpose = Field(
        description="Why this OTP was issued",
    )
    attempt_count: int = Field(
        default=0,
        description="Number of verification attempts made against this OTP",
    )
    expires_at: datetime = Field(
        description="UTC expiry — typically created_at + 5 minutes",
    )
    is_verified: bool = Field(
        default=False,
        description="True once successfully verified; OTP becomes invalid",
    )


class OTPLog(OTPLogBase, table=True):
    __tablename__ = "otp_logs"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class OTPLogCreate(OTPLogBase):
    pass


# ── sessions ──────────────────────────────────────────────────────────────────

class SessionBase(SQLModel):
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="FK → users.id",
    )
    jwt_token_hash: str = Field(
        max_length=128,
        description="SHA-256 hash of the JWT — for server-side invalidation",
    )
    ip_address: str = Field(
        max_length=45,
        description="IPv4 or IPv6 address at session creation",
    )
    device_fingerprint: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Hashed browser/device fingerprint",
    )
    user_agent: Optional[str] = Field(
        default=None,
        max_length=512,
        description="HTTP User-Agent string",
    )
    expires_at: datetime = Field(
        description="UTC expiry of the refresh token",
    )
    is_active: bool = Field(
        default=True,
        description="False once logged out or token revoked",
    )


class Session(SessionBase, table=True):
    __tablename__ = "sessions"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class SessionCreate(SessionBase):
    pass


# ── agents ────────────────────────────────────────────────────────────────────

class AgentBase(SQLModel):
    employee_id: str = Field(
        max_length=50,
        unique=True,
        index=True,
        description="Institution-assigned employee ID",
    )
    full_name: str = Field(max_length=255)
    role: AgentRole = Field(description="RBAC role for this agent")
    branch_code: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Branch or office identifier",
    )
    is_active: bool = Field(default=True)


class Agent(AgentBase, TimestampMixin, table=True):
    __tablename__ = "agents"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    password_hash: str = Field(
        max_length=128,
        description="Bcrypt hash of agent password",
    )

    class Config:
        arbitrary_types_allowed = True


class AgentCreate(AgentBase):
    password: str


class AgentRead(AgentBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime]


# ── agent_devices ─────────────────────────────────────────────────────────────

class AgentDeviceBase(SQLModel):
    agent_id: uuid.UUID = Field(
        foreign_key="agents.id",
        index=True,
        description="FK → agents.id",
    )
    device_fingerprint: str = Field(
        max_length=255,
        description="Hashed device fingerprint",
    )
    device_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Human-readable device label e.g. 'Branch PC - Counter 3'",
    )
    is_authorized: bool = Field(
        default=False,
        description="Must be explicitly authorized by admin before use",
    )
    authorized_at: Optional[datetime] = Field(default=None)


class AgentDevice(AgentDeviceBase, table=True):
    __tablename__ = "agent_devices"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class AgentDeviceCreate(AgentDeviceBase):
    pass


# ── agent_sessions ────────────────────────────────────────────────────────────

class AgentSessionBase(SQLModel):
    agent_id: uuid.UUID = Field(
        foreign_key="agents.id",
        index=True,
        description="FK → agents.id",
    )
    jwt_token_hash: str = Field(max_length=128)
    ip_address: str = Field(max_length=45)
    device_fingerprint: Optional[str] = Field(default=None, max_length=255)
    twofa_verified: bool = Field(
        default=False,
        description="True once 2FA OTP has been successfully verified",
    )
    expires_at: datetime = Field(description="UTC expiry of the session")
    is_active: bool = Field(default=True)


class AgentSession(AgentSessionBase, table=True):
    __tablename__ = "agent_sessions"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class AgentSessionCreate(AgentSessionBase):
    pass
