"""
Storage API — Presigned URLs for document retrieval
"""
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import CurrentAgent
from app.core.storage import generate_presigned_get
from app.schemas.common import APIResponse


router = APIRouter()


class PresignedGetResponse(BaseModel):
    url: str
    expires_in: int


@router.get("/presigned-get/{storage_key:path}", response_model=APIResponse[PresignedGetResponse])
async def get_presigned_get_url(
    storage_key: str,
    current_agent: CurrentAgent,
):
    """
    Generate a presigned URL for retrieving a document from object storage.
    Accessible by agents (maker/checker/compliance officer/admin).
    """
    # Validate storage_key to prevent path traversal
    decoded_key = urllib.parse.unquote(storage_key)
    if ".." in decoded_key or decoded_key.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid storage key")

    url = generate_presigned_get(decoded_key)
    return APIResponse(data=PresignedGetResponse(url=url, expires_in=300))