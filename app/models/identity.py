"""
Domain 1 — Identity & Access Control

Key fixes:
  - All enum Field defaults use .value (plain str), not the enum member.
    asyncpg sees the Python value before SQLAlchemy type coercion and
    rejects enum objects with "can't subtract offset-naive..." or similar.
  - All datetime columns use DateTime(timezone=False) + naive utcnow().
  - All enum columns use sa.Column(sa.String(N)) — no Postgres native ENUM.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.models.base import TimestampMixin, new_uuid, utcnow
from app.models.enums import AgentRole, OTPPurpose, UserStatus


# ── users ─────────────────────────────────────────────────────────────────────

class UserBase(SQLModel):
    mobile_number: str = Field(max_length=15, index=True)
    email: Optional[str] = Field(default=None, max_length=255, index=True)
    status: str = Field(
        default=UserStatus.active.value,           # ← .value = plain "active"
        sa_column=sa.Column(sa.String(20), nullable=False, server_default="active"),
    )


class User(UserBase, TimestampMixin, table=True):
    __tablename__ = "users"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

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
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    otp_hash: str = Field(max_length=128)
    purpose: str = Field(
        sa_column=sa.Column(sa.String(50), nullable=False),
    )
    attempt_count: int = Field(default=0)
    expires_at: datetime = Field(
        nullable=False,
    )
    is_verified: bool = Field(default=False)


class OTPLog(OTPLogBase, table=True):
    __tablename__ = "otp_logs"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class OTPLogCreate(OTPLogBase):
    pass


# ── sessions ──────────────────────────────────────────────────────────────────

class SessionBase(SQLModel):
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    jwt_token_hash: str = Field(max_length=128)
    ip_address: str = Field(max_length=45)
    device_fingerprint: Optional[str] = Field(default=None, max_length=255)
    user_agent: Optional[str] = Field(default=None, max_length=512)
    expires_at: datetime = Field(
        nullable=False,
    )
    is_active: bool = Field(default=True)


class Session(SessionBase, table=True):
    __tablename__ = "sessions"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class SessionCreate(SessionBase):
    pass


# ── agents ────────────────────────────────────────────────────────────────────

class AgentBase(SQLModel):
    employee_id: str = Field(max_length=50, unique=True, index=True)
    full_name: str = Field(max_length=255)
    role: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    branch_code: Optional[str] = Field(default=None, max_length=20)
    is_active: bool = Field(default=True)


class Agent(AgentBase, TimestampMixin, table=True):
    __tablename__ = "agents"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    password_hash: str = Field(max_length=128)

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
    agent_id: uuid.UUID = Field(foreign_key="agents.id", index=True)
    device_fingerprint: str = Field(max_length=255)
    device_name: Optional[str] = Field(default=None, max_length=255)
    is_authorized: bool = Field(default=False)
    authorized_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )


class AgentDevice(AgentDeviceBase, table=True):
    __tablename__ = "agent_devices"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class AgentDeviceCreate(AgentDeviceBase):
    pass


# ── agent_sessions ────────────────────────────────────────────────────────────

class AgentSessionBase(SQLModel):
    agent_id: uuid.UUID = Field(foreign_key="agents.id", index=True)
    jwt_token_hash: str = Field(max_length=128)
    ip_address: str = Field(max_length=45)
    device_fingerprint: Optional[str] = Field(default=None, max_length=255)
    twofa_verified: bool = Field(default=False)
    expires_at: datetime = Field(
        nullable=False,
    )
    is_active: bool = Field(default=True)


class AgentSession(AgentSessionBase, table=True):
    __tablename__ = "agent_sessions"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class AgentSessionCreate(AgentSessionBase):
    pass
