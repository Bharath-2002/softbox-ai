"""The current-state row per (variant, catalog slot) (D18) — mutable
approval/QC state, as opposed to `generation_items`' immutable attempt log.
`generation_item_id` points at the winning attempt that produced this row's
`asset_id`.

`superseded_by` is what the partial unique index
(`UNIQUE (tenant_id, variant_id, catalog_image_slot_id) WHERE superseded_by
IS NULL`) keys off: exactly one row per (variant, slot) may have it `NULL`
("live") at a time, while the full history is kept. Regeneration is
therefore a **two-write, one-transaction** operation — `mark_superseded` on
the existing live row, then `create()` for the replacement — and the write
order inside that transaction is not interchangeable: `update` (retiring
the old row) must run *before* `add` (inserting the new one), because
Postgres checks the (non-deferrable) partial unique index at the end of
each statement, not at commit — insert-then-update would have both rows
satisfying `superseded_by IS NULL` simultaneously for the duration of the
`INSERT` and raise a duplicate-key error immediately.

That same `update` step also references, via `superseded_by`, a row that
does not exist in the database yet — the replacement's id is known (this
codebase generates ids client-side, never via a DB default) but not yet
inserted. A plain foreign key would reject that immediately, which is
exactly what the migration's first version did before a test caught it:
`fk_catalog_images_superseded_by` is `DEFERRABLE INITIALLY DEFERRED`
specifically so the reference is only checked at commit, by which point the
replacement row has been inserted. See the migration's docstring for the
full constraint-interaction reasoning and
`tests/infrastructure/test_catalog_image_supersede.py` for both the correct
order proven to work and the reversed order proven to fail, against real
Postgres.

`create()` and `mark_superseded()` shipped first; `mark_qc_passed`/`mark_qc_failed`/
`mark_human_review` (D20) land alongside the `QualityControl` port, once a QC agent
exists to drive them. **`mark_qc_passed` always lands on `pending_approval`**, never
`approved` directly — `docs/ARCHITECTURE.md`'s own compressed state diagram
(`pending_qc ▶ qc_failed | pending_approval ▶ approved | rejected`) shows exactly one
QC-pass target, and no `approval.required`-style setting is registered anywhere in this
codebase today (`entities.setting`'s docstring uses that key only as an illustrative
example of D16's *shape*, not a shipped default) — inventing an auto-approve branch off
an unset setting would be guessing at a value nothing has ever configured, the same
mistake `CreateProduct`'s `price_currency` discussion caught and avoided. Auto-approve
when approval is disabled is M6's job ("Approval & content"), once a real approval
feature exists to make that call for real.

The QC/approval transitions this chunk does *not* add
(`pending_approval -> approved/rejected`) still have no caller — that is M6, not M5.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.shared.errors import ValidationError
from app.shared.ids import (
    AssetId,
    CatalogImageId,
    CatalogImageSlotId,
    GenerationItemId,
    ProductVariantId,
    TenantId,
    UserId,
    new_catalog_image_id,
)


class CatalogImageStatus(StrEnum):
    PENDING_QC = "pending_qc"
    QC_FAILED = "qc_failed"
    HUMAN_REVIEW = "human_review"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class CatalogImage:
    id: CatalogImageId
    tenant_id: TenantId
    variant_id: ProductVariantId
    catalog_image_slot_id: CatalogImageSlotId
    asset_id: AssetId
    generation_item_id: GenerationItemId
    status: CatalogImageStatus
    qc_result: dict[str, Any] | None
    is_primary: bool
    approved_by: UserId | None
    approved_at: datetime | None
    rejection_reason: str | None
    superseded_by: CatalogImageId | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        variant_id: ProductVariantId,
        catalog_image_slot_id: CatalogImageSlotId,
        asset_id: AssetId,
        generation_item_id: GenerationItemId,
        *,
        now: datetime,
        is_primary: bool = False,
    ) -> CatalogImage:
        return CatalogImage(
            id=new_catalog_image_id(),
            tenant_id=tenant_id,
            variant_id=variant_id,
            catalog_image_slot_id=catalog_image_slot_id,
            asset_id=asset_id,
            generation_item_id=generation_item_id,
            status=CatalogImageStatus.PENDING_QC,
            qc_result=None,
            is_primary=is_primary,
            approved_by=None,
            approved_at=None,
            rejection_reason=None,
            superseded_by=None,
            created_at=now,
            updated_at=now,
        )

    def mark_superseded(self, *, by: CatalogImageId, now: datetime) -> None:
        if self.superseded_by is not None:
            raise ValidationError(f"Catalog image {self.id} is already superseded.")
        self.superseded_by = by
        self.updated_at = now

    def mark_qc_passed(self, *, qc_result: dict[str, Any], now: datetime) -> None:
        if self.status != CatalogImageStatus.PENDING_QC:
            raise ValidationError(f"Cannot pass QC from status {self.status.value!r}.")
        self.status = CatalogImageStatus.PENDING_APPROVAL
        self.qc_result = qc_result
        self.updated_at = now

    def mark_qc_failed(self, *, qc_result: dict[str, Any], now: datetime) -> None:
        if self.status != CatalogImageStatus.PENDING_QC:
            raise ValidationError(f"Cannot fail QC from status {self.status.value!r}.")
        self.status = CatalogImageStatus.QC_FAILED
        self.qc_result = qc_result
        self.updated_at = now

    def mark_human_review(self, *, reason: str, now: datetime) -> None:
        """`qc_failed -> human_review` — D20's retry ladder exhausted (or,
        for the retry-can't-even-be-attempted case, no alternate template
        exists). Reachable **regardless of the tenant's approval setting** —
        this is the one place a QC failure always surfaces to a human."""
        if self.status != CatalogImageStatus.QC_FAILED:
            raise ValidationError(
                f"Cannot escalate to human review from status {self.status.value!r}."
            )
        self.status = CatalogImageStatus.HUMAN_REVIEW
        self.rejection_reason = reason
        self.updated_at = now
