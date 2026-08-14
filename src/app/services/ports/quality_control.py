"""The automated QC gate (D20) every generated image passes through before
either the approval queue or auto-publish ever sees it: "is the expected
subject present, correctly framed, matching the template's composition,"
"does the motif/border match the source photos," colour delta against the
variant's declared colour, artefact detection, and a safety/brand-safety
scan. One port rather than five, since a real provider call (a
multimodal vision model, same shape as `VisionAnalysis`) naturally answers
all five checks from the same image in one round trip — splitting them
into five ports would mean five separate provider calls for one photo.

No real adapter exists — no QC/vision provider credentials are configured
anywhere in this repo, the same deferred-adapter posture as
`VisionAnalysis`/`ImageGeneration`: a fabricated QC verdict is not a
degraded version of a real one, it is a different, dishonest thing that
would let a flawed generated image reach `pending_approval` (or, worse,
auto-publish) on nothing.

`reference_images` (the photographed inputs) and `slot_spec` (the pinned
snapshot's catalog-slot dict — aspect ratio, label; D15 discipline, the
same "read the pinned snapshot, not the live table" rule
`FanOutGenerationItems` follows) are both already-resolved data, not ids —
same "ports name a capability, never fetch their own inputs" reasoning
`ImageGeneration.reference_images` uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class QcVerdict:
    passed: bool
    checks: dict[str, bool]
    reason: str | None


class QualityControl(Protocol):
    async def evaluate(
        self,
        image_bytes: bytes,
        *,
        reference_images: list[bytes],
        slot_spec: dict[str, Any],
        declared_colour: str | None,
    ) -> QcVerdict: ...
