"""The storefront's view of ``ListProducts`` (D11, M8): published products
only, via ``ProductRepository.list_published_page`` rather than a filter
applied here — filtering after the query would break cursor pagination's
own page-boundary and ``has_more`` accounting for the exact rows this
method exists to exclude.
"""

from __future__ import annotations

from app.entities.product import Product
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CategoryId, TenantId
from app.shared.pagination import Cursor, Page, decode_cursor, encode_cursor

_DEFAULT_LIMIT = 20


class ListPublicProducts:
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
            rows = await uow.products.list_published_page(
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
