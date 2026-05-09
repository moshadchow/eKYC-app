"""
CRUD — AML Compliance & Risk Grading (Phase 7 & 8)
All business logic and DB operations extracted from api/v1/compliance.py.
"""

import random
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.risk_tables import (
    PROFESSION_SCORES,
    PROFESSION_DEFAULT_SCORE,
    BUSINESS_ACTIVITY_SCORES,
    BUSINESS_DEFAULT_SCORE,
    lookup_score,
)
from app.models.base import utcnow
from app.models.compliance import (
    BeneficialOwner,
    EDDDocument,
    EDDRequest,
    PEPIPCheck,
    RiskScore,
    ScreeningResult,
)
from app.models.enums import (
    CDDStatus,
    EDDStatus,
    EDDTriggerReason,
    RiskClassification,
    ScreenResult,
    ScreenType,
)
from app.models.onboarding import CustomerProfile, KYCApplication


class CRUDCompliance:

    # ── Application guard ─────────────────────────────────────────────────────

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

    async def get_customer_profile(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> CustomerProfile:
        result = await db.execute(
            select(CustomerProfile).where(
                CustomerProfile.kyc_application_id == app_id
            )
        )
        profile = result.scalar_one_or_none()
        if not profile:
            raise HTTPException(
                status_code=422,
                detail="Customer profile required before screening",
            )
        return profile

    # ── Risk classification ───────────────────────────────────────────────────

    def classify_risk(self, total_score: int) -> RiskClassification:
        """BFIU section 6.2: total >= 15 = high, >= 8 = medium, else low."""
        if total_score >= settings.HIGH_RISK_SCORE_THRESHOLD:
            return RiskClassification.high
        if total_score >= 8:
            return RiskClassification.medium
        return RiskClassification.low

    # ── Sanctions screening ───────────────────────────────────────────────────

    async def run_all_screenings(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        customer_name: str,
    ) -> list[ScreeningResult]:
        """Run UN sanctions, internal blacklist, adverse media. Simulated — replace with real APIs."""
        screening_sources = [
            (ScreenType.un_sanctions, "UN SCSR", 0.12),
            (ScreenType.internal_blacklist, "BFIU Internal", 0.08),
            (ScreenType.adverse_media, "News API", 0.05),
        ]
        results = []
        for screen_type, source, hit_prob in screening_sources:
            is_hit = random.random() < hit_prob
            match_score = round(random.uniform(0.7, 0.95), 2) if is_hit else None

            sr = ScreeningResult(
                kyc_application_id=app_id,
                screen_type=screen_type.value,
                list_source=source,
                matched_name=customer_name if is_hit else None,
                match_score=match_score,
                result=ScreenResult.potential_match.value if is_hit else ScreenResult.clear.value,
                requires_review=is_hit,
            )
            db.add(sr)
            results.append(sr)
        return results

    async def list_screening_results(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> list[ScreeningResult]:
        result = await db.execute(
            select(ScreeningResult).where(
                ScreeningResult.kyc_application_id == app_id
            )
        )
        return list(result.scalars().all())

    # ── PEP/IP check ──────────────────────────────────────────────────────────

    async def create_pep_ip_check(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        is_pep: bool,
        is_ip: bool,
        is_family_of_pep: bool,
        is_family_of_ip: bool,
        is_high_official_intl_org: bool,
        match_detail: Optional[str],
    ) -> PEPIPCheck:
        edd_required = any([
            is_pep, is_ip, is_family_of_pep,
            is_family_of_ip, is_high_official_intl_org,
        ])
        check = PEPIPCheck(
            kyc_application_id=app_id,
            is_pep=is_pep,
            is_ip=is_ip,
            is_family_of_pep=is_family_of_pep,
            is_family_of_ip=is_family_of_ip,
            is_high_official_intl_org=is_high_official_intl_org,
            match_detail=match_detail,
            edd_required=edd_required,
        )
        db.add(check)
        await db.flush()
        return check

    async def get_pep_ip_check(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> Optional[PEPIPCheck]:
        result = await db.execute(
            select(PEPIPCheck).where(PEPIPCheck.kyc_application_id == app_id)
        )
        return result.scalar_one_or_none()

    # ── Beneficial owners ─────────────────────────────────────────────────────

    async def add_beneficial_owner(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        full_name: str,
        nid_number: Optional[str],
        ownership_percentage: Optional[float],
        is_pep: bool,
        is_ip: bool,
    ) -> BeneficialOwner:
        bo = BeneficialOwner(
            kyc_application_id=app_id,
            full_name=full_name,
            nid_number=nid_number,
            ownership_percentage=ownership_percentage,
            is_pep=is_pep,
            is_ip=is_ip,
            cdd_status=CDDStatus.pending.value,
        )
        db.add(bo)
        await db.flush()
        return bo

    async def list_beneficial_owners(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> list[BeneficialOwner]:
        result = await db.execute(
            select(BeneficialOwner).where(
                BeneficialOwner.kyc_application_id == app_id
            )
        )
        return list(result.scalars().all())

    # ── Risk scoring ──────────────────────────────────────────────────────────

    async def auto_calculate_scores(
        self, db: AsyncSession, app: KYCApplication
    ) -> dict:
        """Derive factor scores from profile and application. BFIU section 6.3."""
        profile_result = await db.execute(
            select(CustomerProfile).where(
                CustomerProfile.kyc_application_id == app.id
            )
        )
        profile = profile_result.scalar_one_or_none()
        pep_check = await self.get_pep_ip_check(db, app.id)

        channel_scores = {
            "self_checkin": 2, "internet": 2, "assisted": 2, "branch": 3,
        }
        score_channel = channel_scores.get(str(app.onboarding_channel), 2)
        score_geo = 3 if (profile and profile.is_nrb) else 1

        score_customer = 0
        if pep_check:
            if pep_check.is_pep or pep_check.is_ip:
                score_customer = 5
            elif pep_check.is_family_of_pep or pep_check.is_family_of_ip:
                score_customer = 5
            else:
                score_customer = 1

        product_scores = {
            "bo_account": 2, "life_insurance": 1, "non_life_insurance": 3,
        }
        score_product = product_scores.get(str(app.product_type), 2)

        investment = float(app.expected_investment or 0)
        if investment < 1_000_000:
            score_txn = 1
        elif investment < 5_000_000:
            score_txn = 2
        elif investment < 50_000_000:
            score_txn = 3
        else:
            score_txn = 5

        score_transparency = 1 if (profile and profile.source_of_fund) else 5

        # BFIU Annexure-1 profession and business activity risk scoring
        score_profession, matched_profession = lookup_score(
            profile.profession if profile else None,
            PROFESSION_SCORES,
            PROFESSION_DEFAULT_SCORE,
        )
        score_business_activity, matched_business = lookup_score(
            profile.business_activity if profile else None,
            BUSINESS_ACTIVITY_SCORES,
            BUSINESS_DEFAULT_SCORE,
        )

        return {
            "score_onboarding_channel": score_channel,
            "score_geography": score_geo,
            "score_customer_type": score_customer,
            "score_product": score_product,
            "score_business_activity": score_business_activity,
            "score_profession": score_profession,
            "score_transaction_volume": score_txn,
            "score_transparency": score_transparency,
            # Diagnostic keys - not persisted in DB, passed through to API response
            "_matched_profession_category": matched_profession,
            "_matched_business_category": matched_business,
        }

    async def get_latest_risk_score(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> Optional[RiskScore]:
        result = await db.execute(
            select(RiskScore)
            .where(RiskScore.kyc_application_id == app_id)
            .order_by(RiskScore.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_risk_score(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        scores: dict,
        pep_check: Optional[PEPIPCheck] = None,
    ) -> RiskScore:
        # Strip diagnostic keys (starting with "_") before DB insert
        db_scores = {k: v for k, v in scores.items() if not k.startswith("_")}

        latest = await self.get_latest_risk_score(db, app_id)
        version = (latest.version + 1) if latest else 1

        total = sum(db_scores.values())
        risk_class = self.classify_risk(total)
        edd_required = (
            risk_class == RiskClassification.high
            or bool(pep_check and pep_check.edd_required)
        )
        rs = RiskScore(
            kyc_application_id=app_id,
            **db_scores,
            total_score=total,
            risk_classification=risk_class.value,
            edd_required=edd_required,
            version=version,
        )
        db.add(rs)
        await db.flush()
        return rs

    # ── EDD ───────────────────────────────────────────────────────────────────

    async def create_edd_request(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        trigger_reason: EDDTriggerReason,
    ) -> EDDRequest:
        risk_score = await self.get_latest_risk_score(db, app_id)
        if not risk_score:
            raise HTTPException(
                status_code=422,
                detail="Risk score must be calculated before EDD request",
            )
        edd = EDDRequest(
            kyc_application_id=app_id,
            risk_score_id=risk_score.id,
            trigger_reason=trigger_reason.value,
            required_documents=(
                '["bank_statement","income_proof","source_of_fund_declaration"]'
            ),
            status=EDDStatus.pending.value,
            deadline_at=utcnow() + timedelta(days=settings.EDD_DEADLINE_DAYS),
        )
        db.add(edd)
        await db.flush()
        return edd

    async def get_latest_edd_request(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> EDDRequest:
        result = await db.execute(
            select(EDDRequest)
            .where(EDDRequest.kyc_application_id == app_id)
            .order_by(EDDRequest.requested_at.desc())
            .limit(1)
        )
        edd = result.scalar_one_or_none()
        if not edd:
            raise HTTPException(status_code=404, detail="No EDD request found")
        return edd

    async def attach_edd_document(
        self,
        db: AsyncSession,
        edd_id: uuid.UUID,
        app_id: uuid.UUID,
        document_type: str,
        storage_key: str,
        checksum_sha256: str,
    ) -> EDDDocument:
        result = await db.execute(
            select(EDDRequest).where(
                EDDRequest.id == edd_id,
                EDDRequest.kyc_application_id == app_id,
            )
        )
        edd = result.scalar_one_or_none()
        if not edd:
            raise HTTPException(status_code=404, detail="EDD request not found")

        doc = EDDDocument(
            edd_request_id=edd_id,
            document_type=document_type,
            storage_key=storage_key,
            checksum_sha256=checksum_sha256,
        )
        db.add(doc)

        if edd.status == EDDStatus.pending.value:
            edd.status = EDDStatus.documents_received.value
            edd.responded_at = utcnow()

        return doc


crud_compliance = CRUDCompliance()
