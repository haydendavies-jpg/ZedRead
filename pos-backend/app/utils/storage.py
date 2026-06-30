"""Generic Supabase Storage upload helper, shared by every image-upload
feature (product photos, Group/Brand/Site logos). Factored out of the
original product-photo-only implementation in product_service.py."""

import structlog
from fastapi import HTTPException, status

log = structlog.get_logger(__name__)

_EXT_BY_CONTENT_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

# Shared limits for Group/Brand/Site logo uploads
ALLOWED_LOGO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_LOGO_BYTES = 1 * 1024 * 1024  # 1 MB


async def upload_image(
    bucket: str,
    path: str,
    content_type: str,
    contents: bytes,
    allowed_content_types: set[str],
    max_bytes: int,
) -> str:
    """
    Validate and upload image bytes to a Supabase Storage bucket, returning its public URL.

    Args:
        bucket: Name of the Supabase Storage bucket (e.g. "product-photos", "logos").
        path: Storage path within the bucket (e.g. "groups/{group_id}.jpg").
        content_type: MIME type of the image, as reported by the client.
        contents: Raw image bytes already read from the upload.
        allowed_content_types: Set of MIME types this caller accepts.
        max_bytes: Maximum allowed size in bytes for this caller.

    Returns:
        str: The public URL of the uploaded file.

    Raises:
        HTTPException: 415 if content_type is not in allowed_content_types.
        HTTPException: 413 if contents exceeds max_bytes.
        HTTPException: 503 if Supabase Storage is not configured.
    """
    if content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type '{content_type}'. Accepted: jpeg, png, webp",
        )

    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds {max_bytes} byte limit ({len(contents)} bytes received)",
        )

    import os

    from supabase import create_client

    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_STORAGE_KEY", "")

    if not url or not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image storage is not configured",
        )

    client = create_client(url, key)
    storage_bucket = client.storage.from_(bucket)

    try:
        storage_bucket.upload(
            path=path, file=contents, file_options={"content-type": content_type, "upsert": "true"}
        )
    except Exception:
        log.error("storage.upload_failed", bucket=bucket, path=path, exc_info=True)
        raise

    return storage_bucket.get_public_url(path)


def extension_for_content_type(content_type: str) -> str:
    """
    Return the file extension to use for a given image MIME type, defaulting to 'jpg'.

    Args:
        content_type: MIME type of the image (e.g. "image/png").

    Returns:
        str: The matching extension without a leading dot (e.g. "png").
    """
    return _EXT_BY_CONTENT_TYPE.get(content_type, "jpg")
