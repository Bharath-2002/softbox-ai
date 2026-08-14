"""Seeds a catalog image slot with the stock scene preset library (D0's
resolution to D14): ``authored_scene`` templates that ship on day one,
before a tenant has captured a single reference photo.

Every preset description is placeholder-free by construction — a stock
preset is written before anyone knows what input slots a given tenant's
category declares, so it cannot reference ``{{input.*}}`` and still be
guaranteed to validate. That also means every preset always reaches
``analysed`` immediately; D14a's validator only ever has ``{{attr.*}}``/
``{{variant.*}}`` to check, and these presets don't use those either.

One transaction, one snapshot resolution, looped over every preset — not
built by calling ``CreateAuthoredTemplate`` once per preset, which would
open N transactions and re-resolve the same spec N times for what is
conceptually a single seeding operation.

**Nothing calls this yet.** There is no tenant-provisioning flow in this
codebase at all (tenant onboarding is out of scope until M9 — see
``docs/ARCHITECTURE.md``'s milestone table), so "seeded for every new
tenant" has no hook to attach to today. The earliest point a preset is even
attachable is once a catalog image slot exists (``catalog_templates.
catalog_image_slot_id`` is not nullable), which argues for triggering this
from catalog-slot creation rather than tenant creation once a trigger is
wired — a decision left open rather than invented against a flow that
doesn't exist.
"""

from __future__ import annotations

from app.entities.catalog_template import CatalogTemplate
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.spec_snapshot_builder import SpecSnapshotBuilder
from app.services.template_placeholder_validator import validate_template_placeholders
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageSlotId, TenantId, UserId

# Scene-only, product-agnostic (D0's finding 2: a template must not describe
# the product, only the scene, placement, camera, light and grade). No
# placeholders, no vertical vocabulary - safe to ship before any tenant's
# category, input slots, or reference photos exist.
DEFAULT_STOCK_SCENE_PRESETS: tuple[tuple[str, str], ...] = (
    (
        "Studio flatlay",
        "A clean flat-lay composition on a seamless white studio surface, "
        "soft diffused overhead daylight, minimal shadow, straight-down camera angle.",
    ),
    (
        "Marble tabletop",
        "Resting on a polished white marble surface, soft natural light from "
        "the left, shallow depth of field, slight warm colour grade.",
    ),
    (
        "Linen backdrop",
        "Draped against a neutral linen backdrop, warm late-afternoon light, "
        "gentle diagonal composition, soft grain.",
    ),
    (
        "Outdoor natural light",
        "Photographed outdoors in open shade, soft natural daylight, "
        "softly blurred greenery in the background, eye-level camera angle.",
    ),
)


class SeedStockPresets:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        actor_user_id: UserId,
        presets: tuple[tuple[str, str], ...] = DEFAULT_STOCK_SCENE_PRESETS,
    ) -> list[CatalogTemplate]:
        async with self._uow_factory(tenant_id) as uow:
            catalog_slot = await uow.catalog_image_slots.get(tenant_id, catalog_image_slot_id)
            if catalog_slot is None:
                raise NotFoundError("Catalog image slot not found.")

            snapshot_builder = SpecSnapshotBuilder(
                uow.categories,
                uow.attribute_definitions,
                uow.variant_axes,
                uow.variant_axis_values,
                uow.input_image_slots,
                uow.catalog_image_slots,
                uow.catalog_slot_input_requirements,
            )
            snapshot = await snapshot_builder.build(tenant_id, catalog_slot.category_id)

            now = self._clock.now()
            seeded: list[CatalogTemplate] = []
            for position, (name, prompt_template) in enumerate(presets):
                existing = await uow.catalog_templates.get_latest_version(
                    tenant_id, catalog_image_slot_id, name
                )
                version = existing.version + 1 if existing is not None else 1

                template = CatalogTemplate.create_authored(
                    tenant_id,
                    catalog_image_slot_id,
                    name=name,
                    prompt_template=prompt_template,
                    created_by=actor_user_id,
                    now=now,
                    version=version,
                    position=position,
                )
                await uow.catalog_templates.add(template)

                problems = validate_template_placeholders(
                    snapshot,
                    catalog_image_slot_id=str(catalog_image_slot_id),
                    prompt_template=prompt_template,
                )
                template.start_analysing(now=now)
                if problems:
                    template.mark_invalid(reason="; ".join(problems), now=now)
                else:
                    template.mark_analysed(
                        prompt_template=prompt_template,
                        analysis=None,
                        analysis_model=None,
                        now=now,
                    )
                await uow.catalog_templates.update(template)
                seeded.append(template)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="catalog_template.stock_presets_seeded",
                subject_type="catalog_image_slot",
                subject_id=catalog_image_slot_id,
                before=None,
                after={"count": len(seeded)},
                now=now,
            )

            return seeded
