"""
Domain 4 — Workflow, Audit Trail & Lifecycle Management
All enum fields use sa_column=sa.Column(sa.String) to prevent
SQLAlchemy from generating Postgres native ENUM types.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.models.base import TimestampMixin, new_uuid, utcnow
from app.models.enums import (
    AccountStatus,
    AccountType,
    ActorType,
    ApprovalAction,
    AuditAction,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    PreCheckDecision,
    QueuePriority,
    QueueStatus,
    QueueType,
    RefreshEventType,
    RefreshStatus,
    RiskClassification,
)


# ── pre_check_logs ────────────────────────────────────────────────────────────

class PreCheckLogBase(SQLModel):
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    product_type: str = Field(max_length=50)
    investment_amount: Optional[Decimal] = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(18, 2), nullable=True),
    )
    pep_declared: bool = Field(default=False)
    ip_declared: bool = Field(default=False)
    residency: str = Field(max_length=50)
    decision: str = Field(
        sa_column=sa.Column(sa.String(20), nullable=False),
    )
    decision_reason: Optional[str] = Field(default=None, max_length=500)
    ip_address: Optional[str] = Field(default=None, max_length=45)


class PreCheckLog(PreCheckLogBase, table=True):
    __tablename__ = "pre_check_logs"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class PreCheckLogCreate(PreCheckLogBase):
    pass


class PreCheckLogRead(PreCheckLogBase):
    id: uuid.UUID
    created_at: datetime


# ── approval_queue ────────────────────────────────────────────────────────────

class ApprovalQueueBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id", unique=True, index=True
    )
    queue_type: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    priority: str = Field(
        default=QueuePriority.normal,
        sa_column=sa.Column(sa.String(10), nullable=False, server_default="normal"),
    )
    assigned_maker_id: Optional[str] = Field(default=None, max_length=100)
    assigned_checker_id: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(
        default=QueueStatus.unassigned,
        sa_column=sa.Column(sa.String(20), nullable=False, server_default="unassigned"),
    )
    assigned_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )


class ApprovalQueue(ApprovalQueueBase, table=True):
    __tablename__ = "approval_queue"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class ApprovalQueueCreate(ApprovalQueueBase):
    pass


class ApprovalQueueRead(ApprovalQueueBase):
    id: uuid.UUID
    created_at: datetime


# ── approval_decisions ────────────────────────────────────────────────────────

class ApprovalDecisionBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(foreign_key="kyc_applications.id", index=True)
    queue_entry_id: uuid.UUID = Field(foreign_key="approval_queue.id", index=True)
    actor_id: str = Field(max_length=100)
    actor_role: str = Field(max_length=50)
    action: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    notes: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    rejection_reason: Optional[str] = Field(default=None, max_length=1000)


class ApprovalDecision(ApprovalDecisionBase, table=True):
    __tablename__ = "approval_decisions"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    decided_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class ApprovalDecisionCreate(ApprovalDecisionBase):
    pass


class ApprovalDecisionRead(ApprovalDecisionBase):
    id: uuid.UUID
    decided_at: datetime


# ── accounts ──────────────────────────────────────────────────────────────────

class AccountBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id", unique=True, index=True
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    account_number: str = Field(max_length=30, unique=True, index=True)
    unique_account_number: str = Field(max_length=30, unique=True)
    account_type: str = Field(
        sa_column=sa.Column(sa.String(40), nullable=False),
    )
    status: str = Field(
        default=AccountStatus.active,
        sa_column=sa.Column(sa.String(30), nullable=False, server_default="active"),
    )
    kyc_next_review_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    risk_tier: str = Field(
        sa_column=sa.Column(sa.String(10), nullable=False),
    )
    activated_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )
    closed_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )


class Account(AccountBase, TimestampMixin, table=True):
    __tablename__ = "accounts"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    class Config:
        arbitrary_types_allowed = True


class AccountCreate(AccountBase):
    pass


class AccountRead(AccountBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime]


# ── audit_logs ────────────────────────────────────────────────────────────────

class AuditLog(SQLModel, table=True):
    """Immutable append-only audit trail — no FK constraints, never updated."""
    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    actor_id: Optional[str] = Field(default=None, max_length=100, index=True)
    actor_type: str = Field(
        sa_column=sa.Column(sa.String(20), nullable=False),
    )
    entity_id: Optional[str] = Field(default=None, max_length=100, index=True)
    entity_type: str = Field(max_length=100, index=True)
    action: str = Field(
        sa_column=sa.Column(sa.String(40), nullable=False),
    )
    old_value_json: Optional[str] = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    new_value_json: Optional[str] = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    ip_address: Optional[str] = Field(default=None, max_length=45)
    device_fingerprint: Optional[str] = Field(default=None, max_length=255)
    user_agent: Optional[str] = Field(default=None, max_length=512)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False, index=True,
    )

    class Config:
        arbitrary_types_allowed = True


class AuditLogRead(SQLModel):
    id: uuid.UUID
    actor_id: Optional[str]
    actor_type: str
    entity_id: Optional[str]
    entity_type: str
    action: str
    old_value_json: Optional[str]
    new_value_json: Optional[str]
    ip_address: Optional[str]
    created_at: datetime


# ── notifications ─────────────────────────────────────────────────────────────

class NotificationBase(SQLModel):
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    kyc_application_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="kyc_applications.id", index=True
    )
    channel: str = Field(
        sa_column=sa.Column(sa.String(10), nullable=False),
    )
    notification_type: str = Field(
        sa_column=sa.Column(sa.String(40), nullable=False),
    )
    recipient_address: str = Field(max_length=255)
    message_body: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    status: str = Field(
        default=NotificationStatus.pending,
        sa_column=sa.Column(sa.String(15), nullable=False, server_default="pending"),
    )
    retry_count: int = Field(default=0)
    gateway_message_id: Optional[str] = Field(default=None, max_length=255)
    sent_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )
    delivered_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )


class Notification(NotificationBase, table=True):
    __tablename__ = "notifications"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class NotificationCreate(NotificationBase):
    pass


class NotificationRead(NotificationBase):
    id: uuid.UUID
    created_at: datetime
    error_message: Optional[str] = None
    gateway_response: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


# ── kyc_refresh_schedules ─────────────────────────────────────────────────────

class KYCRefreshScheduleBase(SQLModel):
    account_id: uuid.UUID = Field(foreign_key="accounts.id", unique=True, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    risk_tier: str = Field(
        sa_column=sa.Column(sa.String(10), nullable=False),
    )
    due_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False, index=True))
    status: str = Field(
        default=RefreshStatus.scheduled,
        sa_column=sa.Column(sa.String(20), nullable=False, server_default="scheduled"),
    )
    reminder_count: int = Field(default=0)
    last_reminder_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
    )


class KYCRefreshSchedule(KYCRefreshScheduleBase, table=True):
    __tablename__ = "kyc_refresh_schedules"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class KYCRefreshScheduleCreate(KYCRefreshScheduleBase):
    pass


class KYCRefreshScheduleRead(KYCRefreshScheduleBase):
    id: uuid.UUID
    created_at: datetime


# ── kyc_refresh_events ────────────────────────────────────────────────────────

class KYCRefreshEventBase(SQLModel):
    schedule_id: uuid.UUID = Field(foreign_key="kyc_refresh_schedules.id", index=True)
    kyc_application_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="kyc_applications.id"
    )
    event_type: str = Field(
        sa_column=sa.Column(sa.String(30), nullable=False),
    )
    notes: Optional[str] = Field(default=None, max_length=1000)


class KYCRefreshEvent(KYCRefreshEventBase, table=True):
    __tablename__ = "kyc_refresh_events"
    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
    )

    class Config:
        arbitrary_types_allowed = True


class KYCRefreshEventCreate(KYCRefreshEventBase):
    pass


class KYCRefreshEventRead(KYCRefreshEventBase):
    id: uuid.UUID
    created_at: datetime
