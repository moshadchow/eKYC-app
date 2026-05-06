"""
Domain 4 — Workflow, Audit Trail & Lifecycle Management
Tables: pre_check_logs, approval_queue, approval_decisions,
        accounts, audit_logs, notifications,
        kyc_refresh_schedules, kyc_refresh_events
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field, SQLModel

from .base import TimestampMixin, new_uuid, utcnow
from .enums import (
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
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="Customer who completed the pre-check questionnaire",
    )
    product_type: str = Field(
        max_length=50,
        description="Product type selected e.g. bo_account, life_insurance",
    )
    investment_amount: Optional[Decimal] = Field(
        default=None,
        decimal_places=2,
        max_digits=18,
        description="Expected investment/premium in BDT",
    )

    # Risk declarations
    pep_declared: bool = Field(
        default=False,
        description="Did the customer self-declare as PEP?",
    )
    ip_declared: bool = Field(
        default=False,
        description="Did the customer self-declare as IP?",
    )
    residency: str = Field(
        max_length=50,
        description="resident_bangladeshi or non_resident_bangladeshi",
    )

    # Decision engine output
    decision: PreCheckDecision = Field(
        description="simplified | regular | rejected — output of decision engine",
    )
    decision_reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Human-readable explanation of the decision",
    )

    # Contextual metadata
    ip_address: Optional[str] = Field(default=None, max_length=45)


class PreCheckLog(PreCheckLogBase, table=True):
    __tablename__ = "pre_check_logs"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

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
        foreign_key="kyc_applications.id",
        unique=True,
        index=True,
        description="One queue entry per application",
    )
    queue_type: QueueType = Field(
        index=True,
        description="standard | high_risk | failed_verification | edd_pending",
    )
    priority: QueuePriority = Field(
        default=QueuePriority.normal,
        index=True,
    )
    assigned_maker_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Agent ID of the maker assigned to this application",
    )
    assigned_checker_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Agent ID of the checker — must differ from maker",
    )
    status: QueueStatus = Field(
        default=QueueStatus.unassigned,
        index=True,
    )
    assigned_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)


class ApprovalQueue(ApprovalQueueBase, table=True):
    __tablename__ = "approval_queue"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class ApprovalQueueCreate(ApprovalQueueBase):
    pass


class ApprovalQueueRead(ApprovalQueueBase):
    id: uuid.UUID
    created_at: datetime


# ── approval_decisions ────────────────────────────────────────────────────────

class ApprovalDecisionBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        index=True,
    )
    queue_entry_id: uuid.UUID = Field(
        foreign_key="approval_queue.id",
        index=True,
    )

    # Actor
    actor_id: str = Field(
        max_length=100,
        description="Agent ID or system identifier who made the decision",
    )
    actor_role: str = Field(
        max_length=50,
        description="maker | checker | compliance_officer — role at time of decision",
    )

    # Decision
    action: ApprovalAction = Field(
        description="approve | reject | request_more_info | escalate | override_risk",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Maker/checker notes visible to both",
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Mandatory when action = reject",
    )


class ApprovalDecision(ApprovalDecisionBase, table=True):
    __tablename__ = "approval_decisions"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    decided_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class ApprovalDecisionCreate(ApprovalDecisionBase):
    pass


class ApprovalDecisionRead(ApprovalDecisionBase):
    id: uuid.UUID
    decided_at: datetime


# ── accounts ──────────────────────────────────────────────────────────────────

def _default_review_date() -> date:
    """Placeholder — overwritten at activation based on risk tier."""
    return (datetime.now(timezone.utc) + timedelta(days=365 * 5)).date()


class AccountBase(SQLModel):
    kyc_application_id: uuid.UUID = Field(
        foreign_key="kyc_applications.id",
        unique=True,
        index=True,
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
    )
    account_number: str = Field(
        max_length=30,
        unique=True,
        index=True,
        description="Institution-generated account/policy number",
    )
    unique_account_number: str = Field(
        max_length=30,
        unique=True,
        description="CDBL or insurer unique account identifier",
    )
    account_type: AccountType = Field()
    status: AccountStatus = Field(
        default=AccountStatus.active,
        index=True,
    )

    # KYC lifecycle
    kyc_next_review_date: date = Field(
        default_factory=_default_review_date,
        description="Calculated at activation: high=+1yr, medium=+2yr, low=+5yr",
    )
    risk_tier: RiskClassification = Field(
        description="Current risk tier — may change on reassessment",
    )

    # Timestamps
    activated_at: Optional[datetime] = Field(default=None)
    closed_at: Optional[datetime] = Field(
        default=None,
        description="Set on account closure — triggers 5-year retention clock",
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
    """
    Immutable append-only audit trail.
    Never update or delete rows in this table.
    All application events are recorded here with actor + entity context.
    """
    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    # Actor context
    actor_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="UUID string of user/agent, or 'system'",
        index=True,
    )
    actor_type: ActorType = Field(
        description="customer | agent | system",
    )

    # Subject entity
    entity_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="UUID string of the affected record",
        index=True,
    )
    entity_type: str = Field(
        max_length=100,
        description="Table/model name e.g. 'kyc_applications', 'biometric_verifications'",
        index=True,
    )

    # Event
    action: AuditAction = Field(
        index=True,
        description="What happened",
    )
    old_value_json: Optional[str] = Field(
        default=None,
        description="JSON snapshot of relevant fields before the change",
    )
    new_value_json: Optional[str] = Field(
        default=None,
        description="JSON snapshot of relevant fields after the change",
    )

    # Request metadata
    ip_address: Optional[str] = Field(default=None, max_length=45)
    device_fingerprint: Optional[str] = Field(default=None, max_length=255)
    user_agent: Optional[str] = Field(default=None, max_length=512)

    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        index=True,
    )

    class Config:
        arbitrary_types_allowed = True


class AuditLogRead(SQLModel):
    id: uuid.UUID
    actor_id: Optional[str]
    actor_type: ActorType
    entity_id: Optional[str]
    entity_type: str
    action: AuditAction
    old_value_json: Optional[str]
    new_value_json: Optional[str]
    ip_address: Optional[str]
    created_at: datetime


# ── notifications ─────────────────────────────────────────────────────────────

class NotificationBase(SQLModel):
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
    )
    kyc_application_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="kyc_applications.id",
        index=True,
        description="Linked application — null for generic account notifications",
    )
    channel: NotificationChannel = Field(description="sms | email | push")
    notification_type: NotificationType = Field()
    recipient_address: str = Field(
        max_length=255,
        description="Mobile number, email address, or FCM device token",
    )
    message_body: str = Field(
        max_length=2000,
        description="Rendered message content — no secrets or PII beyond identifier",
    )
    status: NotificationStatus = Field(
        default=NotificationStatus.pending,
        index=True,
    )
    retry_count: int = Field(
        default=0,
        description="Number of delivery retries attempted",
    )
    gateway_message_id: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Message ID returned by SMS/email gateway for delivery tracking",
    )
    sent_at: Optional[datetime] = Field(default=None)
    delivered_at: Optional[datetime] = Field(
        default=None,
        description="Set when delivery receipt received from gateway",
    )


class Notification(NotificationBase, table=True):
    __tablename__ = "notifications"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class NotificationCreate(NotificationBase):
    pass


class NotificationRead(NotificationBase):
    id: uuid.UUID
    created_at: datetime


# ── kyc_refresh_schedules ─────────────────────────────────────────────────────

class KYCRefreshScheduleBase(SQLModel):
    account_id: uuid.UUID = Field(
        foreign_key="accounts.id",
        unique=True,
        index=True,
        description="One active schedule per account",
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
    )
    risk_tier: RiskClassification = Field(
        description="Risk tier at time of schedule creation — drives due_date",
    )
    due_date: date = Field(
        index=True,
        description="Date by which KYC must be refreshed. "
                    "high=+1yr, medium=+2yr, low=+5yr from activation or last review",
    )
    status: RefreshStatus = Field(
        default=RefreshStatus.scheduled,
        index=True,
    )
    reminder_count: int = Field(
        default=0,
        description="Number of reminder notifications sent",
    )
    last_reminder_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Set when refresh is accepted and new review date is calculated",
    )


class KYCRefreshSchedule(KYCRefreshScheduleBase, table=True):
    __tablename__ = "kyc_refresh_schedules"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class KYCRefreshScheduleCreate(KYCRefreshScheduleBase):
    pass


class KYCRefreshScheduleRead(KYCRefreshScheduleBase):
    id: uuid.UUID
    created_at: datetime


# ── kyc_refresh_events ────────────────────────────────────────────────────────

class KYCRefreshEventBase(SQLModel):
    schedule_id: uuid.UUID = Field(
        foreign_key="kyc_refresh_schedules.id",
        index=True,
    )
    kyc_application_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="kyc_applications.id",
        description="Linked to the new application opened during refresh",
    )
    event_type: RefreshEventType = Field()
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="e.g. 'Customer self-declaration received — no changes'",
    )


class KYCRefreshEvent(KYCRefreshEventBase, table=True):
    __tablename__ = "kyc_refresh_events"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    class Config:
        arbitrary_types_allowed = True


class KYCRefreshEventCreate(KYCRefreshEventBase):
    pass


class KYCRefreshEventRead(KYCRefreshEventBase):
    id: uuid.UUID
    created_at: datetime
