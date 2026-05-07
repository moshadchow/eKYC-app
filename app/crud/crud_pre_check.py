"""
CRUD — Pre-Onboarding Assessment (Phase 2)
All business logic and DB operations extracted from api/v1/pre_check.py.
"""

import uuid
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.models.enums import KYCType, PreCheckDecision, ProductType, ResidencyStatus
from app.models.workflow import PreCheckLog


class CRUDPreCheck:

    # ── Decision engine ───────────────────────────────────────────────────────

    def run_decision_engine(
        self,
        product_type: ProductType,
        expected_investment: Optional[Decimal],
        annual_premium: Optional[Decimal],
        is_pep: bool,
        is_ip: bool,
    ) -> tuple[PreCheckDecision, str, dict]:
        """
        BFIU eKYC Guidelines Section 2.3 decision logic.
        Returns (decision, reason, thresholds_applied).
        """
        thresholds: dict = {}
        reasons: list[str] = []

        if is_pep or is_ip:
            reasons.append("PEP/IP declared — Enhanced Due Diligence required")

        investment = expected_investment or Decimal("0")
        premium = annual_premium or Decimal("0")

        if product_type == ProductType.bo_account:
            limit = Decimal(str(settings.SIMPLIFIED_BO_THRESHOLD_BDT))
            thresholds["bo_simplified_limit_bdt"] = float(limit)
            if investment > limit:
                reasons.append(
                    f"Investment BDT {investment:,.0f} exceeds "
                    f"simplified BO threshold BDT {limit:,.0f}"
                )

        elif product_type == ProductType.life_insurance:
            sum_limit = Decimal(str(settings.SIMPLIFIED_LIFE_SUM_ASSURED_BDT))
            prem_limit = Decimal(str(settings.SIMPLIFIED_LIFE_PREMIUM_BDT))
            thresholds["simplified_sum_assured_bdt"] = float(sum_limit)
            thresholds["simplified_annual_premium_bdt"] = float(prem_limit)
            if investment > sum_limit:
                reasons.append(
                    f"Sum assured BDT {investment:,.0f} exceeds "
                    f"simplified limit BDT {sum_limit:,.0f}"
                )
            if premium > prem_limit:
                reasons.append(
                    f"Annual premium BDT {premium:,.0f} exceeds "
                    f"simplified limit BDT {prem_limit:,.0f}"
                )

        elif product_type == ProductType.non_life_insurance:
            prem_limit = Decimal(str(settings.SIMPLIFIED_NON_LIFE_PREMIUM_BDT))
            thresholds["simplified_premium_bdt"] = float(prem_limit)
            if premium > prem_limit:
                reasons.append(
                    f"Premium BDT {premium:,.0f} exceeds "
                    f"simplified non-life limit BDT {prem_limit:,.0f}"
                )

        if reasons:
            return (PreCheckDecision.regular, "; ".join(reasons), thresholds)

        return (
            PreCheckDecision.simplified,
            "All thresholds within simplified eKYC limits and no high-risk flags",
            thresholds,
        )

    def decision_to_kyc_type(self, decision: PreCheckDecision) -> KYCType:
        return (
            KYCType.simplified
            if decision == PreCheckDecision.simplified
            else KYCType.regular
        )

    # ── DB operations ─────────────────────────────────────────────────────────

    async def create_pre_check_log(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        product_type: ProductType,
        investment_amount: Optional[Decimal],
        pep_declared: bool,
        ip_declared: bool,
        residency: ResidencyStatus,
        decision: PreCheckDecision,
        decision_reason: str,
        ip_address: Optional[str],
    ) -> PreCheckLog:
        log = PreCheckLog(
            user_id=user_id,
            product_type=product_type.value,
            investment_amount=investment_amount,
            pep_declared=pep_declared,
            ip_declared=ip_declared,
            residency=residency.value,
            decision=decision.value,
            decision_reason=decision_reason,
            ip_address=ip_address,
        )
        db.add(log)
        await db.flush()
        return log

    async def get_pre_check_log(
        self,
        db: AsyncSession,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PreCheckLog:
        result = await db.execute(
            select(PreCheckLog).where(
                PreCheckLog.id == log_id,
                PreCheckLog.user_id == user_id,
            )
        )
        log = result.scalar_one_or_none()
        if not log:
            raise HTTPException(status_code=404, detail="Pre-check log not found")
        return log


crud_pre_check = CRUDPreCheck()
