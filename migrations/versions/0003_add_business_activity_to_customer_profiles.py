"""Add business_activity column to customer_profiles

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-09

Adds a new nullable business_activity field to customer_profiles table
for BFIU Annexure-1 business activity risk scoring.

This column is optional - existing records will have NULL which defaults
to score 3 in the risk calculation.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer_profiles",
        sa.Column("business_activity", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("customer_profiles", "business_activity")