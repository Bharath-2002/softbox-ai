"""The run-level row for one "Save & Generate" (D18): one per product
variant, fanning out into many `generation_items` (the immutable attempt
log — see `entities.generation_item`). `spec_version_id` is the pinned
snapshot the request was generated against, the same D15 discipline as
`Product`/`ProductVariant` — a later spec change must never retroactively
alter what an in-flight or historical request meant.

`create()` and `mark_running()` land in this chunk — `mark_running` is
driven by `FanOutGenerationItems`, which moves a request out of `queued`
once it has finished expanding it into `generation_items` and enqueueing
their render jobs, i.e. once real work is actually in flight.

`mark_succeeded`/`mark_partially_failed`/`mark_failed` all funnel through
one private `_mark_terminal`, driven by
`features.generation.reconcile_generation_requests_for_tenant` (the
reconciler's "due/retryable" half — see `services.generation_request_
rollup` for how a `running` request's `generation_items` decide which of
the three it becomes) — every terminal transition sets `completed_at` and
is only legal from `running`, so a second reconcile pass on an
already-settled request raises rather than silently re-transitioning it.
`cancelled` (`queued -> cancelled`, `running -> cancelled`) still has no
caller — cancellation is a human-initiated action with no use case built
yet, unlike the other three which the reconciler drives automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.shared.errors import ValidationError
from app.shared.ids import (
    CategorySpecVersionId,
    GenerationRequestId,
    ProductId,
    ProductVariantId,
    TenantId,
    UserId,
    new_generation_request_id,
)


class GenerationRequestStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GenerationRequest:
    id: GenerationRequestId
    tenant_id: TenantId
    product_id: ProductId
    variant_id: ProductVariantId
    spec_version_id: CategorySpecVersionId
    status: GenerationRequestStatus
    settings_snapshot: dict[str, Any]
    quota_reservation_id: UUID | None
    requested_by: UserId
    created_at: datetime
    completed_at: datetime | None

    @staticmethod
    def create(
        tenant_id: TenantId,
        product_id: ProductId,
        variant_id: ProductVariantId,
        spec_version_id: CategorySpecVersionId,
        *,
        settings_snapshot: dict[str, Any],
        quota_reservation_id: UUID | None,
        requested_by: UserId,
        now: datetime,
    ) -> GenerationRequest:
        return GenerationRequest(
            id=new_generation_request_id(),
            tenant_id=tenant_id,
            product_id=product_id,
            variant_id=variant_id,
            spec_version_id=spec_version_id,
            status=GenerationRequestStatus.QUEUED,
            settings_snapshot=settings_snapshot,
            quota_reservation_id=quota_reservation_id,
            requested_by=requested_by,
            created_at=now,
            completed_at=None,
        )

    def mark_running(self, *, now: datetime) -> None:
        if self.status != GenerationRequestStatus.QUEUED:
            raise ValidationError(f"Cannot start running from status {self.status.value!r}.")
        self.status = GenerationRequestStatus.RUNNING

    def mark_succeeded(self, *, now: datetime) -> None:
        self._mark_terminal(GenerationRequestStatus.SUCCEEDED, now=now)

    def mark_partially_failed(self, *, now: datetime) -> None:
        self._mark_terminal(GenerationRequestStatus.PARTIALLY_FAILED, now=now)

    def mark_failed(self, *, now: datetime) -> None:
        self._mark_terminal(GenerationRequestStatus.FAILED, now=now)

    def _mark_terminal(self, status: GenerationRequestStatus, *, now: datetime) -> None:
        if self.status != GenerationRequestStatus.RUNNING:
            raise ValidationError(f"Cannot settle from status {self.status.value!r}.")
        self.status = status
        self.completed_at = now
