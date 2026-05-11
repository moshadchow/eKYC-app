"""Phase 5 — Identity Verification (API layer only)"""
import json
import uuid
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import CurrentActor, DBSession
from app.core.storage import generate_presigned_put
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


ALLOWED_SELFIE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_NID_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_NID_SIDES = {"front", "back"}


class SelfieUploadUrlResponse(BaseModel):
    upload_url: str
    storage_key: str
    expires_in: int = 300


class NIDUploadUrlResponse(BaseModel):
    upload_url: str
    storage_key: str
    expires_in: int = 300


class NIDOCRRequest(BaseModel):
    nid_front_key: str
    nid_back_key: str


@router.post("/applications/{app_id}/verify/nid", response_model=APIResponse[dict])
async def validate_nid(
    app_id: uuid.UUID, body: NIDVerifyRequest, request: Request,
    actor: CurrentActor, db: DBSession,
    image_uploaded: bool = False,
):
    """Phase 5: Validate NID + DOB against EC database. Returns fields for auto-fill."""
    await crud_verification.get_application(db, app_id, actor.id)
    ec_result = await crud_verification.validate_nid(body.nid_number, body.date_of_birth)
    actor_type = ActorType.customer if actor.is_customer else ActorType.agent
    await record_event(
        db, actor_id=str(actor.id), actor_type=actor_type,
        action=AuditAction.biometric_attempt, entity_type="kyc_applications", entity_id=str(app_id),
        new_value={"nid_validated": True, "nid_number": body.nid_number, "nid_image_captured": image_uploaded},
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
    actor: CurrentActor, db: DBSession,
):
    """Phase 5: Face matching. Max 10 attempts/session, 2 sessions/day, 3 total (BFIU)."""
    await crud_verification.get_application(db, app_id, actor.id)
    ip = request.client.host if request.client else None
    verification = await crud_verification.run_face_match(
        db, app_id, body.nid_number, body.selfie_storage_key,
        body.date_of_birth, ip, request.headers.get("user-agent"),
    )
    actor_type = ActorType.customer if actor.is_customer else ActorType.agent
    await record_event(
        db, actor_id=str(actor.id), actor_type=actor_type,
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


@router.get("/applications/{app_id}/selfie-upload-url", response_model=APIResponse[SelfieUploadUrlResponse])
async def get_selfie_upload_url(
    app_id: uuid.UUID,
    actor: CurrentActor,
    db: DBSession,
    content_type: str = "image/jpeg",
):
    """Generate a presigned PUT URL for direct selfie upload to object storage."""
    if content_type not in ALLOWED_SELFIE_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail=f"content_type must be one of {ALLOWED_SELFIE_CONTENT_TYPES}")
    await crud_verification.get_application(db, app_id, actor.id)
    key = f"selfies/{app_id}/{uuid4()}.jpg"
    url = generate_presigned_put(key, content_type, expires=300)
    return APIResponse(data=SelfieUploadUrlResponse(upload_url=url, storage_key=key))


@router.get("/applications/{app_id}/nid-upload-url", response_model=APIResponse[NIDUploadUrlResponse])
async def get_nid_upload_url(
    app_id: uuid.UUID,
    actor: CurrentActor,
    db: DBSession,
    side: str = "front",
    content_type: str = "image/jpeg",
    file_size_bytes: int = 0,
):
    """Generate a presigned PUT URL for direct NID front/back image upload to object storage."""
    if side not in ALLOWED_NID_SIDES:
        raise HTTPException(status_code=422, detail=f"side must be one of {ALLOWED_NID_SIDES}")
    if content_type not in ALLOWED_NID_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail=f"content_type must be one of {ALLOWED_NID_CONTENT_TYPES}")
    if file_size_bytes > 10_000_000:
        raise HTTPException(status_code=422, detail="File exceeds the 10 MB size limit.")
    await crud_verification.get_application(db, app_id, actor.id)
    key = f"nid/{app_id}/{side}/{uuid4()}.jpg"
    url = generate_presigned_put(key, content_type, expires=300)
    return APIResponse(data=NIDUploadUrlResponse(upload_url=url, storage_key=key))


@router.post("/applications/{app_id}/ocr/nid", response_model=APIResponse[dict])
async def run_nid_ocr(
    app_id: uuid.UUID, body: NIDOCRRequest, request: Request,
    actor: CurrentActor, db: DBSession,
):
    """Phase 5: Run OCR extraction on uploaded NID front/back images."""
    await crud_verification.get_application(db, app_id, actor.id)
    actor_type = ActorType.customer if actor.is_customer else ActorType.agent
    try:
        result = await crud_verification.run_ocr_extraction(
            db, app_id, body.nid_front_key, body.nid_back_key
        )
    except HTTPException as exc:
        await record_event(
            db, actor_id=str(actor.id), actor_type=actor_type,
            action=AuditAction.failed, entity_type="ocr_extractions",
            entity_id=str(app_id),
            new_value={"nid_image_captured": True, "reason": exc.detail},
            ip_address=request.client.host if request.client else None,
        )
        raise
    await record_event(
        db, actor_id=str(actor.id), actor_type=actor_type,
        action=AuditAction.create, entity_type="ocr_extractions", entity_id=str(result.id),
        new_value={"nid_image_captured": True, "confidence": result.confidence_score, "ocr_provider": result.ocr_provider},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(
        message="OCR extraction complete",
        data={
            "id": str(result.id),
            "kyc_application_id": str(result.kyc_application_id),
            "document_id": str(result.document_id),
            "extracted_name_en": result.extracted_name_en,
            "extracted_name_bn": result.extracted_name_bn,
            "extracted_nid": result.extracted_nid,
            "extracted_dob": result.extracted_dob.isoformat() if result.extracted_dob else None,
            "extracted_address": result.extracted_address,
            "extracted_fathers_name": result.extracted_fathers_name,
            "extracted_mothers_name": result.extracted_mothers_name,
            "confidence_score": result.confidence_score,
            "raw_json": result.raw_json,
            "created_at": result.created_at.isoformat(),
            "attempt_number": result.attempt_number,
            "ocr_provider": result.ocr_provider,
            "field_confidence": (
                json.loads(result.field_confidence_json)
                if result.field_confidence_json else None
            ),
            "quality_flags": (
                json.loads(result.quality_flags_json)
                if result.quality_flags_json else None
            ),
        },
    )


@router.post("/applications/{app_id}/verify/fingerprint", response_model=APIResponse[dict])
async def verify_fingerprint(
    app_id: uuid.UUID, body: FingerprintMatchRequest, request: Request,
    actor: CurrentActor, db: DBSession,
):
    """Phase 4 (Assisted only): Fingerprint match. Falls back to face after 3 failed sessions."""
    await crud_verification.get_application(db, app_id, actor.id)
    ip = request.client.host if request.client else None
    verification, suggest_fallback = await crud_verification.run_fingerprint_match(
        db, app_id, body.nid_number, body.fingerprint_template,
        body.date_of_birth, body.finger_position, ip, request.headers.get("user-agent"),
    )
    actor_type = ActorType.customer if actor.is_customer else ActorType.agent
    await record_event(
        db, actor_id=str(actor.id), actor_type=actor_type,
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
    app_id: uuid.UUID, actor: CurrentActor, db: DBSession,
):
    """Get biometric verification status for an application."""
    await crud_verification.get_application(db, app_id, actor.id)
    status = await crud_verification.get_verification_status(db, app_id)
    return APIResponse(data=status)


@router.post("/applications/{app_id}/documents/upload", response_model=APIResponse[dict])
async def register_document(
    app_id: uuid.UUID, body: DocumentUploadRequest, request: Request,
    actor: CurrentActor, db: DBSession,
):
    """Phase 5: Register document metadata after binary upload via presigned URL."""
    await crud_verification.get_application(db, app_id, actor.id)
    doc = await crud_verification.register_document(
        db, app_id, body.document_type, body.storage_key,
        body.mime_type, body.file_size_bytes, body.checksum_sha256,
        body.original_filename,
    )
    actor_type = ActorType.customer if actor.is_customer else ActorType.agent
    await record_event(
        db, actor_id=str(actor.id), actor_type=actor_type,
        action=AuditAction.create, entity_type="kyc_documents", entity_id=str(doc.id),
        new_value={"document_type": body.document_type.value, "version": doc.version},
        ip_address=request.client.host if request.client else None,
    )
    return APIResponse(message="Document registered", data={"document_id": str(doc.id), "version": doc.version})
