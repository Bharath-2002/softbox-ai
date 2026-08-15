"""The storefront's view of ``ListCategoryChildren`` (D10, M8): active
categories only. A separate use case rather than an ``is_active`` parameter
on the admin one — the admin tree management view needs to see an inactive
category to reactivate it; a shopper must never see it at all. Two call
shapes for two different visibility rules, not one method with a flag that
would let a future caller forget to set it.
"""

from __future__ import annotations

from app.entities.category import Category
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CategoryId, TenantId


class ListPublicCategoryChildren:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, parent_id: CategoryId | None
    ) -> list[Category]:
        async with self._uow_factory(tenant_id) as uow:
            children = await uow.categories.list_children(tenant_id, parent_id)
            return [category for category in children if category.is_active]
