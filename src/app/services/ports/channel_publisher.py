"""D21 — publishing to an external channel behind one Protocol. No real
adapter exists in this repo — no Pinterest/Instagram/Facebook app
credentials are configured anywhere, the same deferred-adapter posture as
`VisionAnalysis`/`ImageGeneration`/`QualityControl`/`TextGeneration`.

D21's own text: "On retry, the adapter first queries the provider for a
post carrying that key... before re-attempting." Read literally, that is
**not a fifth port method** — it means `publish()` itself must be
idempotent on `idempotency_key`: calling it twice with the same key must
never create two posts on the provider side. The use case layer's only
job is committing the key before the first call; every adapter (including
this port's fake) carries the re-query obligation internally, invisible to
callers. This is the single highest-consequence design decision behind
`publications`' Gate property, which is why `capabilities`/`validate`/
`publish`/`fetch_metrics` match D21's own sketch with nothing added.

`PublishPayload`/`PublishResult`/`ChannelMetrics` are deliberately minimal
and provider-agnostic — D21 itself: "provider specifics are deliberately
not written here." A real adapter's own `capabilities` is where exact
caption-length limits, aspect ratios, and media counts get encoded, once
one exists to encode them against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.shared.ids import AssetId, ProductVariantId


@dataclass(frozen=True)
class ChannelCapabilities:
    max_media: int
    max_caption_length: int
    supports_video: bool


@dataclass(frozen=True)
class PublishPayload:
    variant_id: ProductVariantId
    caption: str
    media_asset_ids: list[AssetId]
    link: str | None


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]


@dataclass(frozen=True)
class PublishResult:
    external_post_id: str
    permalink: str | None


@dataclass(frozen=True)
class ChannelMetrics:
    impressions: int | None
    likes: int | None
    clicks: int | None


class ChannelPublisher(Protocol):
    @property
    def capabilities(self) -> ChannelCapabilities: ...

    async def validate(self, payload: PublishPayload) -> ValidationResult: ...

    async def publish(self, payload: PublishPayload, *, idempotency_key: str) -> PublishResult: ...

    async def fetch_metrics(self, external_id: str) -> ChannelMetrics: ...
