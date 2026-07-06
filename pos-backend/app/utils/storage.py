"""Generic Supabase Storage upload helper, shared by every image-upload
feature (product photos, Group/Brand/Site logos). Factored out of the
original product-photo-only implementation in product_service.py."""

import os
from typing import Any

import structlog
from fastapi import HTTPException, status

log = structlog.get_logger(__name__)

_EXT_BY_CONTENT_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

# Shared limits for Group/Brand/Site logo uploads
ALLOWED_LOGO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_LOGO_BYTES = 1 * 1024 * 1024  # 1 MB

# Process-wide Supabase client, built once on first upload. Creating a client
# performs setup work (config parsing, HTTP session), so rebuilding it on every
# upload — as the original code did — wasted work on the request hot path.
_storage_client: Any | None = None


def _get_storage_client() -> Any:
    """
    Return the process-wide Supabase Storage client, creating it on first use.

    The client is cached in a module global so it is built once rather than on
    every upload. It is created lazily (not at import) so importing this module
    never requires Supabase credentials — only an actual upload does. The client
    is only cached after a successful build, so a request that arrives before
    storage is configured raises 503 without poisoning the cache.

    Returns:
        The initialised Supabase client.

    Raises:
        HTTPException: 503 if SUPABASE_URL / SUPABASE_STORAGE_KEY are not set.
    """
    global _storage_client
    if _storage_client is not None:
        return _storage_client

    # Imported lazily so module import never pulls in the Supabase SDK / creds
    from supabase import create_client

    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_STORAGE_KEY", "")
    if not url or not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image storage is not configured",
        )

    _storage_client = create_client(url, key)
    return _storage_client


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

    # Reuse the process-wide client instead of rebuilding it per upload
    client = _get_storage_client()
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
