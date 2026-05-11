"""add ocr extraction extended columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocr_extractions", sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("ocr_extractions", sa.Column("ocr_provider", sa.String(50), nullable=True))
    op.add_column("ocr_extractions", sa.Column("field_confidence_json", sa.Text(), nullable=True))
    op.add_column("ocr_extractions", sa.Column("quality_flags_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("ocr_extractions", "quality_flags_json")
    op.drop_column("ocr_extractions", "field_confidence_json")
    op.drop_column("ocr_extractions", "ocr_provider")
    op.drop_column("ocr_extractions", "attempt_number")
