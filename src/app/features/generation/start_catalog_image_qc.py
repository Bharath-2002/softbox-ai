"""Claims the next due `catalog_image.qc_requested` job (D19/D20) and hands
back everything `agents.catalog_image_qc` needs for the provider call it
makes *outside* this transaction: where the generated image and its
reference photos live (`storage_key`s, read from the winning
`generation_item`'s `output_asset_id`/`input_asset_ids` while a transaction
is already open), the slot's spec dict from the product's **pinned**
snapshot (D15 - the same discipline `FanOutGenerationItems` follows, not
the live `catalog_image_slots` table), and the variant's declared colour.

`declared_colour` is resolved via `SemanticRole.COLOUR` on the pinned
snapshot's `attribute_definitions` - the only vertical-agnostic way to find
"the colour" (`VariantAxis` carries no semantic role, so a tenant that
models colour as a variant axis rather than an attribute - `entities.
product_variant`'s own docstring uses exactly that example - yields `None`
here, an honest, documented gap in the colour-delta check, not a guess).

Read-only in the domain sense - no entity is mutated here, since
`CatalogImageStatus` has no intermediate "qc_running" state to transition
into (unlike `GenerationItem`, which does). Only the claimed `task_queue`
job actually changes state in this transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.entities.attribute_definition import SemanticRole
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.prompt_composition import merge_attributes
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageId, TenantId

JOB_TYPE = "catalog_image.qc_requested"
CLAIMED_BY = "catalog-image-qc-worker"


@dataclass(frozen=True)
class CatalogImageQcContext:
    job_id: UUID
    catalog_image_id: CatalogImageId
    image_storage_key: str
    reference_storage_keys: list[str]
    slot_spec: dict[str, Any]
    declared_colour: str | None


class StartCatalogImageQc:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, tenant_id: TenantId) -> CatalogImageQcContext | None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            job = await uow.task_queue.claim(
                tenant_id, claimed_by=CLAIMED_BY, job_type=JOB_TYPE, now=now
            )
            if job is None:
                return None

            image_id = CatalogImageId(UUID(job.payload["catalog_image_id"]))
            image = await uow.catalog_images.get(tenant_id, image_id)
            if image is None:
                await uow.task_queue.fail(
                    tenant_id, job.id, error=f"catalog_image {image_id} not found", now=now
                )
                return None

            asset = await uow.assets.get(tenant_id, image.asset_id)
            if asset is None:
                raise NotFoundError(f"Catalog image asset {image.asset_id} not found.")

            item = await uow.generation_items.get(tenant_id, image.generation_item_id)
            if item is None:
                raise NotFoundError(f"Generation item {image.generation_item_id} not found.")

            reference_storage_keys: list[str] = []
            for asset_id in item.input_asset_ids:
                reference_asset = await uow.assets.get(tenant_id, asset_id)
                if reference_asset is None:
                    raise NotFoundError(f"Reference asset {asset_id} not found.")
                reference_storage_keys.append(reference_asset.storage_key)

            variant = await uow.product_variants.get(tenant_id, image.variant_id)
            if variant is None:
                raise NotFoundError("Product variant not found.")
            product = await uow.products.get(tenant_id, variant.product_id)
            if product is None:
                raise NotFoundError("Product not found.")
            spec_version = await uow.category_spec_versions.get(tenant_id, product.spec_version_id)
            if spec_version is None:
                raise NotFoundError(
                    "The product's pinned spec version is missing (data inconsistency)."
                )
            snapshot = spec_version.snapshot

            slot_spec: dict[str, Any] = next(
                (
                    s
                    for s in snapshot.get("catalog_image_slots", [])
                    if s["id"] == str(image.catalog_image_slot_id)
                ),
                {},
            )

            merged_attributes = merge_attributes(product.attributes, variant.attributes)
            colour_key = next(
                (
                    a["key"]
                    for a in snapshot.get("attribute_definitions", [])
                    if a.get("semantic_role") == SemanticRole.COLOUR.value
                ),
                None,
            )
            declared_colour = merged_attributes.get(colour_key) if colour_key is not None else None

            return CatalogImageQcContext(
                job_id=job.id,
                catalog_image_id=image.id,
                image_storage_key=asset.storage_key,
                reference_storage_keys=reference_storage_keys,
                slot_spec=slot_spec,
                declared_colour=declared_colour,
            )
