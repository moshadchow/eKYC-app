"""Phase 5 — Identity Verification (API layer only)"""
import uuid
from datetime import date

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import CurrentAgent, CurrentUser, DBSession
from app.crud.crud_verification import crud_verification
from app.models.enums import ActorType, AuditAction, DocumentType
from app.schemas.common import APIResponse
from app.services.audit import record_event

router = APIRouter(prefix="/kyc", tags=["Identity Verification"])


class NIDVerifyRequest(BaseModel):
    nid_number: str = Field(..., min_length=10, max_length=20)
    date_of_birth: date


class FaceMatchRequest(BaseModel):
    nid_number: str = Field(..., min_length=10, max_length=20)
    selfie_storage_key: str = Field(..., description="Storage key of the uploaded live selfie")
    date_of_birth: date


class FingerprintMatchRequest(BaseModel):
    nid_number: str = Field(..., min_length=10, max_length=20)
    fingerprint_template: str = Field(..., description="Base64-encoded fingerprint template")
    finger_position: str | None = Field(None, description="e.g. right_index, left_thumb")
    date_of_birth: date


class DocumentUploadRequest(BaseModel):
    document_type: DocumentType
    storage_key: str = Field(..., description="Object storage key after presigned-URL upload")
    original_filename: str | None = None
    mime_type: str = Field(..., example="image/jpeg")
    file_size_bytes: int
    checksum_sha256: str = Field(..., min_length=64, max_length=64)


@router.post("/applications/{app_id}/verify/nid", response_model=APIResponse[dict])
async def validate_nid(
    app_id: uuid.UUID, body: NIDVerifyRequest, request: Request,
    current_user: CurrentUser, db: DBSession,
):
    """Phase 5: Validate NID + DOB against EC database. Returns fields for auto-fill."""
    await crud_verification.get_application(db, app_id, current_user.id)
    ec_result = await crud_verification.validate_nid(body.nid_number, body.date_of_birth)
    await record_event(
        db, actor_id=str(current_user.id), actor_type=ActorType.customer,
        action=AuditAction.biometric_attempt, entity_type="kyc_applications", entity_id=str(app_id),
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


@router.post("/applications/{app_id}/verify/face", response_model=APIResponse[dict])
async def verify_face(
    app_id: uuid.UUID, body: FaceMatchRequest, request: Request,
    current_user: CurrentUser, db: DBSession,
):
    """Phase 5: Face matching. Max 10 attempts/session, 2 sessions/day, 3 total (BFIU)."""
    await crud_verification.get_application(db, app_id, current_user.id)
    ip = request.client.host if request.client else None
    verification = await crud_verification.run_face_match(
        db, app_id, body.nid_number, body.selfie_storage_key,
        body.date_of_birth, ip, request.headers.get("user-agent"),
    )
    await record_event(
        db, actor_id=str(current_user.id), actor_type=ActorType.customer,
        action=AuditAction.biometric_success if verification.is_matched else AuditAction.biometric_failure,
        entity_type="biometric_verifications", entity_id=str(verification.id),
        new_value={"type": "face_match", "score": verification.similarity_score, "matched": verification.is_matched},
        ip_address=ip,
    )
    return APIResponse(
        message="Face match successful" if verification.is_matched else "Face match failed",
        data={
            "matched": verification.is_matched,
            "similarity_score": verification.similarity_score,
            "attempt_number": verification.attempt_number,
            "session_number": verification.session_number,
            "attempts_remaining": settings.BIOMETRIC_MAX_ATTEMPTS_PER_SESSION - verification.attempt_number,
        },
    )


@router.post("/applications/{app_id}/verify/fingerprint", response_model=APIResponse[dict])
async def verify_fingerprint(
    app_id: uuid.UUID, body: FingerprintMatchRequest, request: Request,
    current_agent: CurrentAgent, db: DBSession,
):
    """Phase 4 (Assisted only): Fingerprint match. Falls back to face after 3 failed sessions."""
    await crud_verification.get_application(db, app_id)
    ip = request.client.host if request.client else None
    verification, suggest_fallback = await crud_verification.run_fingerprint_match(
        db, app_id, body.nid_number, body.fingerprint_template,
        body.date_of_birth, body.finger_position, ip, request.headers.get("user-agent"),
    )
    await record_event(
        db, actor_id=str(current_agent.id), actor_type=ActorType.agent,
        action=AuditAction.biometric_success if verification.is_matched else AuditAction.biometric_failure,
        entity_type="biometric_verifications", entity_id=str(verification.id),
        new_value={"type": "fingerprint", "score": verification.similarity_score, "matched": verification.is_matched},
        ip_address=ip,
    )
    return APIResponse(
        message="Fingerprint match successful" if verification.is_matched else "Fingerprint match failed",
        data={
            "matched": verification.is_matched,
            "similarity_score": verification.similarity_score,
            "attempt_number": verification.attempt_number,
            "session_number": verification.session_number,
            "suggest_face_fallback": suggest_fallback,
            "fallback_message": "3 fingerprint sessions failed. Please proceed with face matching." if suggest_fallback else None,
        },
    )


@router.get("/applications/{app_id}/verify/status", response_model=APIResponse[dict])
async def get_verification_status(
    app_id: uuid.UUID, current_user: CurrentUser, db: DBSession,
):
    """Get biometric verification status for an application."""
    await crud_verification.get_application(db, app_id, current_user.id)
    status = await crud_verification.get_verification_status(db, app_id)
    return APIResponse(data=status)


@router.post("/applications/{app_id}/documents/upload", response_model=APIResponse[dict])
async def register_document(
    app_id: uuid.UUID, body: DocumentUploadRequest, request: Request,
    current_user: CurrentUser, db: DBSession,
):
    """Phase 5: Register document metadata after binary upload via presigned URL."""
    await crud_verification.get_application(db, app_id, current_user.id)
    doc = await crud_verification.register_document(
        db, app_id, body.document_type, body.storage_key,
        body.mime_type, body.file_size_bytes, body.checksum_sha256,
        body.original_filename,
    )
    await record_event(
        db, actor_id=str(current_user.id), actor_type=ActorType.customer,
        action=AuditAction.create, entity_type="kyc_documents", entity_id=str(doc.id),
        new_value={"document_type": body.document_type.value, "version": doc.version},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="Document registered", data={"document_id": str(doc.id), "version": doc.version})
