import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Naive UTC datetime — matches TIMESTAMP WITHOUT TIME ZONE columns.
    asyncpg requires naive datetimes for timezone=False columns.
    """
    return datetime.utcnow()


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin(SQLModel):
    """
    Adds created_at / updated_at using plain Field() — no sa_column.
    Keeping it simple avoids the 'Column already assigned' error that
    occurs when sa_column objects are shared across multiple subclasses.
    The TIMESTAMP WITHOUT TIME ZONE type is enforced by utcnow() returning
    a naive datetime, which asyncpg maps correctly.
    """
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None, nullable=True)
