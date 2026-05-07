"""
CRUD — Audit Trail & KYC Lifecycle (Phase 11 & 12)
All DB operations extracted from api/v1/audit_lifecycle.py.
"""

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.base import utcnow
from app.models.enums import RefreshEventType, RefreshStatus, RiskClassification
from app.models.workflow import Account, AuditLog, KYCRefreshEvent, KYCRefreshSchedule


class CRUDAudit:

    async def list_logs(
        self,
        db: AsyncSession,
        actor_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        action: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AuditLog]:
        query = select(AuditLog)
        if actor_id:
            query = query.where(AuditLog.actor_id == actor_id)
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if action:
            query = query.where(AuditLog.action == action)
        query = (
            query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def list_by_entity(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
    ) -> list[AuditLog]:
        result = await db.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.asc())
        )
        return list(result.scalars().all())


crud_audit = CRUDAudit()


class CRUDLifecycle:

    def _review_due_date(self, risk_tier: RiskClassification) -> date:
        days = {
            RiskClassification.high: 365,
            RiskClassification.medium: 730,
            RiskClassification.low: 1825,
        }
        return (utcnow() + timedelta(days=days[risk_tier])).date()

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
        schedule.status = RefreshStatus.in_progress.value
        event = KYCRefreshEvent(
            schedule_id=schedule.id,
            event_type=RefreshEventType.customer_response.value,
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
        """Returns (completed_schedule, updated_account, new_schedule)."""
        result = await db.execute(
            select(KYCRefreshSchedule).where(
                KYCRefreshSchedule.account_id == account_id
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        account = await self.get_account(db, account_id)

        effective_tier = new_risk_tier or RiskClassification(schedule.risk_tier)
        next_due = self._review_due_date(effective_tier)

        schedule.status = RefreshStatus.completed.value
        schedule.completed_at = utcnow()
        schedule.risk_tier = effective_tier.value
        schedule.due_date = next_due

        account.kyc_next_review_date = next_due
        account.risk_tier = effective_tier.value

        event = KYCRefreshEvent(
            schedule_id=schedule.id,
            event_type=RefreshEventType.completed.value,
            notes=f"KYC refresh completed. Next due: {next_due}. Risk: {effective_tier.value}",
        )
        db.add(event)

        new_schedule = KYCRefreshSchedule(
            account_id=account_id,
            user_id=schedule.user_id,
            risk_tier=effective_tier.value,
            due_date=next_due,
            status=RefreshStatus.scheduled.value,
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
                    RefreshStatus.scheduled.value,
                    RefreshStatus.reminder_sent.value,
                ]),
            )
        )
        return list(result.scalars().all())


crud_lifecycle = CRUDLifecycle()
