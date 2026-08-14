"""Copy generation (D23): a text model produces per-channel, per-locale
marketing copy for a product variant — title, body, hashtags, CTA, and
image alt text — read directly into `content_drafts`' own columns, the
same "port returns exactly what the caller needs, already structured"
shape `VisionAnalysis.analyse_template`/`QualityControl.evaluate` use. A
port that returned a raw string would just move JSON-parsing into every
future caller that touches copy.

No real adapter exists — no text-generation provider credentials are
configured anywhere in this repo, the same deferred-adapter posture as
every other LLM-backed port this session (`VisionAnalysis`,
`ImageGeneration`, `QualityControl`): a fabricated title or care
instruction is not a degraded version of a real one, it is fabricated
brand content a tenant's customer would read as fact — the exact
consumer-protection risk D23 names as the reason copy needs the same
approval gate and a forbidden-claims validation pass as imagery.

`prompt` is the already-rendered instruction — channel voice, locale, the
product's attributes and approved imagery baked in by the copywriting
agent that calls this port. The port itself knows nothing about channels,
locales, or brand voice, matching the "ports name a capability, never
fetch or shape their own inputs" rule `ImageGeneration.reference_images`
and `QualityControl.slot_spec` already follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GeneratedCopy:
    title: str | None
    body: str
    hashtags: list[str]
    cta: str | None
    alt_text: str
    model: str
    cost_micros: int
    latency_ms: int


class TextGeneration(Protocol):
    async def generate_copy(
        self, prompt: str, *, model: str, params: dict[str, Any]
    ) -> GeneratedCopy: ...
