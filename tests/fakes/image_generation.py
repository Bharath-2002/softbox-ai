from __future__ import annotations

from typing import Any

from app.services.ports.image_generation import GeneratedImage

_FAKE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01"
    b"\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeImageGeneration:
    """Returns ``next_result`` (or raises ``next_error`` if set) on every
    call. Tests configure whichever behaviour the case under test needs -
    a successful generation, or a provider failure to drive the retry/dead
    path."""

    def __init__(self) -> None:
        self.next_result = GeneratedImage(
            image_bytes=_FAKE_PNG_BYTES, mime="image/png", cost_micros=1_000, latency_ms=250
        )
        self.next_error: Exception | None = None
        self.calls: list[tuple[str, str, int, dict[str, Any], int]] = []

    async def generate(
        self,
        prompt: str,
        *,
        model: str,
        seed: int,
        params: dict[str, Any],
        reference_images: list[bytes],
    ) -> GeneratedImage:
        self.calls.append((prompt, model, seed, params, len(reference_images)))
        if self.next_error is not None:
            raise self.next_error
        return self.next_result
