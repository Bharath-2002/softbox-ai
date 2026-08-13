"""A single read, wrapped in the same transactional shape every other M2
use case uses — kept as its own use case rather than a repository call from
the router, so every HTTP-reachable read goes through `features`, not
`services`/`infrastructure` directly.
"""

from __future__ import annotations

from app.entities.category import Category
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId


class GetCategory:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, tenant_id: TenantId, category_id: CategoryId) -> Category:
        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")
            return category
