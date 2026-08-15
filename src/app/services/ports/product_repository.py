"""Product storage (D11, D12). Same shape as ``CatalogTemplateRepository``.

No ``get_by_sku``/``get_by_title`` lookup yet — ``sku``/``title`` are
promoted, nullable columns (a category need not declare either semantic
role), so a uniqueness-backed lookup on either is a later use case's
concern, not this port's, until one actually needs it.

``list_page`` is CLAUDE.md §9's cursor pagination (``shared.pagination``,
built in M1 but with no real caller until ``ListProducts``) — a tenant's
product catalog is exactly the open-ended, potentially-large collection
that module's own docstring names as the reason offset pagination is
disallowed, unlike ``list_children``'s admin-configured, naturally-bounded
category tree. Ordered by ``(created_at, id)`` ascending, the same tiebreak
a ``Cursor`` encodes; ``category_id=None`` lists across every category.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.product import Product
from app.shared.ids import CategoryId, ProductId, TenantId
from app.shared.pagination import Cursor


class ProductRepository(Protocol):
    async def get(self, tenant_id: TenantId, product_id: ProductId) -> Product | None: ...

    async def add(self, product: Product) -> None: ...

    async def update(self, product: Product) -> None: ...

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[Product]: ...

    async def list_page(
        self,
        tenant_id: TenantId,
        category_id: CategoryId | None,
        *,
        after: Cursor | None,
        limit: int,
    ) -> list[Product]:
        """Up to ``limit`` rows strictly after ``after`` (``None`` starts
        from the beginning). Callers wanting to know if a next page exists
        should ask for ``limit + 1`` and trim — this method does no
        trimming or cursor-encoding of its own, matching ``Page``'s own
        division of labour."""
        ...

    async def list_published_page(
        self,
        tenant_id: TenantId,
        category_id: CategoryId | None,
        *,
        after: Cursor | None,
        limit: int,
    ) -> list[Product]:
        """The storefront's view of ``list_page``: ``status ==
        ProductStatus.PUBLISHED`` only, filtered at the query itself rather
        than by the caller — a cursor-paginated method that filtered after
        fetching would return short pages and break ``has_more`` for
        exactly the rows this method exists to exclude. A separate method
        rather than a ``status`` parameter on ``list_page``, matching
        ``ListPublicCategoryChildren``'s reasoning: a shared method with a
        visibility flag lets a future caller forget to set it."""
        ...
