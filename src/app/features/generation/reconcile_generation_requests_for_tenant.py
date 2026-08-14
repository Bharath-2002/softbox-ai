"""The "due/retryable" half of D19's reconciler for one tenant — the other
half, stuck `task_queue_jobs`, is `features.system.reap_stuck_task_queue_jobs`.
Settles every `running` `GenerationRequest` whose required catalog image
slots have all resolved (`services.generation_request_rollup.compute_rollup`),
transitioning it to `succeeded`/`partially_failed`/`failed` and reconciling
its quota reservation to match.

One transaction for the whole sweep, the same "one tenant, one transaction,
bounded by a limit" shape `RelayOutboxEventsForTenant` established — a
crash mid-sweep must never settle some requests' quota but not their status,
or vice versa. `list_running_for_update` locks the rows it returns
(`SKIP LOCKED`), so a second concurrent sweep for the same tenant picks up
whatever this one didn't reach rather than re-processing the same request.

**Quota split, not a single commit-or-release call**: `commit()`'s own
docstring says "call on success" and `release()`'s says a failed attempt
"does not permanently consume budget it never used" — both read as
per-unit language, not per-request, and the quota metric is literally
`generation.images` (successful image *outputs*, not raw provider calls).
So a `partially_failed` request commits the succeeded slots' quantity
(real images delivered) and releases the failed slots' quantity (budget
that produced nothing) — the two always sum to the slot count reserved at
`CreateGenerationRequest` time, since `compute_rollup` classifies every
required slot as exactly one of succeeded/failed once it returns a status
other than `None`. `succeeded`/`failed` are the same split with one side
at zero. A request created before quota reservation existed (or any
future path that leaves `quota_reservation_id` `None`) skips the quota
calls entirely — nothing was ever reserved to reconcile.

Settling the entity **before** touching quota, both inside the same
transaction: `_mark_terminal` raises on anything but `running`, so if this
method is ever called twice for the same request within one sweep (it
should not be, since `list_running_for_update` only returns each row once
per call), the second attempt fails loudly before double-committing or
double-releasing quota, rather than the quota calls (which are unconditional
`UPDATE`s with no such guard) silently running twice. A settled request is
simply absent from the next sweep's `list_running_for_update` result, so
calling this twice on the same tenant is always safe — the second call
finds nothing left to do for that request, not a raised error.

Before committing or releasing, the reservation row is re-fetched and its
id checked against `request.quota_reservation_id`: `commit`/`release` are
unconditional `UPDATE`s keyed on `(tenant_id, period, metric)`, not on a
reservation id, and both silently match zero rows if the row was deleted
or the period key no longer resolves to what was actually reserved. A
mismatch here means the request's quota accounting can no longer be
trusted — raising loudly is the only alternative to a silent accounting
drift nobody would ever notice.
"""

from __future__ import annotations

from app.entities.generation_request import GenerationRequestStatus
from app.services.generation_request_rollup import compute_rollup
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import TenantId

_QUOTA_METRIC = "generation.images"


class ReconcileGenerationRequestsForTenant:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, tenant_id: TenantId, *, limit: int = 50) -> int:
        now = self._clock.now()
        settled = 0
        async with self._uow_factory(tenant_id) as uow:
            requests = await uow.generation_requests.list_running_for_update(tenant_id, limit=limit)
            for request in requests:
                spec_version = await uow.category_spec_versions.get(
                    tenant_id, request.spec_version_id
                )
                if spec_version is None:
                    raise NotFoundError(
                        "The request's pinned spec version is missing (data inconsistency)."
                    )
                required_slot_ids = [
                    slot["id"]
                    for slot in spec_version.snapshot.get("catalog_image_slots", [])
                    if slot.get("is_required")
                ]
                items = await uow.generation_items.list_for_request(tenant_id, request.id)
                rollup = compute_rollup(required_slot_ids, items)
                if rollup.status is None:
                    continue

                if rollup.status == GenerationRequestStatus.SUCCEEDED:
                    request.mark_succeeded(now=now)
                elif rollup.status == GenerationRequestStatus.PARTIALLY_FAILED:
                    request.mark_partially_failed(now=now)
                elif rollup.status == GenerationRequestStatus.FAILED:
                    request.mark_failed(now=now)
                else:
                    raise NotImplementedError(f"Unhandled rollup status {rollup.status!r}.")
                await uow.generation_requests.update(request)

                if request.quota_reservation_id is not None:
                    period = request.created_at.strftime("%Y-%m")
                    reservation = await uow.quota_reservations.get(
                        tenant_id, period=period, metric=_QUOTA_METRIC
                    )
                    if reservation is None or reservation.id != request.quota_reservation_id:
                        raise NotFoundError(
                            f"Generation request {request.id}'s quota reservation "
                            f"{request.quota_reservation_id} no longer matches the "
                            f"{period!r}/{_QUOTA_METRIC!r} row (data inconsistency)."
                        )
                    if rollup.succeeded_slot_count:
                        await uow.quota_reservations.commit(
                            tenant_id,
                            period=period,
                            metric=_QUOTA_METRIC,
                            quantity=rollup.succeeded_slot_count,
                            now=now,
                        )
                    if rollup.failed_slot_count:
                        await uow.quota_reservations.release(
                            tenant_id,
                            period=period,
                            metric=_QUOTA_METRIC,
                            quantity=rollup.failed_slot_count,
                            now=now,
                        )
                settled += 1
        return settled
