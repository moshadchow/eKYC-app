import boto3
from botocore.config import Config
from app.core.config import settings

_client = None


def get_storage_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="ap-south-1",
        )
    return _client


def generate_presigned_put(key: str, content_type: str, expires: int = 300) -> str:
    return get_storage_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.STORAGE_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def generate_presigned_get(key: str, expires: int = 300) -> str:
    """Generate a presigned URL for reading an object from S3."""
    return get_storage_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.STORAGE_BUCKET, "Key": key},
        ExpiresIn=expires,
    )
