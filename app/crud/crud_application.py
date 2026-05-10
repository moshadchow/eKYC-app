"""
CRUD — KYC Applications (Phase 3 & 4)
All business logic and DB operations extracted from api/v1/applications.py.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.security import generate_application_ref, hash_password
from app.models.base import utcnow
from app.models.enums import (
    ApplicationStatus,
    KYCType,
    NomineeRelation,
    OnboardingChannel,
    ProductType,
    ResidencyStatus,
    SignatureType,
    SourceOfFund,
)
from app.models.identity import User
from app.models.onboarding import (
    BiometricVerification,
    CustomerProfile,
    DigitalSignature,
    KYCApplication,
    Nominee,
)


class CRUDApplication:

    # ── KYC Application ───────────────────────────────────────────────────────

    async def create(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        kyc_type: KYCType,
        onboarding_channel: OnboardingChannel,
        product_type: ProductType,
        product_code: Optional[str] = None,
        expected_investment: Optional[Decimal] = None,
        agent_id: Optional[uuid.UUID] = None,
    ) -> KYCApplication:
        app = KYCApplication(
            user_id=user_id,
            agent_id=agent_id,
            kyc_type=kyc_type.value,
            onboarding_channel=onboarding_channel.value,
            product_type=product_type.value,
            product_code=product_code,
            expected_investment=expected_investment,
            status=ApplicationStatus.draft.value,
            application_ref=generate_application_ref(),
        )
        db.add(app)
        await db.flush()
        return app

    async def get_by_id(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> KYCApplication:
        query = select(KYCApplication).where(KYCApplication.id == app_id)
        if user_id:
            query = query.where(KYCApplication.user_id == user_id)
        result = await db.execute(query)
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        return app

    async def list_by_agent(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        status_filter: Optional[ApplicationStatus] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[KYCApplication]:
        query = select(KYCApplication).where(KYCApplication.agent_id == agent_id)
        if status_filter:
            query = query.where(KYCApplication.status == status_filter.value)
        query = query.order_by(KYCApplication.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def submit(
        self, db: AsyncSession, app: KYCApplication,
        require_signature: bool = True,
    ) -> KYCApplication:
        """Validate pre-conditions and move draft → submitted."""
        if app.status != ApplicationStatus.draft.value:
            raise HTTPException(
                status_code=400,
                detail=f"Only draft applications can be submitted. Current: {app.status}",
            )
        await self._assert_profile_exists(db, app.id)
        await self._assert_biometric_verified(db, app.id)
        if require_signature:
            await self._assert_signature_captured(db, app.id)

        app.status = ApplicationStatus.submitted.value
        app.submitted_at = utcnow()
        await db.flush()

        from app.crud.crud_admin import crud_admin
        await crud_admin.get_or_create_queue_entry(db, app)

        return app

    async def get_customer_by_mobile(
        self, db: AsyncSession, mobile_number: str
    ) -> User:
        result = await db.execute(
            select(User).where(User.mobile_number == mobile_number)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=404,
                detail="Customer not found. Customer must verify mobile first.",
            )
        return user

    # ── Customer Profile ──────────────────────────────────────────────────────

    async def get_profile(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> Optional[CustomerProfile]:
        result = await db.execute(
            select(CustomerProfile).where(
                CustomerProfile.kyc_application_id == app_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert_profile(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
        app_status: str,
        data: dict,
    ) -> CustomerProfile:
        if app_status != ApplicationStatus.draft.value:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot update profile in status: {app_status}",
            )

        profile = await self.get_profile(db, app_id)

        if profile:
            for key, val in data.items():
                setattr(profile, key, val)
        else:
            bio = await self._get_matched_biometric(db, app_id)
            profile = CustomerProfile(
                kyc_application_id=app_id,
                user_id=user_id,
                nid_number=bio.nid_number if bio else "PENDING",
                date_of_birth=bio.dob_provided if bio else date.today(),
                **data,
            )
            db.add(profile)
            await db.flush()

        return profile

    # ── Nominees ──────────────────────────────────────────────────────────────

    async def add_nominee(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        full_name: str,
        relation: NomineeRelation,
        date_of_birth: Optional[date] = None,
        contact_number: Optional[str] = None,
        address: Optional[str] = None,
        photo_storage_key: Optional[str] = None,
        is_minor: bool = False,
        guardian_name: Optional[str] = None,
        guardian_nid: Optional[str] = None,
        guardian_address: Optional[str] = None,
    ) -> Nominee:
        if is_minor and not guardian_name:
            raise HTTPException(
                status_code=422,
                detail="Guardian name is required when nominee is a minor",
            )
        nominee = Nominee(
            kyc_application_id=app_id,
            full_name=full_name,
            relation=relation.value,
            date_of_birth=date_of_birth,
            contact_number=contact_number,
            address=address,
            photo_storage_key=photo_storage_key,
            is_minor=is_minor,
            guardian_name=guardian_name,
            guardian_nid=guardian_nid,
            guardian_address=guardian_address,
        )
        db.add(nominee)
        await db.flush()
        return nominee

    # ── Signature ─────────────────────────────────────────────────────────────

    async def capture_signature(
        self,
        db: AsyncSession,
        app: KYCApplication,
        signature_type: SignatureType,
        storage_key: Optional[str],
        pin: Optional[str],
    ) -> DigitalSignature:
        if signature_type == SignatureType.pin:
            if app.kyc_type != KYCType.simplified.value:
                raise HTTPException(
                    status_code=400,
                    detail="PIN signature only permitted for simplified eKYC accounts",
                )
            if not pin:
                raise HTTPException(
                    status_code=422,
                    detail="PIN is required for PIN signature type",
                )
        if signature_type in (SignatureType.wet, SignatureType.electronic):
            if not storage_key:
                raise HTTPException(
                    status_code=422,
                    detail="storage_key required for wet/electronic signature",
                )
        sig = DigitalSignature(
            kyc_application_id=app.id,
            signature_type=signature_type.value,
            storage_key=storage_key,
            pin_hash=hash_password(pin) if pin else None,
            is_low_risk_pin=(signature_type == SignatureType.pin),
        )
        db.add(sig)
        await db.flush()
        return sig

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_matched_biometric(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> Optional[BiometricVerification]:
        result = await db.execute(
            select(BiometricVerification)
            .where(
                BiometricVerification.kyc_application_id == app_id,
                BiometricVerification.is_matched == True,
            )
            .order_by(BiometricVerification.verified_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _assert_profile_exists(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> None:
        if not await self.get_profile(db, app_id):
            raise HTTPException(
                status_code=422,
                detail="Customer profile not found. Complete profile before submitting.",
            )

    async def _assert_biometric_verified(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> None:
        if not await self._get_matched_biometric(db, app_id):
            raise HTTPException(
                status_code=422,
                detail="Biometric verification required before submission.",
            )

    async def _assert_signature_captured(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> None:
        result = await db.execute(
            select(DigitalSignature).where(
                DigitalSignature.kyc_application_id == app_id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=422,
                detail="Signature or consent required before submission.",
            )


crud_application = CRUDApplication()
