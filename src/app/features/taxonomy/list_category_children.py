"""Lists a category's direct children, or every root category when
``parent_id`` is ``None``.

No cursor pagination (CLAUDE.md §9's default) — deliberately: a tenant's
category tree is an admin-configured hierarchy, not an open-ended,
user-generated collection like a product or generation listing, so its
sibling count is naturally bounded rather than something to page through.
Revisit if a real tenant's usage ever proves that assumption wrong.
"""

from __future__ import annotations

from app.entities.category import Category
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CategoryId, TenantId


class ListCategoryChildren:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, parent_id: CategoryId | None
    ) -> list[Category]:
        async with self._uow_factory(tenant_id) as uow:
            return await uow.categories.list_children(tenant_id, parent_id)
