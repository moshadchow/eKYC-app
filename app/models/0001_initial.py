"""
Initial migration — creates all 21 eKYC tables.

Run:
    alembic upgrade head

To generate a new migration after model changes:
    alembic revision --autogenerate -m "describe change"
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mobile_number", sa.String(15), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_mobile_number", "users", ["mobile_number"])
    op.create_index("ix_users_email", "users", ["email"])

    # ── otp_logs ──────────────────────────────────────────────────────────────
    op.create_table(
        "otp_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("otp_hash", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_otp_logs_user_id", "otp_logs", ["user_id"])

    # ── sessions ──────────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("jwt_token_hash", sa.String(128), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("device_fingerprint", sa.String(255), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # ── agents ────────────────────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", sa.String(50), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("branch_code", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agents_employee_id", "agents", ["employee_id"])

    # ── agent_devices ─────────────────────────────────────────────────────────
    op.create_table(
        "agent_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("device_fingerprint", sa.String(255), nullable=False),
        sa.Column("device_name", sa.String(255), nullable=True),
        sa.Column("is_authorized", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── agent_sessions ────────────────────────────────────────────────────────
    op.create_table(
        "agent_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("jwt_token_hash", sa.String(128), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("device_fingerprint", sa.String(255), nullable=True),
        sa.Column("twofa_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── kyc_applications ──────────────────────────────────────────────────────
    op.create_table(
        "kyc_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("kyc_type", sa.String(20), nullable=False),
        sa.Column("onboarding_channel", sa.String(30), nullable=False),
        sa.Column("product_type", sa.String(30), nullable=False),
        sa.Column("product_code", sa.String(50), nullable=True),
        sa.Column("expected_investment", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("application_ref", sa.String(30), nullable=True, unique=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_kyc_applications_user_id", "kyc_applications", ["user_id"])
    op.create_index("ix_kyc_applications_status", "kyc_applications", ["status"])
    op.create_index("ix_kyc_applications_ref", "kyc_applications", ["application_ref"])

    # ── customer_profiles ─────────────────────────────────────────────────────
    op.create_table(
        "customer_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("full_name_en", sa.String(255), nullable=False),
        sa.Column("full_name_bn", sa.String(255), nullable=True),
        sa.Column("fathers_name_en", sa.String(255), nullable=True),
        sa.Column("fathers_name_bn", sa.String(255), nullable=True),
        sa.Column("mothers_name_en", sa.String(255), nullable=True),
        sa.Column("mothers_name_bn", sa.String(255), nullable=True),
        sa.Column("spouse_name_en", sa.String(255), nullable=True),
        sa.Column("date_of_birth", sa.Date, nullable=False),
        sa.Column("gender", sa.String(1), nullable=True),
        sa.Column("nid_number", sa.String(20), nullable=False),
        sa.Column("tin_number", sa.String(20), nullable=True),
        sa.Column("profession", sa.String(255), nullable=True),
        sa.Column("monthly_income", sa.Numeric(18, 2), nullable=True),
        sa.Column("source_of_fund", sa.String(30), nullable=True),
        sa.Column("source_of_fund_detail", sa.String(500), nullable=True),
        sa.Column("mobile_number", sa.String(15), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("present_address", sa.Text, nullable=True),
        sa.Column("permanent_address", sa.Text, nullable=True),
        sa.Column("nationality", sa.String(100), nullable=False, server_default="Bangladeshi"),
        sa.Column("residency_status", sa.String(30), nullable=False),
        sa.Column("is_pep", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_ip", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_nrb", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_customer_profiles_nid", "customer_profiles", ["nid_number"])

    # ── nominees ──────────────────────────────────────────────────────────────
    op.create_table(
        "nominees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=True),
        sa.Column("relation", sa.String(20), nullable=False),
        sa.Column("contact_number", sa.String(15), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("photo_storage_key", sa.String(512), nullable=True),
        sa.Column("is_minor", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("guardian_name", sa.String(255), nullable=True),
        sa.Column("guardian_nid", sa.String(20), nullable=True),
        sa.Column("guardian_address", sa.Text, nullable=True),
        sa.Column("guardian_photo_storage_key", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── kyc_documents ─────────────────────────────────────────────────────────
    op.create_table(
        "kyc_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("is_encrypted", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── biometric_verifications ───────────────────────────────────────────────
    op.create_table(
        "biometric_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("verification_type", sa.String(20), nullable=False),
        sa.Column("nid_number", sa.String(20), nullable=False),
        sa.Column("dob_provided", sa.Date, nullable=False),
        sa.Column("similarity_score", sa.Float, nullable=True),
        sa.Column("is_matched", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("session_number", sa.Integer, nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("device_info", sa.String(512), nullable=True),
        sa.Column("mock_api_response", sa.Text, nullable=True),
        sa.Column("failure_reason", sa.String(50), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_biometric_kyc_app", "biometric_verifications", ["kyc_application_id"])

    # ── ocr_extractions ───────────────────────────────────────────────────────
    op.create_table(
        "ocr_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_documents.id"), nullable=False),
        sa.Column("raw_json", sa.Text, nullable=False),
        sa.Column("extracted_name_en", sa.String(255), nullable=True),
        sa.Column("extracted_name_bn", sa.String(255), nullable=True),
        sa.Column("extracted_nid", sa.String(20), nullable=True),
        sa.Column("extracted_dob", sa.Date, nullable=True),
        sa.Column("extracted_address", sa.Text, nullable=True),
        sa.Column("extracted_fathers_name", sa.String(255), nullable=True),
        sa.Column("extracted_mothers_name", sa.String(255), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── digital_signatures ────────────────────────────────────────────────────
    op.create_table(
        "digital_signatures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False, unique=True),
        sa.Column("signature_type", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("pin_hash", sa.String(128), nullable=True),
        sa.Column("is_low_risk_pin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── screening_results ─────────────────────────────────────────────────────
    op.create_table(
        "screening_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("screen_type", sa.String(30), nullable=False),
        sa.Column("list_source", sa.String(100), nullable=False),
        sa.Column("matched_name", sa.String(255), nullable=True),
        sa.Column("match_score", sa.Float, nullable=True),
        sa.Column("result", sa.String(30), nullable=False),
        sa.Column("raw_response", sa.Text, nullable=True),
        sa.Column("requires_review", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("screened_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── pep_ip_checks ─────────────────────────────────────────────────────────
    op.create_table(
        "pep_ip_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False, unique=True),
        sa.Column("is_pep", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_ip", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_family_of_pep", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_family_of_ip", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_high_official_intl_org", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("match_detail", sa.String(1000), nullable=True),
        sa.Column("edd_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── beneficial_owners ─────────────────────────────────────────────────────
    op.create_table(
        "beneficial_owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("nid_number", sa.String(20), nullable=True),
        sa.Column("ownership_percentage", sa.Float, nullable=True),
        sa.Column("is_pep", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_ip", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cdd_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("cdd_notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── risk_scores ───────────────────────────────────────────────────────────
    op.create_table(
        "risk_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("score_onboarding_channel", sa.Integer, nullable=False),
        sa.Column("score_geography", sa.Integer, nullable=False),
        sa.Column("score_customer_type", sa.Integer, nullable=False),
        sa.Column("score_product", sa.Integer, nullable=False),
        sa.Column("score_business_activity", sa.Integer, nullable=False),
        sa.Column("score_profession", sa.Integer, nullable=False),
        sa.Column("score_transaction_volume", sa.Integer, nullable=False),
        sa.Column("score_transparency", sa.Integer, nullable=False),
        sa.Column("total_score", sa.Integer, nullable=False),
        sa.Column("risk_classification", sa.String(10), nullable=False),
        sa.Column("edd_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_scores_kyc_app", "risk_scores", ["kyc_application_id"])

    # ── edd_requests ──────────────────────────────────────────────────────────
    op.create_table(
        "edd_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("risk_score_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risk_scores.id"), nullable=False),
        sa.Column("trigger_reason", sa.String(30), nullable=False),
        sa.Column("required_documents", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("compliance_officer_id", sa.String(100), nullable=True),
        sa.Column("compliance_notes", sa.Text, nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_edd_requests_status", "edd_requests", ["status"])

    # ── edd_documents ─────────────────────────────────────────────────────────
    op.create_table(
        "edd_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("edd_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("edd_requests.id"), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── pre_check_logs ────────────────────────────────────────────────────────
    op.create_table(
        "pre_check_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_type", sa.String(50), nullable=False),
        sa.Column("investment_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("pep_declared", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ip_declared", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("residency", sa.String(50), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("decision_reason", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── approval_queue ────────────────────────────────────────────────────────
    op.create_table(
        "approval_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False, unique=True),
        sa.Column("queue_type", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("assigned_maker_id", sa.String(100), nullable=True),
        sa.Column("assigned_checker_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="unassigned"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approval_queue_status", "approval_queue", ["status", "queue_type"])

    # ── approval_decisions ────────────────────────────────────────────────────
    op.create_table(
        "approval_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False),
        sa.Column("queue_entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_queue.id"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("rejection_reason", sa.String(1000), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── accounts ──────────────────────────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_number", sa.String(30), nullable=False, unique=True),
        sa.Column("unique_account_number", sa.String(30), nullable=False, unique=True),
        sa.Column("account_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("kyc_next_review_date", sa.Date, nullable=False),
        sa.Column("risk_tier", sa.String(10), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_accounts_account_number", "accounts", ["account_number"])
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("old_value_json", sa.Text, nullable=True),
        sa.Column("new_value_json", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("device_fingerprint", sa.String(255), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_actor", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ── notifications ─────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=True),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("notification_type", sa.String(40), nullable=False),
        sa.Column("recipient_address", sa.String(255), nullable=False),
        sa.Column("message_body", sa.Text, nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gateway_message_id", sa.String(255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])

    # ── kyc_refresh_schedules ─────────────────────────────────────────────────
    op.create_table(
        "kyc_refresh_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("risk_tier", sa.String(10), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("reminder_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_schedules_due_date", "kyc_refresh_schedules", ["due_date", "status"])

    # ── kyc_refresh_events ────────────────────────────────────────────────────
    op.create_table(
        "kyc_refresh_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_refresh_schedules.id"), nullable=False),
        sa.Column("kyc_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_applications.id"), nullable=True),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "kyc_refresh_events", "kyc_refresh_schedules", "notifications",
        "audit_logs", "accounts", "approval_decisions", "approval_queue",
        "pre_check_logs", "edd_documents", "edd_requests", "risk_scores",
        "beneficial_owners", "pep_ip_checks", "screening_results",
        "digital_signatures", "ocr_extractions", "biometric_verifications",
        "kyc_documents", "nominees", "customer_profiles", "kyc_applications",
        "agent_sessions", "agent_devices", "agents",
        "sessions", "otp_logs", "users",
    ]:
        op.drop_table(table)
