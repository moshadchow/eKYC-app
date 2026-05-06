import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin(SQLModel):
    """Adds created_at / updated_at to any table model."""

    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        description="UTC timestamp of record creation",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
        sa_column_kwargs={"onupdate": utcnow},
        description="UTC timestamp of last update",
    )
