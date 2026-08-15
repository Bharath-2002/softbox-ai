"""A single storefront product page (D11, M8). Unlike the paginated list,
filtering after the fetch is fine here — there is no page boundary to
break, and ``NotFoundError`` for "exists but not published" is exactly the
same "do not distinguish missing from someone else's" reasoning applied to
visibility instead of tenancy: a product a shopper should not see behaves
identically to one that does not exist.
"""

from __future__ import annotations

from app.entities.product import Product, ProductStatus
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.errors import NotFoundError
from app.shared.ids import ProductId, TenantId


class GetPublicProduct:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, tenant_id: TenantId, product_id: ProductId) -> Product:
        async with self._uow_factory(tenant_id) as uow:
            product = await uow.products.get(tenant_id, product_id)
            if product is None or product.status is not ProductStatus.PUBLISHED:
                raise NotFoundError("Product not found.")
            return product
