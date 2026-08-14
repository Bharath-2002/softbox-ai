"""Orchestrates D21's publish step: claims one due
`publication.publish_requested` job and calls `ChannelPublisher` *between*
two independent transactions, then completes, fails or defers the row —
the same "agent owns the control flow and the one call that must not
happen inside a transaction, not a transaction itself" shape
`agents.generation_render` established first.

`RateLimiter.allow()` runs first, keyed on `f"publication:{channel_id}"` —
D21's "per-account distributed rate limiting... a burst of queued publishes
must not attempt to breach it." `RateLimiter`'s own docstring says a rate
check normally runs *before* a use case's own transaction opens (the route-
level `api/deps/rate_limit.py` shape); that does not fit this worker
directly, since which account to check is only known once a job has been
claimed — `StartPublicationPublish`'s own transaction. Checking here,
immediately after `start()` returns and before any provider call, is the
closest equivalent: still strictly before `ChannelPublisher` is ever
touched, just after (not before) the one transaction that has to run first
to learn what to check. `publish_rate_limit_per_account_per_day` (config,
D21: "exact figures get verified against provider docs... not written
here") is the limit; the window is fixed at one day — both will move onto
a real adapter's own `ChannelCapabilities` once one exists, per D21's
"capabilities belong on the adapter" framing.

A rejected rate check is routed through `DeferPublicationPublish`, **not**
`FailPublicationPublish` — a deliberate split, not a stylistic choice. A
rejected `validate()` call and a `publish()` exception both go through
`fail()`, because each is a real failed attempt the bounded-retry ladder
should count. A rate-limit rejection is different: the daily window resets
on a schedule `TaskQueue.fail()`'s backoff (capped at 300s) has no
relationship to, so counting it as an attempt would let a channel at its
cap for the first hour of the day exhaust all five retries within about
fifteen minutes and go `dead`/`FAILED` — losing every publish queued for
the rest of a window that had hours left to run. See
`DeferPublicationPublish`'s own docstring for the full reasoning and
`entities.publication.Publication.defer`'s docstring for why it does not
increment `attempts`.

`run()` returns `None` only when nothing was claimable — an ordinary empty
poll. Every other path returns the `Publication`, matching
`GenerationRenderAgent`'s own shape: a caller (today, an admin trigger
route) always gets the row back when real work happened.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from app.entities.publication import Publication
from app.features.publishing.complete_publication_publish import CompletePublicationPublish
from app.features.publishing.defer_publication_publish import DeferPublicationPublish
from app.features.publishing.fail_publication_publish import FailPublicationPublish
from app.features.publishing.start_publication_publish import StartPublicationPublish
from app.services.ports.channel_publisher import ChannelPublisher, PublishPayload
from app.services.ports.rate_limiter import RateLimiter
from app.shared.clock import Clock, fixed_window_start
from app.shared.ids import AssetId, TenantId

_RATE_LIMIT_WINDOW = timedelta(days=1)


class PublishChannelAgent:
    def __init__(
        self,
        start: StartPublicationPublish,
        complete: CompletePublicationPublish,
        fail: FailPublicationPublish,
        defer: DeferPublicationPublish,
        channel_publisher: ChannelPublisher,
        rate_limiter: RateLimiter,
        clock: Clock,
        *,
        rate_limit_per_account_per_day: int,
    ) -> None:
        self._start = start
        self._complete = complete
        self._fail = fail
        self._defer = defer
        self._channel_publisher = channel_publisher
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._rate_limit = rate_limit_per_account_per_day

    async def run(self, *, tenant_id: TenantId) -> Publication | None:
        ctx = await self._start(tenant_id=tenant_id)
        if ctx is None:
            return None

        now = self._clock.now()
        allowed = await self._rate_limiter.allow(
            tenant_id,
            f"publication:{ctx.channel_id}",
            limit=self._rate_limit,
            window=_RATE_LIMIT_WINDOW,
            now=now,
        )
        if not allowed:
            window_end = fixed_window_start(now, _RATE_LIMIT_WINDOW) + _RATE_LIMIT_WINDOW
            return await self._defer(
                tenant_id=tenant_id,
                publication_id=ctx.publication_id,
                job_id=ctx.job_id,
                reason="Per-account publish rate limit exceeded for the day.",
                run_at=window_end,
            )

        payload = PublishPayload(
            variant_id=ctx.variant_id,
            caption=ctx.payload["caption"],
            media_asset_ids=[AssetId(UUID(a)) for a in ctx.payload["media_asset_ids"]],
            link=ctx.payload.get("link"),
        )

        try:
            validation = await self._channel_publisher.validate(payload)
            if not validation.valid:
                return await self._fail(
                    tenant_id=tenant_id,
                    publication_id=ctx.publication_id,
                    job_id=ctx.job_id,
                    error="; ".join(validation.errors) or "Publish payload failed validation.",
                )
            result = await self._channel_publisher.publish(
                payload, idempotency_key=ctx.idempotency_key
            )
        except Exception as exc:  # any provider failure is retryable, not fatal
            return await self._fail(
                tenant_id=tenant_id,
                publication_id=ctx.publication_id,
                job_id=ctx.job_id,
                error=str(exc),
            )

        return await self._complete(
            tenant_id=tenant_id,
            publication_id=ctx.publication_id,
            job_id=ctx.job_id,
            external_post_id=result.external_post_id,
            permalink=result.permalink,
        )
