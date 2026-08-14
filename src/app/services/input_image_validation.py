"""The §6.1 `validating` step: resolution floor, blur/focus, exposure
range, aspect sanity — genuinely buildable with Pillow alone (already a
dependency via `image_inspection.py`), unlike `normalising`, which needs
`rembg`/OpenCV or a hosted service and was explicitly deferred (asked the
user directly rather than adding a dependency unilaterally — see
`entities.product_input_image`'s module docstring).

Every rejection reason is written to be actionable by the shop assistant
standing in front of the product holding the phone that took the photo
(CLAUDE.md's "the person holding the phone can retake immediately" - §6.1),
never a bare code.

Blur detection uses `ImageFilter.FIND_EDGES` — its 3x3 kernel
(`-1 -1 -1 / -1 8 -1 / -1 -1 -1`) *is* the standard discrete Laplacian, so
the variance of the edge-filtered image is the same variance-of-Laplacian
metric OpenCV's `cv2.Laplacian(...).var()` computes, without needing OpenCV
or numpy: a sharp image has many strong edges and high variance, a blurry
one has few and low variance.

Every threshold below is a conservative starting point, not calibrated
against real product photos — expect to tune these once real tenant uploads
exist to test against. ``MIN_BLUR_VARIANCE`` in particular has an empirical
floor: `ImageFilter.FIND_EDGES` produces a nonzero response along an image's
one-pixel border (Pillow's convolution boundary handling, not real edge
content), which alone yields a variance of roughly 80 on an 800x800 image
even when the interior is perfectly flat. The threshold must sit
meaningfully above that floor to have any discriminating power at all —
confirmed empirically (a solid-colour image measures ~81) before picking
150, not assumed.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageStat

from app.shared.errors import ValidationError

MIN_WIDTH = 600
MIN_HEIGHT = 600
MIN_ASPECT_RATIO = 1 / 3
MAX_ASPECT_RATIO = 3 / 1
MIN_BLUR_VARIANCE = 150.0
MIN_BRIGHTNESS = 25.0
MAX_BRIGHTNESS = 230.0


@dataclass(frozen=True)
class ValidationVerdict:
    passed: bool
    reason: str | None


def validate_input_image(data: bytes, *, width: int, height: int) -> ValidationVerdict:
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return ValidationVerdict(
            passed=False,
            reason=(
                f"Image resolution is too low ({width}x{height}) — "
                f"retake at least {MIN_WIDTH}x{MIN_HEIGHT}."
            ),
        )

    aspect = width / height
    if not (MIN_ASPECT_RATIO <= aspect <= MAX_ASPECT_RATIO):
        return ValidationVerdict(
            passed=False,
            reason="Image aspect ratio is too extreme — retake in a more standard framing.",
        )

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            gray = img.convert("L")
    except Exception as exc:
        raise ValidationError("File is not a readable image.") from exc

    edges = gray.filter(ImageFilter.FIND_EDGES)
    blur_variance = ImageStat.Stat(edges).var[0]
    if blur_variance < MIN_BLUR_VARIANCE:
        return ValidationVerdict(
            passed=False,
            reason="Image is too blurry — retake in better light or hold the camera steady.",
        )

    brightness = ImageStat.Stat(gray).mean[0]
    if brightness < MIN_BRIGHTNESS:
        return ValidationVerdict(passed=False, reason="Image is too dark — retake in better light.")
    if brightness > MAX_BRIGHTNESS:
        return ValidationVerdict(
            passed=False, reason="Image is overexposed — retake with less direct light."
        )

    return ValidationVerdict(passed=True, reason=None)
