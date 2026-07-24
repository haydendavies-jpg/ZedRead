"""Unit tests for the Stage 24 product photo dimension check. No database or
Supabase account required — images are generated in memory with Pillow."""

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.services.product_service import (
    _MAX_PHOTO_BYTES,
    _MIN_PHOTO_DIMENSION_PX,
    _validate_photo_dimensions,
)


def _png_bytes(width: int, height: int) -> bytes:
    """Return raw PNG bytes for a solid image of the given dimensions."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


def test_max_photo_bytes_is_500kb():
    """Management Portal tweaks: photo size cap is 500 KB (previously raised to 1 MB at Stage 24)."""
    assert _MAX_PHOTO_BYTES == 500 * 1024


def test_validate_photo_dimensions_accepts_minimum_size():
    """A 500x500 image passes validation without raising."""
    _validate_photo_dimensions(_png_bytes(_MIN_PHOTO_DIMENSION_PX, _MIN_PHOTO_DIMENSION_PX))


def test_validate_photo_dimensions_accepts_larger_image():
    """An image larger than the minimum passes validation."""
    _validate_photo_dimensions(_png_bytes(1000, 800))


def test_validate_photo_dimensions_rejects_too_small_width():
    """An image narrower than 500px raises HTTP 422."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_photo_dimensions(_png_bytes(400, 600))
    assert exc_info.value.status_code == 422


def test_validate_photo_dimensions_rejects_too_small_height():
    """An image shorter than 500px raises HTTP 422."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_photo_dimensions(_png_bytes(600, 400))
    assert exc_info.value.status_code == 422


def test_validate_photo_dimensions_rejects_undecodable_bytes():
    """Bytes that are not a valid image raise HTTP 422, not a 500."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_photo_dimensions(b"not an image")
    assert exc_info.value.status_code == 422
