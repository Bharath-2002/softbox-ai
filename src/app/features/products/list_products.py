"""Lists a tenant's products, cursor-paginated (CLAUDE.md §9) — the first
real caller of `shared.pagination` (built in M1, unused until now). A
product catalog is the open-ended, potentially-large collection that
module's docstring names as the reason offset pagination is disallowed.
"""

from __future__ import annotations

from app.entities.product import Product
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CategoryId, TenantId
from app.shared.pagination import Cursor, Page, decode_cursor, encode_cursor

_DEFAULT_LIMIT = 20


class ListProducts:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        category_id: CategoryId | None = None,
        cursor: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> Page[Product]:
        after = decode_cursor(cursor) if cursor is not None else None
        async with self._uow_factory(tenant_id) as uow:
            rows = await uow.products.list_page(
                tenant_id, category_id, after=after, limit=limit + 1
            )

            has_more = len(rows) > limit
            items = rows[:limit]
            next_cursor = (
                encode_cursor(Cursor(sort_key=items[-1].created_at.isoformat(), id=items[-1].id))
                if has_more and items
                else None
            )
            return Page(items=items, next_cursor=next_cursor)
