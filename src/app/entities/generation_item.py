"""The immutable per-attempt record (D18): one row per attempt at rendering
one `catalog_image_slot` for one `generation_request`, via one
`catalog_template`. `attempt_no` distinguishes retries — a retry after
`item_failed` creates a **new** row with `attempt_no + 1` rather than
revising the failed one in place, which is what makes this table an
"immutable lineage record" rather than a mutable status row: which model,
which prompt version, which seed, what it cost and why it failed are facts
about one specific attempt, not a running summary.

Only `create()` lands in this chunk, matching `entities.generation_request`'s
posture: `GenerationItemStatus` names every state
(`pending -> running -> succeeded / failed -> dead`, matching the ERD's
literal `CHECK` text) but the transition methods that would move a row from
`pending` to a terminal status are not built here, since nothing drives them
yet — the worker that would execute a claimed `generation_item` (poll
`TaskQueue.claim()`, render the prompt, call `ImageGeneration`, then write
the terminal state) is still ahead in the M5 sequence.

The input-side fields (`provider`, `model`, `model_params`, `seed`,
`prompt_rendered`, `prompt_version`, `input_asset_ids`) are all knowable
before the provider call is made, so `create()` takes them as required
arguments. The output-side fields (`output_asset_id`, `cost_micros`,
`latency_ms`, `error_code`, `error_detail`) are only knowable after the
attempt resolves, so `create()` always sets them `None` — the future
terminal-state transition method is what fills them in, once, and never
again.

`input_asset_ids` is a Postgres array column (this codebase's first) rather
than a join table: it is a fixed, small, ordered list of asset ids read
once when composing the prompt, not a relation queried or filtered on its
own, so a join table would add write-side complexity (an insert per element,
same-transaction ordering) for zero read-side benefit here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.shared.ids import (
    AssetId,
    CatalogImageSlotId,
    CatalogTemplateId,
    GenerationItemId,
    GenerationRequestId,
    TenantId,
    new_generation_item_id,
)


class GenerationItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class GenerationItem:
    id: GenerationItemId
    tenant_id: TenantId
    request_id: GenerationRequestId
    catalog_image_slot_id: CatalogImageSlotId
    template_id: CatalogTemplateId
    attempt_no: int
    status: GenerationItemStatus
    provider: str
    model: str
    model_params: dict[str, object]
    seed: int
    prompt_rendered: str
    prompt_version: str
    input_asset_ids: list[AssetId]
    output_asset_id: AssetId | None
    cost_micros: int | None
    latency_ms: int | None
    error_code: str | None
    error_detail: str | None
    created_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        request_id: GenerationRequestId,
        catalog_image_slot_id: CatalogImageSlotId,
        template_id: CatalogTemplateId,
        *,
        attempt_no: int,
        provider: str,
        model: str,
        model_params: dict[str, object],
        seed: int,
        prompt_rendered: str,
        prompt_version: str,
        input_asset_ids: list[AssetId],
        now: datetime,
    ) -> GenerationItem:
        return GenerationItem(
            id=new_generation_item_id(),
            tenant_id=tenant_id,
            request_id=request_id,
            catalog_image_slot_id=catalog_image_slot_id,
            template_id=template_id,
            attempt_no=attempt_no,
            status=GenerationItemStatus.PENDING,
            provider=provider,
            model=model,
            model_params=model_params,
            seed=seed,
            prompt_rendered=prompt_rendered,
            prompt_version=prompt_version,
            input_asset_ids=input_asset_ids,
            output_asset_id=None,
            cost_micros=None,
            latency_ms=None,
            error_code=None,
            error_detail=None,
            created_at=now,
        )
