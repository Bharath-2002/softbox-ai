"""The immutable per-attempt record (D18): one row per attempt at rendering
one `catalog_image_slot` for one `generation_request`, via one
`catalog_template`. "Immutable" describes the *lineage* facts — which
model, which prompt version, which seed, which template, which reference
images — set once by `create()` and never revised; it does not mean the row
never changes at all, since `status`/`output_asset_id`/`cost_micros`/
`latency_ms`/`error_code`/`error_detail` plainly must move as an attempt
resolves.

`attempt_no` distinguishes two different notions of "retry" that the
`docs/DIAGRAMS.md` state diagram (`generation_item — immutable attempt
log`) keeps separate:

- A **transient provider failure** (network error, rate limit, a 500 from
  the generation API) retries **in place, on the same row** — the diagram's
  own `item_failed -> item_running: backoff + jitter` self-loop. The
  lineage (model, prompt, seed, template) is identical; only the outcome of
  calling the provider *again* with that same lineage differs. This is the
  same attempt, so `attempt_no` does not change, and `TaskQueue`'s own
  `attempts`/backoff (D19) already counts and paces these — `mark_running`
  after `mark_failed` is that same-row cycle, driven by
  `agents.generation_render` re-claiming the same job.
- A **QC-driven retry** (D20: a different seed, or a different template,
  after `qc_failed`) is a genuinely new attempt with different lineage —
  that one creates a **new** row with `attempt_no + 1`. Not built yet
  (blocked on the QC agent), but this is the case the immutable-log framing
  actually protects: a QC retry must never overwrite the row recording what
  the *previous*, rejected attempt actually did.

`create()` starts a row `pending`; `mark_running`/`mark_succeeded`/
`mark_failed`/`mark_dead` (this chunk) are driven by
`agents.generation_render` and its `features.generation.*` use cases — the
worker M5 planned: poll `TaskQueue.claim()`, render the prompt, call
`ImageGeneration`, then write the terminal state.

The input-side fields (`provider`, `model`, `model_params`, `seed`,
`prompt_rendered`, `prompt_version`, `input_asset_ids`) are all knowable
before the provider call is made, so `create()` takes them as required
arguments. The output-side fields (`output_asset_id`, `cost_micros`,
`latency_ms`, `error_code`, `error_detail`) are only knowable after the
attempt resolves, so `create()` always sets them `None` — `mark_succeeded`/
`mark_failed` are what fill them in.

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

from app.shared.errors import ValidationError
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

    def mark_running(self) -> None:
        """`pending -> running` (the first claim) or `failed -> running`
        (the diagram's `backoff + jitter` self-loop — a transient-failure
        retry, same lineage, same row). No `now` parameter: this table has
        no `updated_at` column to stamp — `created_at` is the only
        timestamp, since it describes when the attempt's lineage was fixed,
        not when its status last changed."""
        if self.status not in (GenerationItemStatus.PENDING, GenerationItemStatus.FAILED):
            raise ValidationError(f"Cannot start running from status {self.status.value!r}.")
        self.status = GenerationItemStatus.RUNNING

    def mark_succeeded(
        self, *, output_asset_id: AssetId, cost_micros: int, latency_ms: int
    ) -> None:
        if self.status != GenerationItemStatus.RUNNING:
            raise ValidationError(f"Cannot succeed from status {self.status.value!r}.")
        self.status = GenerationItemStatus.SUCCEEDED
        self.output_asset_id = output_asset_id
        self.cost_micros = cost_micros
        self.latency_ms = latency_ms

    def mark_failed(self, *, error_code: str, error_detail: str) -> None:
        if self.status != GenerationItemStatus.RUNNING:
            raise ValidationError(f"Cannot fail from status {self.status.value!r}.")
        self.status = GenerationItemStatus.FAILED
        self.error_code = error_code
        self.error_detail = error_detail

    def mark_dead(self) -> None:
        """`failed -> dead` — the diagram's "retry budget exhausted" edge,
        driven by `TaskQueue.fail` reporting the underlying job has itself
        gone `dead`. Always follows `mark_failed` in the same transaction,
        never called directly from `running`."""
        if self.status != GenerationItemStatus.FAILED:
            raise ValidationError(f"Cannot deadletter from status {self.status.value!r}.")
        self.status = GenerationItemStatus.DEAD
