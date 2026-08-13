"""Category taxonomy storage (D10). Tenant id is explicit on every method.

``list_subtree`` returns ``category_id`` plus every descendant — the exact
input ``app.services.category_hierarchy.reparent_subtree`` needs, and the
only way to enumerate "everything under this node" without walking
``parent_id`` one level at a time.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.category import Category
from app.shared.ids import CategoryId, TenantId


class CategoryRepository(Protocol):
    async def get(self, tenant_id: TenantId, category_id: CategoryId) -> Category | None: ...

    async def add(self, category: Category) -> None: ...

    async def update(self, category: Category) -> None: ...

    async def list_children(
        self, tenant_id: TenantId, parent_id: CategoryId | None
    ) -> list[Category]:
        """Direct children only, ordered by ``position``. ``parent_id=None``
        lists the tenant's root categories."""
        ...

    async def list_subtree(self, tenant_id: TenantId, category_id: CategoryId) -> list[Category]:
        """``category_id`` itself plus every descendant, ordered by ``path``
        so parents always precede their children."""
        ...
