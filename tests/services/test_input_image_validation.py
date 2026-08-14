from __future__ import annotations

import io

from PIL import Image

from app.services.input_image_validation import (
    MAX_ASPECT_RATIO,
    MIN_HEIGHT,
    MIN_WIDTH,
    validate_input_image,
)


def _jpeg_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def _checkerboard(size: int = 800, low: int = 0, high: int = 255, square: int = 20) -> Image.Image:
    # High-contrast alternating squares - plenty of sharp edges, so blur
    # variance comes out well above the threshold. Varying `low`/`high`
    # shifts mean brightness while keeping enough edge contrast to still
    # pass the blur check on its own.
    image = Image.new("L", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            pixels[x, y] = high if (x // square + y // square) % 2 == 0 else low
    return image.convert("RGB")


def test_a_sharp_well_exposed_image_of_sufficient_size_passes() -> None:
    data = _jpeg_bytes(_checkerboard())

    verdict = validate_input_image(data, width=800, height=800)

    assert verdict.passed
    assert verdict.reason is None


def test_an_image_below_the_resolution_floor_is_rejected() -> None:
    data = _jpeg_bytes(_checkerboard(size=MIN_WIDTH - 1))

    verdict = validate_input_image(data, width=MIN_WIDTH - 1, height=MIN_HEIGHT - 1)

    assert not verdict.passed
    assert verdict.reason is not None
    assert "resolution" in verdict.reason.lower()


def test_an_extreme_aspect_ratio_is_rejected() -> None:
    width, height = 2000, MIN_HEIGHT
    assert width / height > MAX_ASPECT_RATIO  # keep the test honest if constants change
    data = _jpeg_bytes(Image.new("RGB", (width, height), color="white"))

    verdict = validate_input_image(data, width=width, height=height)

    assert not verdict.passed
    assert verdict.reason is not None
    assert "aspect ratio" in verdict.reason.lower()


def test_a_flat_image_is_rejected_as_blurry() -> None:
    # A perfectly flat image has no real edge content - what little
    # variance FIND_EDGES reports comes entirely from Pillow's convolution
    # boundary handling (see input_image_validation.py's module docstring),
    # which sits well below the threshold. Confirmed empirically at ~81
    # against a 150 threshold, not assumed.
    data = _jpeg_bytes(Image.new("RGB", (800, 800), color=(128, 128, 128)))

    verdict = validate_input_image(data, width=800, height=800)

    assert not verdict.passed
    assert verdict.reason is not None
    assert "blurry" in verdict.reason.lower()


def test_a_dark_image_is_rejected() -> None:
    data = _jpeg_bytes(_checkerboard(low=0, high=20))

    verdict = validate_input_image(data, width=800, height=800)

    assert not verdict.passed
    assert verdict.reason is not None
    assert "dark" in verdict.reason.lower()


def test_an_overexposed_image_is_rejected() -> None:
    data = _jpeg_bytes(_checkerboard(low=210, high=255))

    verdict = validate_input_image(data, width=800, height=800)

    assert not verdict.passed
    assert verdict.reason is not None
    assert "overexposed" in verdict.reason.lower()
