"""Computes whether a product has every required attribute and every
required input image present (the Gate's "`ready` is computed against the
**pinned** spec version" bullet). Pure — reads `is_required` off an
already-resolved `category_spec_versions.snapshot` (D15), never off the
LIVE `attribute_definitions`/`input_image_slots` tables. Reading LIVE here
would be exactly the bug this Gate bullet exists to catch: a product stays
`ready` against the version it pinned even after the category republishes
and adds a new required field, and a snapshot lookup makes that the only
possible outcome rather than something a caller has to remember.

An input image only counts if it has reached `InputImageStatus.READY` —
merely existing (`captured`) is not enough, since an unvalidated,
unnormalised photo reaching a product's `ready` state would defeat §6.1
entirely. With no `ImageNormalisation` adapter built yet (see
`entities.product_input_image`'s module docstring), no product can actually
satisfy this today — that is an honest consequence of the deferral, not a
bug in this function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.entities.product_input_image import InputImageStatus, ProductInputImage
from app.services.input_image_resolution import resolve_input_image
from app.shared.ids import InputImageSlotId, ProductVariantId


@dataclass(frozen=True)
class ReadinessResult:
    is_ready: bool
    missing: list[str]


def compute_product_readiness(
    snapshot: dict[str, Any],
    *,
    attributes: dict[str, Any],
    images: list[ProductInputImage],
    variant_id: ProductVariantId | None = None,
) -> ReadinessResult:
    missing: list[str] = []

    for definition in snapshot.get("attribute_definitions", []):
        if not definition["is_required"]:
            continue
        if attributes.get(definition["key"]) in (None, ""):
            missing.append(f"attribute:{definition['key']}")

    for slot in snapshot.get("input_image_slots", []):
        if not slot["is_required"]:
            continue
        slot_id = InputImageSlotId(UUID(slot["id"]))
        resolved = resolve_input_image(images, variant_id=variant_id, input_image_slot_id=slot_id)
        if resolved is None or resolved.status is not InputImageStatus.READY:
            missing.append(f"input_image:{slot['key']}")

    return ReadinessResult(is_ready=not missing, missing=missing)
