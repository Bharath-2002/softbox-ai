"""Manually-triggered entry point for D23's copy generation — `channel`/
`locale` are caller-supplied, not auto-derived from an approval event.

That is a deliberate scope cut, not an oversight: `docs/DIAGRAMS.md` draws
`Q8 --> C1` (approved imagery feeds the copywriting agent), which reads
like an automatic trigger the same shape `ApproveCatalogImage` ->
`content_draft.generate_requested` outbox event would give. Building that
trigger needs two things this codebase does not have yet: a real,
resolvable "which channels/locales does this tenant publish to" list (D21's
channel adapters — `social_accounts`, `pinterest`/`instagram`/`facebook` —
are still M7, unbuilt), and a "have all this variant's required catalog
slots been approved" rollup (the fan-out target for images,
`catalog_image_slots`, is a real per-category concept; there is no
per-tenant analogue for channels today). Auto-deriving either would be
guessing, the same category of mistake `CreateProduct`'s `price_currency`
gap and D12's recolour hex-injection are already flagged for elsewhere in
this project. This use case is the same "real capability, no automatic
trigger" posture `RecomputeProductReadiness`/`FanOutGenerationItems`
(pre-`CreateGenerationRequest`) both shipped as first.

Requires **at least one live, approved** catalog image for the variant —
cheap, real, and it is what keeps "generate copy for a variant with no
approved imagery" a 4xx instead of fabricated copy describing nothing.
This is not the same as "all required slots approved" (the rollup named
above, not built) — one approved image is enough to prove the variant has
*some* real photography to describe.

Writes a `content_draft.generate_requested` outbox event rather than
calling `TaskQueue.enqueue` directly — the established pattern every other
queue-bound write in this codebase follows (`RelayOutboxEventsForTenant` is
the only direct `enqueue` caller). `model` is stamped into the event
payload at enqueue time, the same "pinned before the call, not decided by
the adapter" reasoning `FanOutGenerationItems` applies to
`generation_items.model`.
"""

from __future__ import annotations

from app.entities.catalog_image import CatalogImageStatus
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import ProductVariantId, TenantId


class GenerateContentDraft:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock, *, model: str) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._model = model

    async def __call__(
        self, *, tenant_id: TenantId, variant_id: ProductVariantId, channel: str, locale: str
    ) -> None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            variant = await uow.product_variants.get(tenant_id, variant_id)
            if variant is None:
                raise NotFoundError("Product variant not found.")

            images = await uow.catalog_images.list_for_variant(tenant_id, variant_id)
            has_approved_image = any(
                image.superseded_by is None and image.status == CatalogImageStatus.APPROVED
                for image in images
            )
            if not has_approved_image:
                raise ValidationError(
                    "Cannot generate copy for a variant with no approved catalog images."
                )

            await uow.outbox_events.add(
                tenant_id,
                event_type="content_draft.generate_requested",
                payload={
                    "variant_id": str(variant_id),
                    "channel": channel,
                    "locale": locale,
                    "model": self._model,
                },
                now=now,
            )
