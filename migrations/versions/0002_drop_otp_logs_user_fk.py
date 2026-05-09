"""Drop otp_logs.user_id FK — column stores both user and agent UUIDs

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08

The initial migration incorrectly added a FK from otp_logs.user_id to
users.id.  Agent 2FA OTPs store an agent UUID in that column, which has
no row in users, causing a ForeignKeyViolationError on insert.

IF EXISTS makes this safe to run on fresh DBs that already used the
corrected 0001 (where the constraint was never created).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE otp_logs DROP CONSTRAINT IF EXISTS otp_logs_user_id_fkey"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE otp_logs ADD CONSTRAINT otp_logs_user_id_fkey "
        "FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE"
    )
