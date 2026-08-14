"""Lists a tenant's live (non-superseded) catalog images awaiting review,
cursor-paginated (CLAUDE.md §9) — the same shape `ListProducts` established
for `ProductRepository.list_page`. `status=None` (the default) lists every
live status, not just `pending_approval` — the approval-queue UI wants to
show a product's full current state (approved, rejected, still pending)
side by side, not just the ones still waiting.
"""

from __future__ import annotations

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import ProductId, TenantId
from app.shared.pagination import Cursor, Page, decode_cursor, encode_cursor

_DEFAULT_LIMIT = 20


class ListCatalogImagesForReview:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        status: CatalogImageStatus | None = None,
        product_id: ProductId | None = None,
        cursor: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> Page[CatalogImage]:
        after = decode_cursor(cursor) if cursor is not None else None
        async with self._uow_factory(tenant_id) as uow:
            rows = await uow.catalog_images.list_page(
                tenant_id, status=status, product_id=product_id, after=after, limit=limit + 1
            )

            has_more = len(rows) > limit
            items = rows[:limit]
            next_cursor = (
                encode_cursor(Cursor(sort_key=items[-1].created_at.isoformat(), id=items[-1].id))
                if has_more and items
                else None
            )
            return Page(items=items, next_cursor=next_cursor)
