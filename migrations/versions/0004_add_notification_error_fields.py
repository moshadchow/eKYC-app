"""Add error_message and gateway_response to notifications

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-10

Adds two nullable columns to the notifications table:
- error_message: stores the last gateway failure reason (up to 500 chars)
- gateway_response: stores raw gateway response for debugging (unlimited text)

These columns are needed to track notification delivery failures and support
retry logic required by BFIU audit trail requirements.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("error_message", sa.String(500), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("gateway_response", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notifications", "gateway_response")
    op.drop_column("notifications", "error_message")