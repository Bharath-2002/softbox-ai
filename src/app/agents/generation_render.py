"""Orchestrates D18/D19's render step: claims one due
`generation_item.render_requested` job, fetches its reference images and
calls the image-generation provider *between* two independent
transactions, then completes or fails the item — the same "agent owns the
control flow and the one call that must not happen inside a transaction,
not a transaction itself" shape `agents.template_analysis` established
first.

`run()` returns `None` when nothing was claimable (an ordinary empty poll,
not an error) so a caller (an admin trigger route today, a scheduled poller
once one exists) can distinguish "nothing to do right now" from "did work."
"""

from __future__ import annotations

from app.entities.generation_item import GenerationItem
from app.features.generation.complete_generation_item_render import CompleteGenerationItemRender
from app.features.generation.fail_generation_item_render import FailGenerationItemRender
from app.features.generation.start_generation_item_render import StartGenerationItemRender
from app.services.ports.image_generation import ImageGeneration
from app.services.ports.object_storage import ObjectStorage
from app.shared.ids import TenantId


class GenerationRenderAgent:
    def __init__(
        self,
        start: StartGenerationItemRender,
        complete: CompleteGenerationItemRender,
        fail: FailGenerationItemRender,
        object_storage: ObjectStorage,
        image_generation: ImageGeneration,
    ) -> None:
        self._start = start
        self._complete = complete
        self._fail = fail
        self._object_storage = object_storage
        self._image_generation = image_generation

    async def run(self, *, tenant_id: TenantId) -> GenerationItem | None:
        ctx = await self._start(tenant_id=tenant_id)
        if ctx is None:
            return None

        try:
            reference_images = [
                await self._object_storage.read(key) for key in ctx.reference_storage_keys
            ]
            result = await self._image_generation.generate(
                ctx.prompt,
                model=ctx.model,
                seed=ctx.seed,
                params=ctx.model_params,
                reference_images=reference_images,
            )
        except Exception as exc:  # any provider/storage failure is retryable, not fatal
            return await self._fail(
                tenant_id=tenant_id,
                item_id=ctx.item_id,
                job_id=ctx.job_id,
                error_code=type(exc).__name__,
                error_detail=str(exc),
            )

        return await self._complete(
            tenant_id=tenant_id,
            item_id=ctx.item_id,
            job_id=ctx.job_id,
            image_bytes=result.image_bytes,
            cost_micros=result.cost_micros,
            latency_ms=result.latency_ms,
        )
