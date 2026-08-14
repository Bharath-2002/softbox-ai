"""Orchestrates D21's publish step: claims one due
`publication.publish_requested` job and calls `ChannelPublisher` *between*
two independent transactions, then completes or fails the row — the same
"agent owns the control flow and the one call that must not happen inside
a transaction, not a transaction itself" shape `agents.generation_render`
established first.

`validate()` runs before `publish()`, in the same try block: a rejected
payload is exactly as much "this attempt failed" as a provider error is,
and routing it through `FailPublicationPublish` gets it the same
retry-vs-dead bookkeeping rather than a special case.

`run()` returns `None` only when nothing was claimable — an ordinary empty
poll. Both the success and failure paths return the `Publication`,
matching `GenerationRenderAgent`'s own shape: a caller (today, an admin
trigger route) always gets the row back when real work happened.
"""

from __future__ import annotations

from uuid import UUID

from app.entities.publication import Publication
from app.features.publishing.complete_publication_publish import CompletePublicationPublish
from app.features.publishing.fail_publication_publish import FailPublicationPublish
from app.features.publishing.start_publication_publish import StartPublicationPublish
from app.services.ports.channel_publisher import ChannelPublisher, PublishPayload
from app.shared.ids import AssetId, TenantId


class PublishChannelAgent:
    def __init__(
        self,
        start: StartPublicationPublish,
        complete: CompletePublicationPublish,
        fail: FailPublicationPublish,
        channel_publisher: ChannelPublisher,
    ) -> None:
        self._start = start
        self._complete = complete
        self._fail = fail
        self._channel_publisher = channel_publisher

    async def run(self, *, tenant_id: TenantId) -> Publication | None:
        ctx = await self._start(tenant_id=tenant_id)
        if ctx is None:
            return None

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
