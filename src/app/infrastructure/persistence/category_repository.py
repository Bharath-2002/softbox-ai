"""Implements ``app.services.ports.category_repository.CategoryRepository``.

Filters use ``categories_table.c.*``, not the mapped class's own attributes —
see ``user_repository.py`` for why. ``list_subtree`` matches ``category_id``
itself (``path = :path``) or any row whose path starts with it followed by a
separator (``path LIKE :prefix``) — the ``.`` guards against ``cat-1``
falsely matching a sibling ``cat-10`` that merely shares a string prefix.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.category import Category
from app.infrastructure.persistence.mapping import categories_table
from app.shared.ids import CategoryId, TenantId


class SqlCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, category_id: CategoryId) -> Category | None:
        stmt = select(Category).where(
            categories_table.c.tenant_id == tenant_id,
            categories_table.c.id == category_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, category: Category) -> None:
        self._session.add(category)
        await self._session.flush()

    async def update(self, category: Category) -> None:
        # Same convention as user_repository.update: `category` is already
        # the identity-mapped instance, mutated in place by the caller (see
        # category_hierarchy.reparent_subtree) - flushing is the update.
        await self._session.flush()

    async def list_children(
        self, tenant_id: TenantId, parent_id: CategoryId | None
    ) -> list[Category]:
        stmt = (
            select(Category)
            .where(
                categories_table.c.tenant_id == tenant_id,
                categories_table.c.parent_id == parent_id
                if parent_id is not None
                else categories_table.c.parent_id.is_(None),
            )
            .order_by(categories_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_subtree(self, tenant_id: TenantId, category_id: CategoryId) -> list[Category]:
        root = await self.get(tenant_id, category_id)
        if root is None:
            return []
        stmt = (
            select(Category)
            .where(
                categories_table.c.tenant_id == tenant_id,
                or_(
                    categories_table.c.id == category_id,
                    categories_table.c.path.like(f"{root.path}.%"),
                ),
            )
            .order_by(categories_table.c.path)
        )
        return list((await self._session.execute(stmt)).scalars().all())
