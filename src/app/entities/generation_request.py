"""The run-level row for one "Save & Generate" (D18): one per product
variant, fanning out into many `generation_items` (the immutable attempt
log — see `entities.generation_item`). `spec_version_id` is the pinned
snapshot the request was generated against, the same D15 discipline as
`Product`/`ProductVariant` — a later spec change must never retroactively
alter what an in-flight or historical request meant.

Only `create()` lands in this chunk. `GenerationRequestStatus` names every
state the D19 state diagram describes (`queued -> running -> succeeded /
partially_failed / failed`, plus `cancelled`), matching the migration's
`CHECK` constraint, but the transition methods themselves are not built
here — nothing drives `running`/`succeeded`/`partially_failed`/`failed` yet,
since the worker that executes `generation_items` and the reconciler that
sweeps stuck runs are both still ahead in the M5 sequence. Same posture
`entities.product` documents for its own not-yet-driven states.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

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
