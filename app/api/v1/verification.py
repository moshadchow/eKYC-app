"""
Phase 5 — Identity Verification Engine
POST /kyc/applications/{app_id}/verify/nid
POST /kyc/applications/{app_id}/verify/face
POST /kyc/applications/{app_id}/verify/fingerprint
GET  /kyc/applications/{app_id}/verify/status
POST /kyc/applications/{app_id}/documents/upload
"""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import func, select

from ...core.config import settings
from ...core.deps import CurrentAgent, CurrentUser, DBSession
from ...models.base import utcnow
from ...models.enums import (
    ActorType,
    AuditAction,
    BiometricFailureReason,
    BiometricVerificationType,
    DocumentType,
)
from ...models.onboarding import BiometricVerification, KYCApplication, KYCDocument
from ...schemas.common import APIResponse
from ...services.audit import record_event
from ...services.mock_ec import mock_ec_service

router = APIRouter(prefix="/kyc", tags=["Identity Verification"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class NIDVerifyRequest(BaseModel):
    app_id: uuid.UUID
    nid_number: str = Field(..., min_length=10, max_length=20)
    date_of_birth: date


class FaceMatchRequest(BaseModel):
    nid_number: str = Field(..., min_length=10, max_length=20)
    selfie_storage_key: str = Field(..., description="Storage key of the uploaded live selfie")


class FingerprintMatchRequest(BaseModel):
    nid_number: str = Field(..., min_length=10, max_length=20)
    fingerprint_template: str = Field(..., description="Base64-encoded fingerprint template from device SDK")
    finger_position: str | None = Field(None, description="e.g. right_index, left_thumb")
    date_of_birth: date


class DocumentUploadRequest(BaseModel):
    document_type: DocumentType
    storage_key: str = Field(..., description="Object storage key after upload via presigned URL")
    original_filename: str | None = None
    mime_type: str = Field(..., example="image/jpeg")
    file_size_bytes: int
    checksum_sha256: str = Field(..., min_length=64, max_length=64)


class VerificationStatus(BaseModel):
    app_id: uuid.UUID
    total_attempts: int
    successful_attempts: int
    current_session: int
    is_verified: bool
    face_matched: bool
    fingerprint_matched: bool
    nid_validated: bool
    can_retry: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _check_retry_limits(
    db: DBSession,
    app_id: uuid.UUID,
    verification_type: BiometricVerificationType,
) -> tuple[int, int]:
    """
    Returns (current_attempt_in_session, current_session_number).
    Raises 429 if limits exceeded per BFIU guidelines.
    """
    result = await db.execute(
        select(BiometricVerification).where(
            BiometricVerification.kyc_application_id == app_id,
            BiometricVerification.verification_type == verification_type,
        ).order_by(BiometricVerification.verified_at.desc())
    )
    all_attempts = result.scalars().all()

    if not all_attempts:
        return 1, 1

    latest = all_attempts[0]
    current_session = latest.session_number
    attempts_in_session = sum(1 for a in all_attempts if a.session_number == current_session)

    # Max total sessions
    if current_session >= settings.BIOMETRIC_MAX_TOTAL_SESSIONS and not any(
        a.is_matched for a in all_attempts
    ):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Maximum {settings.BIOMETRIC_MAX_TOTAL_SESSIONS} sessions exhausted. "
                "Traditional paper KYC process must be offered to the customer."
            ),
        )

    if attempts_in_session >= settings.BIOMETRIC_MAX_ATTEMPTS_PER_SESSION:
        # Move to next session
        if current_session >= settings.BIOMETRIC_MAX_SESSIONS_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail=f"Maximum {settings.BIOMETRIC_MAX_SESSIONS_PER_DAY} sessions per day reached. Try again after 24 hours.",
            )
        return 1, current_session + 1

    return attempts_in_session + 1, current_session


async def _get_app_for_user_or_agent(
    db: DBSession,
    app_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> KYCApplication:
    result = await db.execute(
        select(KYCApplication).where(KYCApplication.id == app_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if user_id and app.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return app


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/applications/{app_id}/verify/face", response_model=APIResponse[dict])
async def verify_face(
    app_id: uuid.UUID,
    body: FaceMatchRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Phase 5: Face matching against EC NID database.
    Allowed for both self check-in (Phase 3) and assisted onboarding (Phase 4).
    Max 10 attempts/session, 2 sessions/day, 3 sessions total per BFIU.
    """
    app = await _get_app_for_user_or_agent(db, app_id, current_user.id)
    attempt_num, session_num = await _check_retry_limits(
        db, app_id, BiometricVerificationType.face_match
    )

    # Call mock EC face match API
    ec_result = await mock_ec_service.face_match(body.nid_number, body.selfie_storage_key)

    is_matched = ec_result["matched"]
    failure_reason = None if is_matched else BiometricFailureReason.low_similarity

    verification = BiometricVerification(
        kyc_application_id=app_id,
        verification_type=BiometricVerificationType.face_match,
        nid_number=body.nid_number,
        dob_provided=date.today(),  # DOB validated separately via NID check
        similarity_score=ec_result["similarity_score"],
        is_matched=is_matched,
        attempt_number=attempt_num,
        session_number=session_num,
        ip_address=request.client.host if request.client else None,
        device_info=request.headers.get("user-agent"),
        mock_api_response=str(ec_result),
        failure_reason=failure_reason,
    )
    db.add(verification)

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.biometric_success if is_matched else AuditAction.biometric_failure,
        entity_type="biometric_verifications",
        entity_id=str(verification.id),
        new_value={"type": "face_match", "score": ec_result["similarity_score"], "matched": is_matched},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="Face match successful" if is_matched else "Face match failed",
        data={
            "matched": is_matched,
            "similarity_score": ec_result["similarity_score"],
            "threshold": ec_result["threshold"],
            "attempt_number": attempt_num,
            "session_number": session_num,
            "attempts_remaining": settings.BIOMETRIC_MAX_ATTEMPTS_PER_SESSION - attempt_num,
        },
    )


@router.post("/applications/{app_id}/verify/nid", response_model=APIResponse[dict])
async def validate_nid(
    app_id: uuid.UUID,
    body: NIDVerifyRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Phase 5: Validate NID number + DOB against EC database.
    Returns NID record fields for OCR pre-population.
    """
    await _get_app_for_user_or_agent(db, app_id, current_user.id)

    ec_result = await mock_ec_service.validate_nid(body.nid_number, body.date_of_birth)

    if not ec_result["matched"]:
        raise HTTPException(
            status_code=400,
            detail=f"NID validation failed: {ec_result.get('reason', 'unknown')}",
        )

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.biometric_attempt,
        entity_type="kyc_applications",
        entity_id=str(app_id),
        new_value={"nid_validated": True, "nid_number": body.nid_number},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="NID validated successfully",
        data={
            "nid_number": ec_result["nid_number"],
            "full_name_en": ec_result["full_name_en"],
            "full_name_bn": ec_result["full_name_bn"],
            "fathers_name_en": ec_result["fathers_name_en"],
            "fathers_name_bn": ec_result["fathers_name_bn"],
            "mothers_name_en": ec_result["mothers_name_en"],
            "mothers_name_bn": ec_result["mothers_name_bn"],
            "date_of_birth": ec_result["date_of_birth"],
            "gender": ec_result["gender"],
            "present_address": ec_result["present_address"],
        },
    )


@router.post("/applications/{app_id}/verify/fingerprint", response_model=APIResponse[dict])
async def verify_fingerprint(
    app_id: uuid.UUID,
    body: FingerprintMatchRequest,
    request: Request,
    current_agent: CurrentAgent,
    db: DBSession,
):
    """
    Phase 4 (Assisted only): Fingerprint match against EC NID database.
    Only available via agent-assisted channel.
    If fails 3 consecutive sessions → must fall back to face match.
    """
    app = await _get_app_for_user_or_agent(db, app_id)
    attempt_num, session_num = await _check_retry_limits(
        db, app_id, BiometricVerificationType.fingerprint
    )

    ec_result = await mock_ec_service.fingerprint_match(
        body.nid_number, body.fingerprint_template, body.finger_position
    )

    is_matched = ec_result["matched"]

    # Check if we need to suggest face match fallback
    fp_sessions = await db.execute(
        select(func.max(BiometricVerification.session_number)).where(
            BiometricVerification.kyc_application_id == app_id,
            BiometricVerification.verification_type == BiometricVerificationType.fingerprint,
        )
    )
    max_fp_sessions = fp_sessions.scalar() or 0
    suggest_face_fallback = (not is_matched and max_fp_sessions >= 3)

    verification = BiometricVerification(
        kyc_application_id=app_id,
        verification_type=BiometricVerificationType.fingerprint,
        nid_number=body.nid_number,
        dob_provided=body.date_of_birth,
        similarity_score=ec_result["similarity_score"],
        is_matched=is_matched,
        attempt_number=attempt_num,
        session_number=session_num,
        ip_address=request.client.host if request.client else None,
        device_info=request.headers.get("user-agent"),
        mock_api_response=str(ec_result),
        failure_reason=None if is_matched else BiometricFailureReason.low_similarity,
    )
    db.add(verification)

    await record_event(
        db,
        actor_id=str(current_agent.id),
        actor_type=ActorType.agent,
        action=AuditAction.biometric_success if is_matched else AuditAction.biometric_failure,
        entity_type="biometric_verifications",
        entity_id=str(verification.id),
        new_value={"type": "fingerprint", "score": ec_result["similarity_score"], "matched": is_matched},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="Fingerprint match successful" if is_matched else "Fingerprint match failed",
        data={
            "matched": is_matched,
            "similarity_score": ec_result["similarity_score"],
            "attempt_number": attempt_num,
            "session_number": session_num,
            "suggest_face_fallback": suggest_face_fallback,
            "fallback_message": "3 fingerprint sessions failed. Please proceed with face matching." if suggest_face_fallback else None,
        },
    )


@router.get("/applications/{app_id}/verify/status", response_model=APIResponse[VerificationStatus])
async def get_verification_status(
    app_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get biometric verification status for an application."""
    await _get_app_for_user_or_agent(db, app_id, current_user.id)

    result = await db.execute(
        select(BiometricVerification).where(
            BiometricVerification.kyc_application_id == app_id
        )
    )
    attempts = result.scalars().all()

    face_attempts = [a for a in attempts if a.verification_type == BiometricVerificationType.face_match]
    fp_attempts = [a for a in attempts if a.verification_type == BiometricVerificationType.fingerprint]
    max_session = max((a.session_number for a in attempts), default=0)

    face_matched = any(a.is_matched for a in face_attempts)
    fp_matched = any(a.is_matched for a in fp_attempts)
    is_verified = face_matched or fp_matched

    can_retry = (
        not is_verified
        and max_session < settings.BIOMETRIC_MAX_TOTAL_SESSIONS
    )

    return APIResponse(
        data=VerificationStatus(
            app_id=app_id,
            total_attempts=len(attempts),
            successful_attempts=sum(1 for a in attempts if a.is_matched),
            current_session=max_session,
            is_verified=is_verified,
            face_matched=face_matched,
            fingerprint_matched=fp_matched,
            nid_validated=True,
            can_retry=can_retry,
        )
    )


@router.post("/applications/{app_id}/documents/upload", response_model=APIResponse[dict])
async def register_document(
    app_id: uuid.UUID,
    body: DocumentUploadRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Phase 5: Register an uploaded document after it has been stored via presigned URL.
    Stores metadata (storage key, checksum, type) — actual binary stored in object storage.
    """
    await _get_app_for_user_or_agent(db, app_id, current_user.id)

    # Check existing version
    existing = await db.execute(
        select(KYCDocument).where(
            KYCDocument.kyc_application_id == app_id,
            KYCDocument.document_type == body.document_type,
        ).order_by(KYCDocument.uploaded_at.desc()).limit(1)
    )
    existing_doc = existing.scalar_one_or_none()
    version = (existing_doc.version + 1) if existing_doc else 1

    doc = KYCDocument(
        kyc_application_id=app_id,
        document_type=body.document_type,
        storage_key=body.storage_key,
        original_filename=body.original_filename,
        mime_type=body.mime_type,
        file_size_bytes=body.file_size_bytes,
        checksum_sha256=body.checksum_sha256,
        is_encrypted=True,
        version=version,
    )
    db.add(doc)
    await db.flush()

    await record_event(
        db,
        actor_id=str(current_user.id),
        actor_type=ActorType.customer,
        action=AuditAction.create,
        entity_type="kyc_documents",
        entity_id=str(doc.id),
        new_value={"document_type": body.document_type, "version": version},
        ip_address=request.client.host if request.client else None,
    )

    return APIResponse(
        message="Document registered",
        data={"document_id": str(doc.id), "version": version},
    )
