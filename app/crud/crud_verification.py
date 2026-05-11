"""
CRUD — Identity Verification (Phase 5)
All business logic and DB operations extracted from api/v1/verification.py.
"""

import json
import re
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.models.enums import (
    BiometricFailureReason,
    BiometricVerificationType,
    DocumentType,
)
from app.models.onboarding import BiometricVerification, KYCApplication, KYCDocument, OCRExtraction
from app.services.ec_service import get_ec_service
from app.services.ocr_service import get_ocr_service

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _normalise_bangla_digits(s: str) -> str:
    return s.translate(_BANGLA_DIGITS)


def _parse_dob(raw: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    normalised = _normalise_bangla_digits(raw.strip())
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(normalised, fmt).date()
        except ValueError:
            continue
    return None


class CRUDVerification:

    # ── Application guard ─────────────────────────────────────────────────────

    async def get_application(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
    ) -> KYCApplication:
        """Get application and verify access for customer or agent actor."""
        result = await db.execute(
            select(KYCApplication).where(KYCApplication.id == app_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        # Check access: either customer (user_id) or agent (agent_id) must match
        if actor_id:
            if app.user_id and app.user_id == actor_id:
                pass  # Customer access OK
            elif app.agent_id and app.agent_id == actor_id:
                pass  # Agent access OK
            else:
                raise HTTPException(status_code=403, detail="Access denied")
        return app

    # ── Retry limit enforcement ───────────────────────────────────────────────

    async def get_attempt_counters(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        verification_type: BiometricVerificationType,
    ) -> tuple[int, int]:
        """
        Returns (next_attempt_number, current_session_number).
        Enforces BFIU limits: 10 attempts/session, 2 sessions/day, 3 total.
        """
        result = await db.execute(
            select(BiometricVerification)
            .where(
                BiometricVerification.kyc_application_id == app_id,
                BiometricVerification.verification_type == verification_type.value,
            )
            .order_by(BiometricVerification.verified_at.desc())
        )
        all_attempts = list(result.scalars().all())

        if not all_attempts:
            return 1, 1

        latest = all_attempts[0]
        current_session = latest.session_number
        attempts_in_session = sum(
            1 for a in all_attempts if a.session_number == current_session
        )

        if current_session >= settings.BIOMETRIC_MAX_TOTAL_SESSIONS and not any(
            a.is_matched for a in all_attempts
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Maximum {settings.BIOMETRIC_MAX_TOTAL_SESSIONS} sessions exhausted. "
                    "Traditional paper KYC must be offered to the customer."
                ),
            )

        if attempts_in_session >= settings.BIOMETRIC_MAX_ATTEMPTS_PER_SESSION:
            if current_session >= settings.BIOMETRIC_MAX_SESSIONS_PER_DAY:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Maximum {settings.BIOMETRIC_MAX_SESSIONS_PER_DAY} sessions "
                        "per day reached. Try again after 24 hours."
                    ),
                )
            return 1, current_session + 1

        return attempts_in_session + 1, current_session

    # ── NID validation ────────────────────────────────────────────────────────

    async def validate_nid(
        self,
        nid_number: str,
        date_of_birth: date,
    ) -> dict:
        """Call mock EC NID API. Raises 400 on mismatch."""
        ec_result = await get_ec_service().validate_nid(nid_number, date_of_birth)
        if not ec_result["matched"]:
            raise HTTPException(
                status_code=400,
                detail=f"NID validation failed: {ec_result.get('reason', 'unknown')}",
            )
        return ec_result

    # ── Face match ────────────────────────────────────────────────────────────

    async def run_face_match(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        nid_number: str,
        selfie_storage_key: str,
        date_of_birth: date,
        ip_address: Optional[str],
        device_info: Optional[str],
    ) -> BiometricVerification:
        attempt_num, session_num = await self.get_attempt_counters(
            db, app_id, BiometricVerificationType.face_match
        )
        ec_result = await get_ec_service().face_match(nid_number, selfie_storage_key)
        is_matched = ec_result["matched"]

        verification = BiometricVerification(
            kyc_application_id=app_id,
            verification_type=BiometricVerificationType.face_match.value,
            nid_number=nid_number,
            dob_provided=date_of_birth,
            similarity_score=ec_result["similarity_score"],
            is_matched=is_matched,
            attempt_number=attempt_num,
            session_number=session_num,
            ip_address=ip_address,
            device_info=device_info,
            mock_api_response=str(ec_result),
            failure_reason=(
                None if is_matched else BiometricFailureReason.low_similarity.value
            ),
        )
        db.add(verification)
        await db.flush()
        return verification

    # ── Fingerprint match ─────────────────────────────────────────────────────

    async def run_fingerprint_match(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        nid_number: str,
        fingerprint_template: str,
        date_of_birth: date,
        finger_position: Optional[str],
        ip_address: Optional[str],
        device_info: Optional[str],
    ) -> tuple[BiometricVerification, bool]:
        """Returns (verification, suggest_face_fallback)."""
        attempt_num, session_num = await self.get_attempt_counters(
            db, app_id, BiometricVerificationType.fingerprint
        )
        ec_result = await get_ec_service().fingerprint_match(
            nid_number, fingerprint_template, finger_position
        )
        is_matched = ec_result["matched"]

        max_fp_result = await db.execute(
            select(func.max(BiometricVerification.session_number)).where(
                BiometricVerification.kyc_application_id == app_id,
                BiometricVerification.verification_type
                == BiometricVerificationType.fingerprint.value,
            )
        )
        max_fp_sessions = max_fp_result.scalar() or 0
        suggest_face_fallback = not is_matched and max_fp_sessions >= 3

        verification = BiometricVerification(
            kyc_application_id=app_id,
            verification_type=BiometricVerificationType.fingerprint.value,
            nid_number=nid_number,
            dob_provided=date_of_birth,
            similarity_score=ec_result["similarity_score"],
            is_matched=is_matched,
            attempt_number=attempt_num,
            session_number=session_num,
            ip_address=ip_address,
            device_info=device_info,
            mock_api_response=str(ec_result),
            failure_reason=(
                None if is_matched else BiometricFailureReason.low_similarity.value
            ),
        )
        db.add(verification)
        await db.flush()
        return verification, suggest_face_fallback

    # ── Verification status ───────────────────────────────────────────────────

    async def get_verification_status(
        self, db: AsyncSession, app_id: uuid.UUID
    ) -> dict:
        result = await db.execute(
            select(BiometricVerification).where(
                BiometricVerification.kyc_application_id == app_id
            )
        )
        attempts = list(result.scalars().all())

        face = [
            a for a in attempts
            if a.verification_type == BiometricVerificationType.face_match.value
        ]
        fp = [
            a for a in attempts
            if a.verification_type == BiometricVerificationType.fingerprint.value
        ]
        max_session = max((a.session_number for a in attempts), default=0)
        face_matched = any(a.is_matched for a in face)
        fp_matched = any(a.is_matched for a in fp)
        is_verified = face_matched or fp_matched

        return {
            "app_id": app_id,
            "total_attempts": len(attempts),
            "successful_attempts": sum(1 for a in attempts if a.is_matched),
            "current_session": max_session,
            "is_verified": is_verified,
            "face_matched": face_matched,
            "fingerprint_matched": fp_matched,
            "nid_validated": True,
            "can_retry": (
                not is_verified
                and max_session < settings.BIOMETRIC_MAX_TOTAL_SESSIONS
            ),
        }

    # ── Documents ─────────────────────────────────────────────────────────────

    async def register_document(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        document_type: DocumentType,
        storage_key: str,
        mime_type: str,
        file_size_bytes: int,
        checksum_sha256: str,
        original_filename: Optional[str] = None,
    ) -> KYCDocument:
        existing = await db.execute(
            select(KYCDocument)
            .where(
                KYCDocument.kyc_application_id == app_id,
                KYCDocument.document_type == document_type.value,
            )
            .order_by(KYCDocument.uploaded_at.desc())
            .limit(1)
        )
        existing_doc = existing.scalar_one_or_none()
        version = (existing_doc.version + 1) if existing_doc else 1

        doc = KYCDocument(
            kyc_application_id=app_id,
            document_type=document_type.value,
            storage_key=storage_key,
            original_filename=original_filename,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            is_encrypted=True,
            version=version,
        )
        db.add(doc)
        await db.flush()
        return doc


    # ── OCR extraction ────────────────────────────────────────────────────────

    async def run_ocr_extraction(
        self,
        db: AsyncSession,
        app_id: uuid.UUID,
        nid_front_key: str,
        nid_back_key: str,
    ) -> OCRExtraction:
        front_result = await db.execute(
            select(KYCDocument)
            .where(
                KYCDocument.kyc_application_id == app_id,
                KYCDocument.document_type == DocumentType.nid_front.value,
            )
            .order_by(KYCDocument.uploaded_at.desc())
            .limit(1)
        )
        front_doc = front_result.scalar_one_or_none()
        if not front_doc:
            raise HTTPException(
                status_code=422,
                detail="NID images must be registered before OCR",
            )

        back_result = await db.execute(
            select(KYCDocument)
            .where(
                KYCDocument.kyc_application_id == app_id,
                KYCDocument.document_type == DocumentType.nid_back.value,
            )
            .order_by(KYCDocument.uploaded_at.desc())
            .limit(1)
        )
        back_doc = back_result.scalar_one_or_none()
        if not back_doc:
            raise HTTPException(
                status_code=422,
                detail="NID images must be registered before OCR",
            )

        attempt_result = await db.execute(
            select(func.max(OCRExtraction.attempt_number)).where(
                OCRExtraction.kyc_application_id == app_id
            )
        )
        next_attempt = (attempt_result.scalar() or 0) + 1

        ocr_data = await get_ocr_service().extract(nid_front_key, nid_back_key)

        raw_json_str = ocr_data.get("raw_json", "{}")
        if len(raw_json_str) > 65_536:
            raw_json_str = raw_json_str[:65_536]

        # Validation gate 1 — confidence threshold
        if (ocr_data.get("confidence_score") or 0) < settings.OCR_CONFIDENCE_THRESHOLD:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"OCR confidence too low "
                    f"({(ocr_data.get('confidence_score') or 0):.0%}). "
                    "Please retake clearer photos of the NID card."
                ),
            )

        # Validation gate 2 — critical field presence (strip whitespace)
        extracted_nid_raw = (ocr_data.get("extracted_nid") or "").strip()
        if not extracted_nid_raw:
            raise HTTPException(
                status_code=422,
                detail="OCR could not extract the NID number. Please retake the NID front photo.",
            )
        if not ocr_data.get("extracted_dob"):
            raise HTTPException(
                status_code=422,
                detail="OCR could not extract the date of birth. Please retake the NID back photo.",
            )

        # Validation gate 3 — NID number format (10, 13, or 17 digits)
        if not re.fullmatch(r"\d{10}|\d{13}|\d{17}", extracted_nid_raw):
            raise HTTPException(
                status_code=422,
                detail="Extracted NID number has an invalid format. Please retake the NID front photo.",
            )

        extracted_dob = _parse_dob(ocr_data.get("extracted_dob") or "") if ocr_data.get("extracted_dob") else None

        ocr = OCRExtraction(
            kyc_application_id=app_id,
            document_id=front_doc.id,
            raw_json=raw_json_str,
            extracted_name_en=ocr_data.get("extracted_name_en"),
            extracted_name_bn=ocr_data.get("extracted_name_bn"),
            extracted_nid=extracted_nid_raw,
            extracted_dob=extracted_dob,
            extracted_address=ocr_data.get("extracted_address"),
            extracted_fathers_name=ocr_data.get("extracted_fathers_name"),
            extracted_mothers_name=ocr_data.get("extracted_mothers_name"),
            confidence_score=ocr_data.get("confidence_score"),
            attempt_number=next_attempt,
            ocr_provider=ocr_data.get("ocr_provider"),
            field_confidence_json=(
                json.dumps(ocr_data["field_confidence"])
                if ocr_data.get("field_confidence") else None
            ),
            quality_flags_json=(
                json.dumps(ocr_data["quality_flags"])
                if ocr_data.get("quality_flags") else None
            ),
        )
        db.add(ocr)
        await db.flush()
        return ocr


crud_verification = CRUDVerification()
