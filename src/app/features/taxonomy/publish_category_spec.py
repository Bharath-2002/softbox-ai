"""Publishes a category's spec (D15): builds the resolved snapshot, stamps
``introduced_in_version`` on any of the category's own rows that don't have
one yet, writes the immutable ``category_spec_versions`` row, advances
``categories.current_spec_version``, clears ``draft_spec_version``, and
audits the change — all in the one transaction ``MoveCategory`` already
established the shape for.

Only rows this category itself owns are stamped (``list_for_category``, not
the whole ancestor chain) — ``introduced_in_version`` tracks a row's
position in *its own owning category's* version sequence; an ancestor's rows
get stamped when that ancestor is published, against its own sequence.

Concurrent double-publish protection is the migration's
``UNIQUE (tenant_id, category_id, version)`` constraint, not application
code — allocating ``version`` via ``current_spec_version + 1`` is
check-then-act, so two concurrent publishes racing the same category both
compute the same next version, and the constraint turns the loser's insert
into a loud ``IntegrityError`` (rolling back its whole transaction, stamps
included) rather than two rows silently claiming the same version.

Change classification (D15's additive/required/retire/rename buckets) and
``needs_attention`` propagation are the next chunk and M4 respectively — a
category's first few publishes have no prior version to classify against,
and nothing reads ``change_summary`` yet.
"""

from __future__ import annotations

from app.entities.category_spec_version import CategorySpecVersion
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.spec_snapshot_builder import SpecSnapshotBuilder
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId, UserId


class PublishCategorySpec:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        category_id: CategoryId,
        actor_user_id: UserId,
    ) -> CategorySpecVersion:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")

            builder = SpecSnapshotBuilder(
                uow.categories,
                uow.attribute_definitions,
                uow.variant_axes,
                uow.variant_axis_values,
                uow.input_image_slots,
                uow.catalog_image_slots,
                uow.catalog_slot_input_requirements,
            )
            snapshot = await builder.build(tenant_id, category_id)

            previous_version = category.current_spec_version
            next_version = (previous_version or 0) + 1

            for definition in await uow.attribute_definitions.list_for_category(
                tenant_id, category_id
            ):
                if definition.introduced_in_version is None:
                    definition.introduced_in_version = next_version
                    await uow.attribute_definitions.update(definition)

            for axis in await uow.variant_axes.list_for_category(tenant_id, category_id):
                if axis.introduced_in_version is None:
                    axis.introduced_in_version = next_version
                    await uow.variant_axes.update(axis)

            for input_slot in await uow.input_image_slots.list_for_category(tenant_id, category_id):
                if input_slot.introduced_in_version is None:
                    input_slot.introduced_in_version = next_version
                    await uow.input_image_slots.update(input_slot)

            for catalog_slot in await uow.catalog_image_slots.list_for_category(
                tenant_id, category_id
            ):
                if catalog_slot.introduced_in_version is None:
                    catalog_slot.introduced_in_version = next_version
                    await uow.catalog_image_slots.update(catalog_slot)

            version = CategorySpecVersion.create(
                tenant_id,
                category_id,
                version=next_version,
                snapshot=snapshot,
                published_by=actor_user_id,
                now=now,
            )
            await uow.category_spec_versions.add(version)

            category.current_spec_version = next_version
            category.draft_spec_version = None
            category.updated_at = now
            await uow.categories.update(category)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="category_spec.published",
                subject_type="category",
                subject_id=category_id,
                before={"current_spec_version": previous_version},
                after={"current_spec_version": next_version},
                now=now,
            )

            return version
