"""D20's bounded auto-retry: a `qc_failed` catalog image gets a new seed on
the same template first, then a different template, before landing on
`human_review` — pure decision logic, no I/O, the same "pure function, thin
caller" shape `task_backoff.compute_backoff`/`product_readiness.
compute_product_readiness` use.

Ladder position is derived from `max(attempt_no)` over every
`generation_item` already recorded for one `(request_id,
catalog_image_slot_id)` pair — no separate counter column, since
`attempt_no` already means exactly this (see `entities.generation_item`'s
corrected docstring: it counts genuinely new attempts, which is exactly
what a QC-driven retry is). `attempts_for_slot` must already be filtered to
one slot by the caller — a request with more than one required slot has
independent `attempt_no` sequences per slot, and mixing them would corrupt
the `UNIQUE(tenant_id, request_id, catalog_image_slot_id, attempt_no)`
guarantee the next `generation_item` relies on.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.entities.catalog_template import CatalogTemplate, TemplateStatus
from app.entities.generation_item import GenerationItem
from app.shared.ids import CatalogTemplateId


@dataclass(frozen=True)
class RetryRung:
    attempt_no: int
    template_id: CatalogTemplateId
    reuse_prompt: bool
    """True: same template as the failed attempt, so `prompt_rendered` can
    be reused verbatim - only the seed changes. False: a different
    template, whose own `prompt_template` must be recomposed."""


def next_rung(
    attempts_for_slot: list[GenerationItem], alternate_templates: list[CatalogTemplate]
) -> RetryRung | None:
    """`None` means the ladder is exhausted (or was never climbable, e.g. no
    alternate analysed template exists for rung two) - the caller's next
    step is `human_review`, not another attempt."""
    latest = max(attempts_for_slot, key=lambda item: item.attempt_no)

    if latest.attempt_no == 1:
        return RetryRung(
            attempt_no=latest.attempt_no + 1, template_id=latest.template_id, reuse_prompt=True
        )

    if latest.attempt_no == 2:
        candidates = [
            t
            for t in alternate_templates
            if t.id != latest.template_id and t.status == TemplateStatus.ANALYSED
        ]
        if not candidates:
            return None
        return RetryRung(
            attempt_no=latest.attempt_no + 1, template_id=candidates[0].id, reuse_prompt=False
        )

    return None
