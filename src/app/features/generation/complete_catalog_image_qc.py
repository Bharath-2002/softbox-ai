"""Records a `QcVerdict` (D20) against the `catalog_image` it was evaluated
for. A pass always lands on `pending_approval` first via `mark_qc_passed` -
QC and approval are recorded as two separate facts even when the net result
is immediate approval, so `qc_result` is never lost or skipped past. Then,
in the same transaction, `approval.required` (D16) is resolved at the
product's category/product scope: resolving to the literal `False` calls
`CatalogImage.approve(approved_by=None, ...)` immediately after; anything
else - `True`, unset (`None`), or a stored value that isn't literally the
bool `False` - leaves the image on `pending_approval`, fail-closed the same
way `QuotaReservationRepository.reserve` treats an unprovisioned metric as
zero budget rather than unlimited. This is the "QC still enforced when
approval is disabled" property M6's gate tests for: the verdict and its
checks are always written via `mark_qc_passed` before the setting is even
read, so disabling approval cannot skip QC, only the human review step
after it.

A fail lands on `qc_failed` and then, in the same transaction, either
creates the next `generation_item` (D20's bounded retry ladder - new seed,
then a different template, via the pure `services.qc_retry_ladder.
next_rung`) or escalates to `human_review` once the ladder is exhausted -
reachable regardless of the approval setting, since `human_review` is not
on the QC-pass path this setting governs at all.

Completes the `catalog_image.qc_requested` `task_queue` job unconditionally
at the end - from the queue's point of view, "QC ran and produced a
verdict" is success, whichever way the verdict and the ladder decision
went. A **job execution failure** (the provider call itself raising) is a
different case, handled by `FailCatalogImageQc`, not this use case.

Rung two (a different template) needs a recomposed prompt - a new
`prompt_template` means `compose_prompt` must run again, which needs the
same product/variant/spec-snapshot lookups `StartCatalogImageQc` already
did once; this transaction is a fresh one, so it pays them again. Rung one
(same template, new seed) reuses `prompt_rendered` verbatim - the lineage
that actually changes is the seed, not the prompt text. Both rungs reuse
the failed attempt's `input_asset_ids` unmodified - required inputs do not
change between QC retries of the same request, so `resolve_input_image`
never runs a second time here.
"""

from __future__ import annotations

import random
from datetime import datetime
from uuid import UUID

from app.entities.generation_item import GenerationItem
from app.services.ports.quality_control import QcVerdict
from app.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.services.prompt_composition import COMPOSITION_VERSION, compose_prompt, merge_attributes
from app.services.qc_retry_ladder import RetryRung, next_rung
from app.services.settings_resolver import SettingsResolver
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageId, TenantId

_SEED_UPPER_BOUND = 2**31 - 1
_APPROVAL_REQUIRED_KEY = "approval.required"


class CompleteCatalogImageQc:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        catalog_image_id: CatalogImageId,
        job_id: UUID,
        verdict: QcVerdict,
    ) -> None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            image = await uow.catalog_images.get(tenant_id, catalog_image_id)
            if image is None:
                raise NotFoundError("Catalog image not found.")

            if verdict.passed:
                image.mark_qc_passed(qc_result=verdict.checks, now=now)

                item = await uow.generation_items.get(tenant_id, image.generation_item_id)
                if item is None:
                    raise NotFoundError("Generation item not found.")
                request = await uow.generation_requests.get(tenant_id, item.request_id)
                if request is None:
                    raise NotFoundError("Generation request not found.")
                product = await uow.products.get(tenant_id, request.product_id)
                if product is None:
                    raise NotFoundError("Product not found.")

                resolver = SettingsResolver(uow.settings, uow.categories)
                approval_required = await resolver.resolve(
                    tenant_id,
                    _APPROVAL_REQUIRED_KEY,
                    category_id=product.category_id,
                    product_id=product.id,
                )
                if approval_required is False:
                    image.approve(approved_by=None, now=now)

                await uow.catalog_images.update(image)
                await uow.task_queue.complete(tenant_id, job_id, now=now)
                return

            image.mark_qc_failed(qc_result=verdict.checks, now=now)
            await uow.catalog_images.update(image)

            item = await uow.generation_items.get(tenant_id, image.generation_item_id)
            if item is None:
                raise NotFoundError("Generation item not found.")

            all_items = await uow.generation_items.list_for_request(tenant_id, item.request_id)
            attempts_for_slot = [
                i for i in all_items if i.catalog_image_slot_id == item.catalog_image_slot_id
            ]
            alternate_templates = await uow.catalog_templates.list_for_catalog_slot(
                tenant_id, item.catalog_image_slot_id
            )

            rung = next_rung(attempts_for_slot, alternate_templates)
            if rung is None:
                image.mark_human_review(
                    reason=verdict.reason or "QC retry ladder exhausted.", now=now
                )
                await uow.catalog_images.update(image)
            else:
                await self._retry(uow, tenant_id, item, rung, now=now)

            await uow.task_queue.complete(tenant_id, job_id, now=now)

    async def _retry(
        self,
        uow: UnitOfWork,
        tenant_id: TenantId,
        item: GenerationItem,
        rung: RetryRung,
        *,
        now: datetime,
    ) -> None:
        if rung.reuse_prompt:
            prompt_rendered = item.prompt_rendered
        else:
            template = await uow.catalog_templates.get(tenant_id, rung.template_id)
            if template is None:
                raise NotFoundError("Alternate template not found.")
            request = await uow.generation_requests.get(tenant_id, item.request_id)
            if request is None:
                raise NotFoundError("Generation request not found.")
            variant = await uow.product_variants.get(tenant_id, request.variant_id)
            if variant is None:
                raise NotFoundError("Product variant not found.")
            product = await uow.products.get(tenant_id, request.product_id)
            if product is None:
                raise NotFoundError("Product not found.")
            spec_version = await uow.category_spec_versions.get(tenant_id, product.spec_version_id)
            if spec_version is None:
                raise NotFoundError(
                    "The product's pinned spec version is missing (data inconsistency)."
                )
            snapshot = spec_version.snapshot
            merged_attributes = merge_attributes(product.attributes, variant.attributes)
            prompt_rendered = compose_prompt(
                snapshot,
                catalog_image_slot_id=str(item.catalog_image_slot_id),
                prompt_template=template.prompt_template or "",
                attributes=merged_attributes,
                axis_values=variant.axis_values,
            )

        new_item = GenerationItem.create(
            tenant_id,
            item.request_id,
            item.catalog_image_slot_id,
            rung.template_id,
            attempt_no=rung.attempt_no,
            provider=item.provider,
            model=item.model,
            model_params=item.model_params,
            seed=random.randint(0, _SEED_UPPER_BOUND),
            prompt_rendered=prompt_rendered,
            prompt_version=COMPOSITION_VERSION,
            input_asset_ids=item.input_asset_ids,
            now=now,
        )
        await uow.generation_items.add(new_item)
        await uow.outbox_events.add(
            tenant_id,
            event_type="generation_item.render_requested",
            payload={"generation_item_id": str(new_item.id)},
            now=now,
        )
