"""Orchestrates D21's metrics fetch-back: claims one stale/never-fetched
`published` publication and calls `ChannelPublisher.fetch_metrics`
*between* two independent transactions, the same "agent owns the control
flow and the one call that must not happen inside a transaction" shape
`PublishChannelAgent`/`GenerationRenderAgent` established.

Unlike those agents, a failed fetch is **not** routed through anything
resembling `FailPublicationPublish` — `fetch_metrics` is best-effort
telemetry, not a publish attempt, and a transient provider error on one
row must not abort a sweep over the rest. Logged and swallowed;
`StartPublicationMetricsFetch` already bumped `metrics_fetched_at` at
claim time, so the row simply waits out its staleness window before the
next sweep tries again rather than being retried immediately.

`run()` returns `None` when nothing was claimable *or* when the claimed
row's fetch failed — a caller (today, an admin trigger route) cannot
distinguish "empty poll" from "one row failed" from the return value
alone, which is an accepted simplification for a route with no real
caller yet; the `Publication` returned on the success path always has a
newly fetched, current `metrics` value.
"""

from __future__ import annotations

from app.entities.publication import Publication
from app.features.publishing.complete_publication_metrics_fetch import (
    CompletePublicationMetricsFetch,
)
from app.features.publishing.start_publication_metrics_fetch import (
    StartPublicationMetricsFetch,
)
from app.services.ports.channel_publisher import ChannelPublisher
from app.shared.ids import TenantId
from app.shared.logging import get_logger

_logger = get_logger(__name__)


class PublicationMetricsAgent:
    def __init__(
        self,
        start: StartPublicationMetricsFetch,
        complete: CompletePublicationMetricsFetch,
        channel_publisher: ChannelPublisher,
    ) -> None:
        self._start = start
        self._complete = complete
        self._channel_publisher = channel_publisher

    async def run(self, *, tenant_id: TenantId) -> Publication | None:
        ctx = await self._start(tenant_id)
        if ctx is None:
            return None

        try:
            metrics = await self._channel_publisher.fetch_metrics(ctx.external_post_id)
        except Exception:
            _logger.exception(
                "publication_metrics.fetch_failed",
                tenant_id=str(tenant_id),
                publication_id=str(ctx.publication_id),
            )
            return None

        return await self._complete(
            tenant_id=tenant_id, publication_id=ctx.publication_id, metrics=metrics
        )
