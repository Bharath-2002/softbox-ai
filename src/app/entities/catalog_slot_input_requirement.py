"""The sharing join behind D13 — what makes one photograph feed several
catalog images. A row says "catalog slot C needs input slot I, playing role
R, at prompt position P."

No synthetic id: the natural key is the pair itself
(``catalog_image_slot_id``, ``input_image_slot_id``) — a catalog slot either
requires a given input or it does not, so there is no meaningful second row
for the same pair to collide with.

``role`` is free descriptive text ("garment_body", "border_detail"), not run
through ``entities.spec_key.validate_key`` — unlike a definition's ``key``,
it is never used as a JSONB key, a Pydantic field name, or a placeholder
segment; ``prompt_position`` (the ``{{input.N}}`` index) is what the D14
template actually keys off.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.shared.ids import CatalogImageSlotId, InputImageSlotId, TenantId


@dataclass
class CatalogSlotInputRequirement:
    tenant_id: TenantId
    catalog_image_slot_id: CatalogImageSlotId
    input_image_slot_id: InputImageSlotId
    role: str
    prompt_position: int
    is_required: bool
    created_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
        *,
        role: str,
        prompt_position: int,
        now: datetime,
        is_required: bool = True,
    ) -> CatalogSlotInputRequirement:
        return CatalogSlotInputRequirement(
            tenant_id=tenant_id,
            catalog_image_slot_id=catalog_image_slot_id,
            input_image_slot_id=input_image_slot_id,
            role=role,
            prompt_position=prompt_position,
            is_required=is_required,
            created_at=now,
        )
