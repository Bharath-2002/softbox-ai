"""Pure per-slot rollup deciding whether a `running` `GenerationRequest`
(D18) is ready to settle, and into which terminal status — the diagram's
own `running -> succeeded: all items ok` / `-> partially_failed: some items
dead` / `-> failed: all items dead`, read literally as **items**, would be
wrong the moment a slot has been through D20's QC retry ladder: a slot's
first attempt can be `dead` while a later attempt (a new row, per
`entities.generation_item`'s attempt-vs-lineage distinction) `succeeded`,
and the diagram's own "all items" framing must not fail that request for a
`dead` row a later row already superseded. So this rolls up **per required
slot**, not per raw item: a slot counts as succeeded if *any* of its items
reached `GenerationItemStatus.SUCCEEDED` (ever, regardless of attempt
order), counts as failed only once its *latest* attempt reached
`GenerationItemStatus.DEAD` with no succeeded item to date, and otherwise
is still in flight (`pending`/`running`, or `failed` — the transient,
retried-in-place kind, not `dead`).

A required slot with **zero** items (fan-out never created one — e.g. a
crash mid-fan-out) is classified `failed`, not left pending forever:
nothing in this codebase creates a first attempt for a slot after fan-out
has already run, so waiting for one would mean this request never
reconciles. Documented rather than silently assumed, since it is the one
branch here that is a judgment call rather than a direct reading of the
state diagram.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.entities.generation_item import GenerationItem, GenerationItemStatus
from app.entities.generation_request import GenerationRequestStatus


@dataclass(frozen=True)
class RequestRollup:
    status: GenerationRequestStatus | None
    """`None` means at least one required slot is still in flight — the
    request is not ready to settle."""
    succeeded_slot_count: int
    failed_slot_count: int


def compute_rollup(required_slot_ids: list[str], items: list[GenerationItem]) -> RequestRollup:
    if not required_slot_ids:
        # Invariant maintained by `CreateGenerationRequest`, which refuses to
        # create a request with zero required slots — guarded here rather
        # than trusted, so this function never reports a bogus "succeeded"
        # for a request with nothing to roll up.
        return RequestRollup(status=None, succeeded_slot_count=0, failed_slot_count=0)

    by_slot: dict[str, list[GenerationItem]] = defaultdict(list)
    for item in items:
        by_slot[str(item.catalog_image_slot_id)].append(item)

    succeeded = 0
    failed = 0
    for slot_id in required_slot_ids:
        slot_items = by_slot.get(slot_id, [])
        if any(i.status == GenerationItemStatus.SUCCEEDED for i in slot_items):
            succeeded += 1
            continue
        if not slot_items:
            failed += 1
            continue
        latest = max(slot_items, key=lambda i: i.attempt_no)
        if latest.status == GenerationItemStatus.DEAD:
            failed += 1
            continue
        return RequestRollup(status=None, succeeded_slot_count=0, failed_slot_count=0)

    if failed == 0:
        status = GenerationRequestStatus.SUCCEEDED
    elif succeeded == 0:
        status = GenerationRequestStatus.FAILED
    else:
        status = GenerationRequestStatus.PARTIALLY_FAILED
    return RequestRollup(status=status, succeeded_slot_count=succeeded, failed_slot_count=failed)
