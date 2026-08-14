from __future__ import annotations

from typing import Any

from app.services.ports.quality_control import QcVerdict

_PASSING_CHECKS = {
    "subject_present": True,
    "framing": True,
    "motif_fidelity": True,
    "colour_delta": True,
    "artefacts": True,
    "brand_safety": True,
}


class FakeQualityControl:
    """Returns ``next_result`` (or raises ``next_error`` if set) on every
    call, the same ``next_result``/``next_error``/``calls`` pattern
    ``FakeImageGeneration``/``FakeVisionAnalysis`` use. Defaults to a
    passing verdict on every check."""

    def __init__(self) -> None:
        self.next_result = QcVerdict(passed=True, checks=dict(_PASSING_CHECKS), reason=None)
        self.next_error: Exception | None = None
        self.calls: list[tuple[bytes, int, str | None]] = []

    async def evaluate(
        self,
        image_bytes: bytes,
        *,
        reference_images: list[bytes],
        slot_spec: dict[str, Any],
        declared_colour: str | None,
    ) -> QcVerdict:
        self.calls.append((image_bytes, len(reference_images), declared_colour))
        if self.next_error is not None:
            raise self.next_error
        return self.next_result
