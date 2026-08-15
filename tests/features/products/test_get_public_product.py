from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.product import Product, ProductStatus
from app.features.products.get_public_product import GetPublicProduct
from app.shared.errors import NotFoundError
from app.shared.ids import (
    TenantId,
    new_category_id,
    new_category_spec_version_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _product(tenant_id: TenantId, status: ProductStatus) -> Product:
    product = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )
    product.status = status
    return product


async def test_returns_a_published_product() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id = new_tenant_id()
    product = _product(tenant_id, ProductStatus.PUBLISHED)
    await uow_factory.products.add(product)
    use_case = GetPublicProduct(uow_factory)

    fetched = await use_case(tenant_id=tenant_id, product_id=product.id)

    assert fetched.id == product.id


async def test_a_draft_product_is_not_found() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id = new_tenant_id()
    product = _product(tenant_id, ProductStatus.DRAFT)
    await uow_factory.products.add(product)
    use_case = GetPublicProduct(uow_factory)

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=tenant_id, product_id=product.id)


async def test_an_unknown_product_is_not_found() -> None:
    use_case = GetPublicProduct(FakeUnitOfWorkFactory())

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), product_id=new_product_id())
