"""Expands a `queued` `generation_request` into one `generation_item` per
required catalog slot (D18) — the fan-out step `CreateGenerationRequest`
deliberately left undone, now unblocked by `prompt_composition` existing.

For each required catalog slot: picks that slot's default, analysed
template (no per-variant template-choice mechanism exists yet — this is the
open question `CreateGenerationRequest`'s docstring flagged, resolved here
with the only real signal available, `CatalogTemplate.is_default`); resolves
each of the slot's required input images via D12's resolution rule
(`resolve_input_image`, variant image wins over the product's) — filtered to
`InputImageStatus.READY` first, the same bar `RecomputeProductReadiness`
(M4) already set for "this input is actually usable"; a `captured`-but-
unvalidated or `rejected` image must not silently count as present, the
same class of bug a status filter left off would have let through here.
Composes the prompt (`prompt_composition.compose_prompt`); and writes a
`PENDING` `generation_item` plus an outbox event so a relay can turn it into
a `task_queue` job once the worker that would claim and execute it exists.
One outbox event **per item**, not one for the whole batch — the eventual
worker claims and executes one `generation_item` per job (D19's "the queue
executes one step"), so the unit the relay enqueues must already be
per-item.

A required catalog slot with no default analysed template, or a required
input the product/variant never captured (or never got past `validating`),
is a real, actionable failure (`ValidationError`) — generation cannot
silently skip a required slot and call the result complete. Against real
Postgres, both failures leave nothing written: the whole `async with` block
rolls back, so fan-out either fully succeeds for a request or writes
nothing, never a partial item set with the request stuck in `queued`. (The
in-memory fake used by this module's own tests has no such rollback — its
single-required-slot test scenarios happen not to exercise a partial-write
case, not a demonstration of the fake enforcing atomicity it doesn't have.)

**Does not implement D12's recolour hex-injection** ("no photographed
variant input -> inject colour + hex as a recolour instruction") even
though, unlike `prompt_composition`, this use case *does* have
`product_input_images` in hand — deferred rather than silently missed;
`{{variant.colour}}` still substitutes to the plain axis value for every
variant today, photographed or not.

Moves the request to `running` on completion (`GenerationRequest.
mark_running`) — the first real driver of that transition; every other
`GenerationRequestStatus` value still has no caller (the worker, the
reconciler).

`provider`/`model` are read from `Settings` (D18: "model id pinned in
config, not code"), passed into this use case's constructor rather than
read from a global — matching every other adapter-configuration value in
this codebase.
"""

from __future__ import annotations

import random
from typing import Any
from uuid import UUID

from app.entities.catalog_template import CatalogTemplate
from app.entities.generation_item import GenerationItem
from app.entities.product_input_image import InputImageStatus, ProductInputImage
from app.services.input_image_resolution import resolve_input_image
from app.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.services.prompt_composition import COMPOSITION_VERSION, compose_prompt, merge_attributes
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import (
    AssetId,
    CatalogImageSlotId,
    GenerationRequestId,
    InputImageSlotId,
    ProductVariantId,
    TenantId,
)

_SEED_UPPER_BOUND = 2**31 - 1


class FanOutGenerationItems:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, clock: Clock, *, provider: str, model: str
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._provider = provider
        self._model = model

    async def __call__(
        self, *, tenant_id: TenantId, generation_request_id: GenerationRequestId
    ) -> list[GenerationItem]:
        async with self._uow_factory(tenant_id) as uow:
            request = await uow.generation_requests.get(tenant_id, generation_request_id)
            if request is None:
                raise NotFoundError("Generation request not found.")
            if request.status.value != "queued":
                raise ValidationError(
                    f"Cannot fan out from status {request.status.value!r} - "
                    "a request is only fanned out once, from 'queued'."
                )

            product = await uow.products.get(tenant_id, request.product_id)
            if product is None:
                raise NotFoundError("Product not found.")
            variant = await uow.product_variants.get(tenant_id, request.variant_id)
            if variant is None:
                raise NotFoundError("Product variant not found.")
            spec_version = await uow.category_spec_versions.get(tenant_id, product.spec_version_id)
            if spec_version is None:
                raise NotFoundError(
                    "The product's pinned spec version is missing (data inconsistency)."
                )
            snapshot = spec_version.snapshot

            captured_images = await uow.product_input_images.list_for_product(tenant_id, product.id)
            ready_images = [i for i in captured_images if i.status == InputImageStatus.READY]
            merged_attributes = merge_attributes(product.attributes, variant.attributes)

            now = self._clock.now()
            items: list[GenerationItem] = []
            for slot in snapshot.get("catalog_image_slots", []):
                if not slot.get("is_required"):
                    continue

                template = await self._pick_default_template(uow, tenant_id, slot)
                input_asset_ids = self._resolve_required_inputs(
                    slot, ready_images, variant_id=variant.id
                )
                prompt_rendered = compose_prompt(
                    snapshot,
                    catalog_image_slot_id=slot["id"],
                    prompt_template=template.prompt_template or "",
                    attributes=merged_attributes,
                    axis_values=variant.axis_values,
                )

                item = GenerationItem.create(
                    tenant_id,
                    request.id,
                    template.catalog_image_slot_id,
                    template.id,
                    attempt_no=1,
                    provider=self._provider,
                    model=self._model,
                    model_params={},
                    seed=random.randint(0, _SEED_UPPER_BOUND),
                    prompt_rendered=prompt_rendered,
                    prompt_version=COMPOSITION_VERSION,
                    input_asset_ids=input_asset_ids,
                    now=now,
                )
                await uow.generation_items.add(item)
                await uow.outbox_events.add(
                    tenant_id,
                    event_type="generation_item.render_requested",
                    payload={"generation_item_id": str(item.id)},
                    now=now,
                )
                items.append(item)

            request.mark_running(now=now)
            await uow.generation_requests.update(request)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=request.requested_by,
                action="generation_request.fanned_out",
                subject_type="generation_request",
                subject_id=request.id,
                before=None,
                after={"item_count": len(items)},
                now=now,
            )

            return items

    async def _pick_default_template(
        self, uow: UnitOfWork, tenant_id: TenantId, slot: dict[str, Any]
    ) -> CatalogTemplate:
        templates = await uow.catalog_templates.list_for_catalog_slot(
            tenant_id, CatalogImageSlotId(UUID(slot["id"]))
        )
        for template in templates:
            if template.is_default and template.status.value == "analysed":
                return template
        raise ValidationError(
            f"Catalog slot {slot['key']!r} has no default, analysed template to generate from."
        )

    def _resolve_required_inputs(
        self,
        slot: dict[str, Any],
        captured_images: list[ProductInputImage],
        *,
        variant_id: ProductVariantId,
    ) -> list[AssetId]:
        input_asset_ids: list[AssetId] = []
        for requirement in slot.get("input_requirements", []):
            image = resolve_input_image(
                captured_images,
                variant_id=variant_id,
                input_image_slot_id=InputImageSlotId(UUID(requirement["input_image_slot_id"])),
            )
            if image is None:
                if requirement.get("is_required"):
                    raise ValidationError(
                        f"Required input {requirement['input_image_slot_id']!r} for catalog "
                        f"slot {slot['key']!r} was never captured."
                    )
                continue
            input_asset_ids.append(image.asset_id)
        return input_asset_ids
