"""Fetches the live D10-D13 tables for one category's ancestor chain,
resolves inheritance (D10), and serializes the result into D15's snapshot
shape (``spec_snapshot.build_snapshot``).

The I/O-bound counterpart to that pure function — same shape as
``PrincipalResolver``: repository ports injected directly, not a
``UnitOfWork``, so this class opens no transaction of its own and can be
called from inside whatever transaction its caller already holds open. 5b's
publish flow constructs one from an open ``uow``'s repository properties and
calls it from inside its own transaction, before writing the
``category_spec_versions`` row.
"""

from __future__ import annotations

from typing import Any

from app.services.ports.attribute_definition_repository import AttributeDefinitionRepository
from app.services.ports.catalog_image_slot_repository import CatalogImageSlotRepository
from app.services.ports.catalog_slot_input_requirement_repository import (
    CatalogSlotInputRequirementRepository,
)
from app.services.ports.category_repository import CategoryRepository
from app.services.ports.input_image_slot_repository import InputImageSlotRepository
from app.services.ports.variant_axis_repository import VariantAxisRepository
from app.services.ports.variant_axis_value_repository import VariantAxisValueRepository
from app.services.spec_inheritance import resolve_inherited
from app.services.spec_snapshot import build_snapshot
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId


class SpecSnapshotBuilder:
    def __init__(
        self,
        categories: CategoryRepository,
        attribute_definitions: AttributeDefinitionRepository,
        variant_axes: VariantAxisRepository,
        variant_axis_values: VariantAxisValueRepository,
        input_image_slots: InputImageSlotRepository,
        catalog_image_slots: CatalogImageSlotRepository,
        catalog_slot_input_requirements: CatalogSlotInputRequirementRepository,
    ) -> None:
        self._categories = categories
        self._attribute_definitions = attribute_definitions
        self._variant_axes = variant_axes
        self._variant_axis_values = variant_axis_values
        self._input_image_slots = input_image_slots
        self._catalog_image_slots = catalog_image_slots
        self._catalog_slot_input_requirements = catalog_slot_input_requirements

    async def build(self, tenant_id: TenantId, category_id: CategoryId) -> dict[str, Any]:
        category = await self._categories.get(tenant_id, category_id)
        if category is None:
            raise NotFoundError("Category not found.")
        chain = category.ancestor_ids()

        attribute_definitions = resolve_inherited(
            chain, await self._attribute_definitions.list_for_categories(tenant_id, chain)
        )
        variant_axes = resolve_inherited(
            chain, await self._variant_axes.list_for_categories(tenant_id, chain)
        )
        input_image_slots = resolve_inherited(
            chain, await self._input_image_slots.list_for_categories(tenant_id, chain)
        )
        catalog_image_slots = resolve_inherited(
            chain, await self._catalog_image_slots.list_for_categories(tenant_id, chain)
        )

        # Values/requirements are not category-owned (D12/D13) -
        # resolve_inherited does not apply to them. Fetch only for the
        # winning axis/slot ids the merge above already chose, never for
        # every axis/slot across the whole ancestor chain - that would pull
        # in values belonging to an axis or slot a descendant overrode.
        variant_axis_values = {
            axis.id: await self._variant_axis_values.list_for_axis(tenant_id, axis.id)
            for axis in variant_axes.values()
        }
        catalog_slot_input_requirements = {
            slot.id: await self._catalog_slot_input_requirements.list_for_catalog_slot(
                tenant_id, slot.id
            )
            for slot in catalog_image_slots.values()
        }

        return build_snapshot(
            attribute_definitions=list(attribute_definitions.values()),
            variant_axes=list(variant_axes.values()),
            variant_axis_values=variant_axis_values,
            input_image_slots=list(input_image_slots.values()),
            catalog_image_slots=list(catalog_image_slots.values()),
            catalog_slot_input_requirements=catalog_slot_input_requirements,
        )
