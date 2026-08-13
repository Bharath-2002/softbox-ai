"""The sharing join's storage (D13). Tenant id is explicit on every method.

``list_for_input_slot`` is the reverse lookup D13's admin-UI affordance
needs — "attach an existing pool slot to a second catalog slot in one
click" means finding every catalog slot an input is *not yet* attached to,
which starts from "every catalog slot it *is* attached to."
"""

from __future__ import annotations

from typing import Protocol

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.shared.ids import CatalogImageSlotId, InputImageSlotId, TenantId


class CatalogSlotInputRequirementRepository(Protocol):
    async def get(
        self,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
    ) -> CatalogSlotInputRequirement | None: ...

    async def add(self, requirement: CatalogSlotInputRequirement) -> None: ...

    async def update(self, requirement: CatalogSlotInputRequirement) -> None: ...

    async def remove(
        self,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
    ) -> None: ...

    async def list_for_catalog_slot(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId
    ) -> list[CatalogSlotInputRequirement]:
        """Every input this catalog slot requires, ordered by
        ``prompt_position`` — the ``{{input.0}}``, ``{{input.1}}``, ...
        order a D14 template renders in."""
        ...

    async def list_for_input_slot(
        self, tenant_id: TenantId, input_image_slot_id: InputImageSlotId
    ) -> list[CatalogSlotInputRequirement]: ...
