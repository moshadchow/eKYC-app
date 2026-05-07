"""
CRUD — KYC Lifecycle Management (Phase 12)
Handles: refresh schedule lookup, initiation, completion, overdue queries.
"""

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.base import utcnow
from app.models.enums import RefreshEventType, RefreshStatus, RiskClassification
from app.models.workflow import Account, KYCRefreshEvent, KYCRefreshSchedule


class CRUDLifecycle:

    def review_due_date(self, risk_tier: RiskClassification) -> date:
        days = {
            RiskClassification.high: 365,
            RiskClassification.medium: 730,
            RiskClassification.low: 1825,
        }
        return (utcnow() + timedelta(days=days[risk_tier])).date()

    # ── Schedule ──────────────────────────────────────────────────────────────

    async def get_schedule(
        self,
        db: AsyncSession,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> KYCRefreshSchedule:
        result = await db.execute(
            select(KYCRefreshSchedule).where(
                KYCRefreshSchedule.account_id == account_id,
                KYCRefreshSchedule.user_id == user_id,
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            raise HTTPException(status_code=404, detail="No refresh schedule found")
        return schedule

    async def get_account(
        self, db: AsyncSession, account_id: uuid.UUID
    ) -> Account:
        result = await db.execute(
            select(Account).where(Account.id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        return account

    async def initiate_refresh(
        self, db: AsyncSession, schedule: KYCRefreshSchedule
    ) -> KYCRefreshSchedule:
        schedule.status = RefreshStatus.in_progress
        event = KYCRefreshEvent(
            schedule_id=schedule.id,
            event_type=RefreshEventType.customer_response,
            notes="Customer initiated KYC refresh",
        )
        db.add(event)
        return schedule

    async def complete_refresh(
        self,
        db: AsyncSession,
        account_id: uuid.UUID,
        new_risk_tier: Optional[RiskClassification] = None,
    ) -> tuple[KYCRefreshSchedule, Account, KYCRefreshSchedule]:
        """
        Mark current schedule complete, update account, create next schedule.
        Returns (completed_schedule, updated_account, new_schedule).
        """
        # Get active schedule (not filtered by user_id — called by agent)
        result = await db.execute(
            select(KYCRefreshSchedule).where(
                KYCRefreshSchedule.account_id == account_id
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        account = await self.get_account(db, account_id)
        effective_tier = new_risk_tier or schedule.risk_tier
        next_due = self.review_due_date(effective_tier)

        # Complete current
        schedule.status = RefreshStatus.completed
        schedule.completed_at = utcnow()
        schedule.risk_tier = effective_tier
        schedule.due_date = next_due

        # Update account
        account.kyc_next_review_date = next_due
        account.risk_tier = effective_tier

        # Log event
        event = KYCRefreshEvent(
            schedule_id=schedule.id,
            event_type=RefreshEventType.completed,
            notes=f"KYC refresh completed. Next due: {next_due}. Risk: {effective_tier}",
        )
        db.add(event)

        # Create next schedule
        new_schedule = KYCRefreshSchedule(
            account_id=account_id,
            user_id=schedule.user_id,
            risk_tier=effective_tier,
            due_date=next_due,
            status=RefreshStatus.scheduled,
        )
        db.add(new_schedule)
        await db.flush()

        return schedule, account, new_schedule

    async def list_overdue(self, db: AsyncSession) -> list[KYCRefreshSchedule]:
        today = date.today()
        result = await db.execute(
            select(KYCRefreshSchedule).where(
                KYCRefreshSchedule.due_date < today,
                KYCRefreshSchedule.status.in_([
                    RefreshStatus.scheduled,
                    RefreshStatus.reminder_sent,
                ]),
            )
        )
        return list(result.scalars().all())


crud_lifecycle = CRUDLifecycle()
