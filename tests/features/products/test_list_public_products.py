from __future__ import annotations

from datetime import UTC, datetime

from app.entities.product import Product, ProductStatus
from app.features.products.list_public_products import ListPublicProducts
from app.shared.ids import new_category_id, new_category_spec_version_id, new_tenant_id, new_user_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_lists_only_published_products() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id = new_tenant_id()
    published = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )
    published.status = ProductStatus.PUBLISHED
    draft = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.products.add(published)
    await uow_factory.products.add(draft)
    use_case = ListPublicProducts(uow_factory)

    page = await use_case(tenant_id=tenant_id)

    assert [p.id for p in page.items] == [published.id]
