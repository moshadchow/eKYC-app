"""
CRUD — Admin Approval Workflow (Phase 9)
All business logic and DB operations extracted from api/v1/admin.py.
"""

import random
import string
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.base import utcnow
from app.models.compliance import PEPIPCheck, RiskScore, ScreeningResult
from app.models.enums import (
    AccountStatus,
    AccountType,
    ApprovalAction,
    ApplicationStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    QueuePriority,
    QueueStatus,
    QueueType,
    RefreshStatus,
    RiskClassification,
)
from app.models.onboarding import BiometricVerification, CustomerProfile, KYCApplication, KYCDocument
from app.models.identity import User
from app.models.workflow import (
    Account,
    ApprovalDecision,
    ApprovalQueue,
    KYCRefreshSchedule,
    Notification,
)


class CRUDAdmin:

    # ── Application ───────────────────────────────────────────────────────────

    async def get_application(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> KYCApplication:
        result = await db.execute(
            select(KYCApplication).where(KYCApplication.id == app_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        return app

    # ── Queue ─────────────────────────────────────────────────────────────────

    async def list_queue(
        self,
        db: AsyncSession,
        queue_type: Optional[QueueType] = None,
        status: Optional[QueueStatus] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ApprovalQueue]:
        query = select(ApprovalQueue)
        if queue_type:
            query = query.where(ApprovalQueue.queue_type == queue_type.value)
        if status:
            query = query.where(ApprovalQueue.status == status.value)
        query = query.order_by(ApprovalQueue.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_or_create_queue_entry(
        self, db: AsyncSession, app: KYCApplication
    ) -> ApprovalQueue:
        """Auto-determines queue type (standard/high_risk/failed_verification) from application data."""
        result = await db.execute(
            select(ApprovalQueue).where(
                ApprovalQueue.kyc_application_id == app.id
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            return entry

        rs_result = await db.execute(
            select(RiskScore)
            .where(RiskScore.kyc_application_id == app.id)
            .order_by(RiskScore.version.desc())
            .limit(1)
        )
        rs = rs_result.scalar_one_or_none()

        bio_result = await db.execute(
            select(BiometricVerification).where(
                BiometricVerification.kyc_application_id == app.id,
                BiometricVerification.is_matched == True,
            )
        )
        bio_ok = bio_result.scalar_one_or_none() is not None

        if not bio_ok:
            queue_type = QueueType.failed_verification
            priority = QueuePriority.high
        elif rs and rs.risk_classification == RiskClassification.high.value:
            queue_type = QueueType.high_risk
            priority = QueuePriority.high
        else:
            queue_type = QueueType.standard
            priority = QueuePriority.normal

        entry = ApprovalQueue(
            kyc_application_id=app.id,
            queue_type=queue_type.value,
            priority=priority.value,
            status=QueueStatus.unassigned.value,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def assign_queue_entry(
        self,
        db: AsyncSession,
        entry_id: uuid.UUID,
        maker_id: Optional[str],
        checker_id: Optional[str],
    ) -> ApprovalQueue:
        result = await db.execute(
            select(ApprovalQueue).where(ApprovalQueue.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(status_code=404, detail="Queue entry not found")

        if maker_id:
            entry.assigned_maker_id = maker_id
        if checker_id:
            if checker_id == entry.assigned_maker_id:
                raise HTTPException(
                    status_code=400,
                    detail="4-eyes principle: checker cannot be the same as the maker",
                )
            entry.assigned_checker_id = checker_id

        entry.status = QueueStatus.in_review.value
        entry.assigned_at = utcnow()
        return entry

    # ── Review summary ────────────────────────────────────────────────────────

    async def build_review_summary(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> dict:
        app = await self.get_application(db, app_id)

        profile_result = await db.execute(
            select(CustomerProfile).where(
                CustomerProfile.kyc_application_id == app_id
            )
        )
        profile = profile_result.scalar_one_or_none()

        bio_result = await db.execute(
            select(BiometricVerification).where(
                BiometricVerification.kyc_application_id == app_id,
                BiometricVerification.is_matched == True,
            )
        )
        bio = bio_result.scalar_one_or_none()

        screen_result = await db.execute(
            select(ScreeningResult).where(
                ScreeningResult.kyc_application_id == app_id,
                ScreeningResult.requires_review == True,
            )
        )
        has_screen_hit = screen_result.scalar_one_or_none() is not None

        pep_result = await db.execute(
            select(PEPIPCheck).where(PEPIPCheck.kyc_application_id == app_id)
        )
        pep = pep_result.scalar_one_or_none()

        rs_result = await db.execute(
            select(RiskScore)
            .where(RiskScore.kyc_application_id == app_id)
            .order_by(RiskScore.version.desc())
            .limit(1)
        )
        rs = rs_result.scalar_one_or_none()

        return {
            "app_id": str(app_id),
            "application_ref": app.application_ref,
            "kyc_type": app.kyc_type,
            "status": app.status,
            "customer_name": profile.full_name_en if profile else None,
            "nid_number": profile.nid_number if profile else None,
            "biometric_verified": bio is not None,
            "face_matched": bio is not None,
            "screening_clear": not has_screen_hit,
            "pep_ip_flagged": bool(pep and pep.edd_required),
            "risk_classification": rs.risk_classification if rs else None,
            "risk_score": rs.total_score if rs else None,
            "edd_required": bool(rs and rs.edd_required),
        }

    async def get_documents(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> list[KYCDocument]:
        """Get all documents for a KYC application."""
        result = await db.execute(
            select(KYCDocument).where(KYCDocument.kyc_application_id == app_id)
        )
        return list(result.scalars().all())

    # ── Decision ──────────────────────────────────────────────────────────────

    async def get_prior_decision(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> Optional[ApprovalDecision]:
        result = await db.execute(
            select(ApprovalDecision)
            .where(ApprovalDecision.kyc_application_id == app_id)
            .order_by(ApprovalDecision.decided_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_decision(
        self,
        db: AsyncSession,
        app: KYCApplication,
        queue_entry: ApprovalQueue,
        actor_id: str,
        actor_role: str,
        action: ApprovalAction,
        notes: Optional[str],
        rejection_reason: Optional[str],
    ) -> ApprovalDecision:
        if action == ApprovalAction.reject and not rejection_reason:
            raise HTTPException(
                status_code=422,
                detail="rejection_reason is required when action is reject",
            )

        prior = await self.get_prior_decision(db, app.id)
        if prior and prior.actor_id == actor_id:
            raise HTTPException(
                status_code=400,
                detail="4-eyes principle: a different agent must make the checker decision",
            )

        decision = ApprovalDecision(
            kyc_application_id=app.id,
            queue_entry_id=queue_entry.id,
            actor_id=actor_id,
            actor_role=actor_role,
            action=action.value,
            notes=notes,
            rejection_reason=rejection_reason,
        )
        db.add(decision)

        status_map = {
            ApprovalAction.approve: ApplicationStatus.approved.value,
            ApprovalAction.reject: ApplicationStatus.rejected.value,
            ApprovalAction.request_more_info: ApplicationStatus.edd_pending.value,
            ApprovalAction.escalate: ApplicationStatus.pending_approval.value,
        }
        if action in status_map:
            app.status = status_map[action]

        if action == ApprovalAction.approve:
            queue_entry.status = QueueStatus.completed.value
            queue_entry.completed_at = utcnow()

        return decision

    # ── Account activation ────────────────────────────────────────────────────

    def _refresh_due_date(self, risk_tier: RiskClassification) -> date:
        days = {
            RiskClassification.high: 365,
            RiskClassification.medium: 730,
            RiskClassification.low: 1825,
        }
        return (utcnow() + timedelta(days=days[risk_tier])).date()

    async def activate_account(
        self, db: AsyncSession, app: KYCApplication
    ) -> Account:
        if app.status != ApplicationStatus.approved.value:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot activate: application status is {app.status}",
            )

        rs_result = await db.execute(
            select(RiskScore)
            .where(RiskScore.kyc_application_id == app.id)
            .order_by(RiskScore.version.desc())
            .limit(1)
        )
        rs = rs_result.scalar_one_or_none()
        risk_tier = (
            RiskClassification(rs.risk_classification)
            if rs else RiskClassification.low
        )

        account_type_map = {
            "bo_account": AccountType.bo_account,
            "life_insurance": AccountType.life_insurance_policy,
            "non_life_insurance": AccountType.non_life_insurance_policy,
        }
        account_num = "BO" + "".join(random.choices(string.digits, k=10))
        unique_num = "CDBL" + "".join(random.choices(string.digits, k=8))

        account = Account(
            kyc_application_id=app.id,
            user_id=app.user_id,
            account_number=account_num,
            unique_account_number=unique_num,
            account_type=account_type_map.get(str(app.product_type), AccountType.bo_account).value,
            status=AccountStatus.active.value,
            risk_tier=risk_tier.value,
            kyc_next_review_date=self._refresh_due_date(risk_tier),
            activated_at=utcnow(),
        )
        db.add(account)
        await db.flush()

        schedule = KYCRefreshSchedule(
            account_id=account.id,
            user_id=app.user_id,
            risk_tier=risk_tier.value,
            due_date=self._refresh_due_date(risk_tier),
            status=RefreshStatus.scheduled.value,
        )
        db.add(schedule)
        await db.flush()

        # Look up user for real notification address
        user_result = await db.execute(
            select(User).where(User.id == app.user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found for notification")

        notif = Notification(
            user_id=app.user_id,
            kyc_application_id=app.id,
            channel=NotificationChannel.sms.value,
            notification_type=NotificationType.account_activation.value,
            recipient_address=user.mobile_number,
            message_body=(
                f"Your account {account_num} has been activated. "
                f"Reference: {app.application_ref}"
            ),
            status=NotificationStatus.pending.value,
        )
        db.add(notif)
        return account


crud_admin = CRUDAdmin()
