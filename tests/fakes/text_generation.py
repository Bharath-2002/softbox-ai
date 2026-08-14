from __future__ import annotations

from typing import Any

from app.services.ports.text_generation import GeneratedCopy


class FakeTextGeneration:
    """Returns ``next_result`` (or raises ``next_error`` if set) on every
    call, the same ``next_result``/``next_error``/``calls`` pattern
    ``FakeImageGeneration``/``FakeVisionAnalysis``/``FakeQualityControl``
    use."""

    def __init__(self) -> None:
        self.next_result = GeneratedCopy(
            title="A handwoven classic",
            body="Crafted with care, styled for every occasion.",
            hashtags=["#handwoven", "#saree"],
            cta="Shop now",
            alt_text="A folded saree laid flat against a neutral background.",
            model="fake-text-model",
            cost_micros=0,
            latency_ms=0,
        )
        self.next_error: Exception | None = None
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def generate_copy(
        self, prompt: str, *, model: str, params: dict[str, Any]
    ) -> GeneratedCopy:
        self.calls.append((prompt, model, params))
        if self.next_error is not None:
            raise self.next_error
        return self.next_result
