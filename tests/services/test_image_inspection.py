from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services.image_inspection import inspect_image
from app.shared.errors import ValidationError


def _png_bytes(*, width: int = 40, height: int = 30) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(*, width: int = 40, height: int = 30) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


def test_a_real_png_is_identified_by_its_own_bytes_not_a_claimed_extension() -> None:
    inspection = inspect_image(_png_bytes(width=64, height=48))

    assert inspection.mime == "image/png"
    assert inspection.width == 64
    assert inspection.height == 48


def test_a_real_jpeg_is_identified_correctly() -> None:
    inspection = inspect_image(_jpeg_bytes())

    assert inspection.mime == "image/jpeg"


def test_a_file_that_lies_about_being_an_image_is_rejected() -> None:
    not_an_image = b"%PDF-1.4\n%this is actually a pdf, not an image\n"

    with pytest.raises(ValidationError, match="not a readable image"):
        inspect_image(not_an_image)


def test_a_truncated_image_is_rejected() -> None:
    truncated = _png_bytes()[:20]

    with pytest.raises(ValidationError):
        inspect_image(truncated)


def test_an_unsupported_but_valid_image_format_is_rejected() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="BMP")

    with pytest.raises(ValidationError, match="Unsupported image format"):
        inspect_image(buf.getvalue())
