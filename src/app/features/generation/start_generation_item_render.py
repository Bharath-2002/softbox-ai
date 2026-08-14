"""Claims the next due `generation_item.render_requested` job (D19: "the
queue executes one step") and hands back everything
`agents.generation_render` needs for the provider call it makes *outside*
this transaction — the prompt, model, seed and params `FanOutGenerationItems`
already composed, plus where each reference image lives (`storage_key`,
read from `input_asset_ids` while a transaction is already open — the same
"look it up now, not a second use case" reasoning `StartTemplateAnalysis`
uses for its own source asset).

Marks the claimed item `running` in the same transaction as the claim, but
only after every reference asset has resolved — a missing asset raises
before the item ever leaves `pending`, so a data inconsistency here never
leaves the item claiming to be `running` with nothing backing it.

Passes `job_type` to `TaskQueue.claim` explicitly: this worker must only
ever claim `generation_item.render_requested` jobs, never whatever else
happens to be oldest-due for the tenant (see `TaskQueue.claim`'s own
docstring for why the filter exists).

Returns `None` when nothing is claimable right now — not an error, the
ordinary "polled and found nothing due" outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import GenerationItemId, TenantId

JOB_TYPE = "generation_item.render_requested"
CLAIMED_BY = "generation-render-worker"


@dataclass(frozen=True)
class GenerationRenderContext:
    job_id: UUID
    item_id: GenerationItemId
    prompt: str
    model: str
    seed: int
    model_params: dict[str, object]
    reference_storage_keys: list[str]


class StartGenerationItemRender:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, tenant_id: TenantId) -> GenerationRenderContext | None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            job = await uow.task_queue.claim(
                tenant_id, claimed_by=CLAIMED_BY, job_type=JOB_TYPE, now=now
            )
            if job is None:
                return None

            item_id = GenerationItemId(UUID(job.payload["generation_item_id"]))
            item = await uow.generation_items.get(tenant_id, item_id)
            if item is None:
                # Data inconsistency, not a retryable provider failure - the
                # row this job pointed at is gone. Dead-letter the job
                # rather than retrying forever against nothing to claim.
                await uow.task_queue.fail(
                    tenant_id, job.id, error=f"generation_item {item_id} not found", now=now
                )
                return None

            reference_storage_keys: list[str] = []
            for asset_id in item.input_asset_ids:
                asset = await uow.assets.get(tenant_id, asset_id)
                if asset is None:
                    raise NotFoundError(f"Reference asset {asset_id} not found.")
                reference_storage_keys.append(asset.storage_key)

            item.mark_running()
            await uow.generation_items.update(item)

            return GenerationRenderContext(
                job_id=job.id,
                item_id=item.id,
                prompt=item.prompt_rendered,
                model=item.model,
                seed=item.seed,
                model_params=item.model_params,
                reference_storage_keys=reference_storage_keys,
            )
