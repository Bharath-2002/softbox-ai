from __future__ import annotations

from app.services.ports.vision_analysis import TemplateAnalysis


class FakeVisionAnalysis:
    """Returns ``next_result`` (or raises ``next_error`` if set) on every
    call. Tests configure whichever behaviour the case under test needs -
    a successful analysis, or a provider failure to drive
    ``mark_analysis_failed``."""

    def __init__(self) -> None:
        self.next_result = TemplateAnalysis(
            analysis={"framing": "flat-lay"},
            prompt_template="A scene with {{input.garment_body}}.",
            model="fake-vision-model",
        )
        self.next_error: Exception | None = None
        self.calls: list[tuple[bytes, str]] = []

    async def analyse_template(self, image_bytes: bytes, *, mime: str) -> TemplateAnalysis:
        self.calls.append((image_bytes, mime))
        if self.next_error is not None:
            raise self.next_error
        return self.next_result
