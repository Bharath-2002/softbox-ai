"""Template analysis (D14): a vision model looks at an uploaded reference
photo and produces a structured description plus a reusable prompt
template with ``{{...}}`` placeholders.

No real adapter exists — no multimodal vision provider credentials are
configured anywhere in this repo (see CHECKLIST.md's M3 STATE entry).
Unlike ``EmailSender``/``ObjectStorage``, there is no honest local default
to wire into ``bootstrap/app.py`` here: "log instead of sending" and "write
to a local disk instead of a bucket" are both genuinely functional
degraded behaviours, but a fabricated scene analysis is not a degraded
version of a real one — it is a different, dishonest thing that would let
a template reach ``analysed`` on made-up data. ``api/deps/vision_analysis.py``
raises ``UnavailableError`` (503) when nothing is configured rather than
falling back to any adapter, honest or otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class TemplateAnalysis:
    analysis: dict[str, Any]
    prompt_template: str
    model: str


class VisionAnalysis(Protocol):
    async def analyse_template(self, image_bytes: bytes, *, mime: str) -> TemplateAnalysis: ...
