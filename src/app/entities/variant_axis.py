"""A tenant-defined variant dimension, owned by one category (D12).

Never hardcode "colour" — a **size** axis multiplies SKUs but must not
multiply generated images; a **colour** axis must. ``affects_imagery`` is
what the generation pipeline (M5) fans out over: the distinct combinations
of imagery-affecting axis values only, never every axis.

``VariantAxisValue`` (below) is the enumerated option set for one axis
(e.g. "maroon", "tissue") — inheritance/override-by-key (D10) applies to
axes themselves (a subcategory can add or override an axis its parent
defines), not to individual values, so only ``VariantAxis.key`` goes through
``entities.spec_key.validate_key``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.entities.spec_key import validate_key
from app.shared.ids import (
    CategoryId,
    TenantId,
    VariantAxisId,
    VariantAxisValueId,
    new_variant_axis_id,
    new_variant_axis_value_id,
)


@dataclass
class VariantAxis:
    id: VariantAxisId
    tenant_id: TenantId
    category_id: CategoryId
    key: str
    label: str
    position: int
    affects_imagery: bool
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
        affects_imagery: bool,
        now: datetime,
        position: int = 0,
    ) -> VariantAxis:
        validate_key(key, what="Variant axis key")
        return VariantAxis(
            id=new_variant_axis_id(),
            tenant_id=tenant_id,
            category_id=category_id,
            key=key,
            label=label,
            position=position,
            affects_imagery=affects_imagery,
            introduced_in_version=None,
            retired_in_version=None,
            created_at=now,
            updated_at=now,
        )


@dataclass
class VariantAxisValue:
    id: VariantAxisValueId
    tenant_id: TenantId
    axis_id: VariantAxisId
    value: str
    label: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        axis_id: VariantAxisId,
        *,
        value: str,
        label: str,
        now: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> VariantAxisValue:
        return VariantAxisValue(
            id=new_variant_axis_value_id(),
            tenant_id=tenant_id,
            axis_id=axis_id,
            value=value,
            label=label,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
