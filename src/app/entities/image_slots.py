"""The category-level input pool and the catalog images produced from it
(D13) — the modelling choice that lets one photograph feed several catalog
images. The sharing join itself (``catalog_slot_input_requirements``) is the
next chunk; this is the two pool-definition tables it references.

``InputImageSlot`` is what gets *captured* (a photograph of one part of the
product). ``CatalogImageSlot`` is what gets *produced* (a generated catalog
image, at a fixed aspect ratio and target size). Neither references the
other directly — the sharing join is a separate table precisely so the same
input can feed more than one catalog slot without being duplicated or
re-captured.

``example_asset_id`` is a bare id, not a foreign key — ``assets`` does not
exist until M3 (the same reasoning ``audit_log.actor_user_id`` used before
``users`` existed, chunk 3). Adding the constraint later is additive.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.entities.spec_key import validate_key
from app.shared.ids import (
    CatalogImageSlotId,
    CategoryId,
    InputImageSlotId,
    TenantId,
    new_catalog_image_slot_id,
    new_input_image_slot_id,
)


@dataclass
class InputImageSlot:
    id: InputImageSlotId
    tenant_id: TenantId
    category_id: CategoryId
    key: str
    label: str
    description: str | None
    capture_guidance: str | None
    example_asset_id: UUID | None
    normalisation: dict[str, Any]
    is_required: bool
    position: int
    introduced_in_version: int | None
    retired_in_version: int | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        category_id: CategoryId,
        *,
        key: str,
        label: str,
        now: datetime,
        description: str | None = None,
        capture_guidance: str | None = None,
        example_asset_id: UUID | None = None,
        normalisation: dict[str, Any] | None = None,
        is_required: bool = True,
        position: int = 0,
    ) -> InputImageSlot:
        validate_key(key, what="Input image slot key")
        return InputImageSlot(
            id=new_input_image_slot_id(),
            tenant_id=tenant_id,
            category_id=category_id,
            key=key,
            label=label,
            description=description,
            capture_guidance=capture_guidance,
            example_asset_id=example_asset_id,
            normalisation=normalisation or {},
            is_required=is_required,
            position=position,
            introduced_in_version=None,
            retired_in_version=None,
            created_at=now,
            updated_at=now,
        )


@dataclass
class CatalogImageSlot:
    id: CatalogImageSlotId
    tenant_id: TenantId
    category_id: CategoryId
    key: str
    label: str
    description: str | None
    position: int
    aspect_ratio: str
    target_width: int
    target_height: int
    is_required: bool
    introduced_in_version: int | None
    retired_in_version: int | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        category_id: CategoryId,
        *,
        key: str,
        label: str,
        aspect_ratio: str,
        target_width: int,
        target_height: int,
        now: datetime,
        description: str | None = None,
        is_required: bool = True,
        position: int = 0,
    ) -> CatalogImageSlot:
        validate_key(key, what="Catalog image slot key")
        return CatalogImageSlot(
            id=new_catalog_image_slot_id(),
            tenant_id=tenant_id,
            category_id=category_id,
            key=key,
            label=label,
            description=description,
            position=position,
            aspect_ratio=aspect_ratio,
            target_width=target_width,
            target_height=target_height,
            is_required=is_required,
            introduced_in_version=None,
            retired_in_version=None,
            created_at=now,
            updated_at=now,
        )
