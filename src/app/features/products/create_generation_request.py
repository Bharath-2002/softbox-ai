"""Reserves quota and creates a `generation_requests` row (D18, D24) — the
"Save & Generate" action, and the first real writer to `outbox_events`:
every other use case shipped so far writes only `audit_log`, so nothing has
proven the outbox's write path end-to-end before this, only its relay
reading from a directly-seeded table in tests.

**Deliberately stops short of creating `generation_items`.** Doing so needs
prompt composition (scene + input role lines + attrs + variant, per
`docs/DIAGRAMS.md`'s Generation flow) to fill `generation_items`'
NOT NULL columns — `prompt_rendered`, `model`, `provider`, `seed` are all
facts about a rendered, ready-to-execute attempt, which cannot exist before
prompt composition does. Building the fan-out here would mean inventing
placeholder values for those columns, exactly the kind of stub CLAUDE.md
forbids. The fan-out is a **separate, later step** — driven by whatever
consumes the `generation_request.created` outbox event once prompt
composition and the worker exist, matching D19's "the queue executes one
step" model rather than one use case doing everything inline.

Quota is reserved for `len(required catalog slots)` — one unit per
`generation_item` this request will eventually produce, read from the
product's **pinned** spec snapshot (D15), not the category's live tables.
`reserve()` is called directly, with no `ensure_period` call from here:
provisioning a tenant's quota limit is a billing/plan concern this use case
has no basis to invent a number for, and no M9 tenant-onboarding flow exists
yet to set one for real. The honest, documented consequence: **no tenant has
a quota row provisioned today, so this always fails closed in practice**
until that M9 flow exists — the same "real capability, not wired to a
trigger that doesn't exist yet" gap this milestone has recorded repeatedly,
here expressed as "real capability, blocked on upstream provisioning that
doesn't exist yet" instead.

Which template renders each catalog slot is deliberately **not** decided
here — no per-variant template-choice mechanism exists in the codebase yet
(no field records one). That choice belongs to the fan-out step, once it's
built, most plausibly defaulting to each slot's `CatalogTemplate.is_default`
row; left as an open question on that step rather than guessed at here,
since this use case never touches `catalog_templates` at all.
"""

from __future__ import annotations

from app.entities.generation_request import GenerationRequest
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, QuotaExceededError
from app.shared.ids import ProductId, ProductVariantId, TenantId, UserId

_QUOTA_METRIC = "generation.images"


class CreateGenerationRequest:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        product_id: ProductId,
        variant_id: ProductVariantId,
        requested_by: UserId,
    ) -> GenerationRequest:
        async with self._uow_factory(tenant_id) as uow:
            product = await uow.products.get(tenant_id, product_id)
            if product is None:
                raise NotFoundError("Product not found.")

            variant = await uow.product_variants.get(tenant_id, variant_id)
            if variant is None or variant.product_id != product_id:
                raise NotFoundError("Product variant not found.")

            spec_version = await uow.category_spec_versions.get(tenant_id, product.spec_version_id)
            if spec_version is None:
                raise NotFoundError(
                    "The product's pinned spec version is missing (data inconsistency)."
                )
            required_slot_count = sum(
                1
                for slot in spec_version.snapshot.get("catalog_image_slots", [])
                if slot.get("is_required")
            )
            if required_slot_count == 0:
                raise NotFoundError(
                    "This product's spec has no required catalog image slots to generate."
                )

            now = self._clock.now()
            period = now.strftime("%Y-%m")
            reserved = await uow.quota_reservations.reserve(
                tenant_id,
                period=period,
                metric=_QUOTA_METRIC,
                quantity=required_slot_count,
                now=now,
            )
            if not reserved:
                raise QuotaExceededError(
                    f"Quota exceeded for {_QUOTA_METRIC!r} in period {period!r}: "
                    f"cannot reserve {required_slot_count} more."
                )
            reservation = await uow.quota_reservations.get(
                tenant_id, period=period, metric=_QUOTA_METRIC
            )
            assert reservation is not None  # just reserved successfully above

            request = GenerationRequest.create(
                tenant_id,
                product_id,
                variant_id,
                product.spec_version_id,
                settings_snapshot={},
                quota_reservation_id=reservation.id,
                requested_by=requested_by,
                now=now,
            )
            await uow.generation_requests.add(request)

            await uow.outbox_events.add(
                tenant_id,
                event_type="generation_request.created",
                payload={"generation_request_id": str(request.id)},
                now=now,
            )

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=requested_by,
                action="generation_request.created",
                subject_type="generation_request",
                subject_id=request.id,
                before=None,
                after={
                    "product_id": str(product_id),
                    "variant_id": str(variant_id),
                    "required_slot_count": required_slot_count,
                },
                now=now,
            )

            return request
