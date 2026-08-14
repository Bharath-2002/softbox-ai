"""Sniffs an image's real format and dimensions from its bytes (M3 Gate: "a
file that lies about its extension is rejected"). Deliberately not a
port/adapter pair like ``ObjectStorage`` or ``ContentModerationScanner`` —
Pillow is a plain library dependency with one implementation, not a
credentialed external service with a fake/real split to keep honest.

``Image.load()`` forces Pillow to fully decode the pixel data rather than
just parse the header, which is what actually catches a truncated or
corrupt file — ``Image.open()`` alone is lazy and would let a half-written
upload through undetected.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from app.shared.errors import ValidationError

_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


@dataclass(frozen=True)
class ImageInspection:
    mime: str
    width: int
    height: int


def inspect_image(data: bytes) -> ImageInspection:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            fmt = img.format
            width, height = img.size
    except Exception as exc:
        raise ValidationError("File is not a readable image.") from exc

    mime = _FORMAT_TO_MIME.get(fmt or "")
    if mime is None:
        raise ValidationError(f"Unsupported image format: {fmt!r}.")
    return ImageInspection(mime=mime, width=width, height=height)
