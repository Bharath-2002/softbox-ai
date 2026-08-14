"""The provider call D18's `generation_items` records the outcome of
(D18: "model, prompt version, seed, params, cost, latency on every attempt").

No real adapter exists — no image-generation provider credentials
(Nano Banana 2 or otherwise) are configured anywhere in this repo. Same
deferred-adapter posture as `VisionAnalysis`: "log instead of sending" has
no analogue here — a fabricated generated image is not a degraded version
of a real one, it is a different, dishonest thing that would let a
`generation_item` reach `succeeded` on nothing. `api/deps/image_generation.py`
mirrors `api/deps/vision_analysis.py`'s `UnavailableError`-on-unset shape —
needed now that `agents.generation_render` has an admin trigger route
(`POST .../generation-requests/{id}/render-next`, the same "real
capability, no automatic trigger" posture every other M5 admin route
uses), even though no real adapter is configured anywhere in this repo yet.

`reference_images` is already-fetched bytes, not asset ids — fetching from
`ObjectStorage` is the worker's job (the same "ports name a capability,
never a technology" reason `ProductRepository.get` never takes a
`session`), so this port stays free of any storage-layer concern.

`GeneratedImage.image_bytes` lets the worker verify/register the result the
same way `VerifyAndRegisterUpload` does for a human-uploaded photo — reusing
that pipeline rather than inventing a second "write bytes then create an
Asset row" path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GeneratedImage:
    image_bytes: bytes
    mime: str
    cost_micros: int
    latency_ms: int


class ImageGeneration(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        model: str,
        seed: int,
        params: dict[str, Any],
        reference_images: list[bytes],
    ) -> GeneratedImage: ...
