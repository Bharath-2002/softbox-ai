from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.entities.product import Product
from app.features.products.list_products import ListProducts
from app.shared.ids import new_category_id, new_category_spec_version_id, new_tenant_id, new_user_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[ListProducts, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return ListProducts(uow_factory), uow_factory


async def _seed(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: object, category_id: object, count: int
) -> list[Product]:
    products = []
    for i in range(count):
        product = Product.create(
            tenant_id,
            category_id,
            new_category_spec_version_id(),
            attributes={},
            created_by=new_user_id(),
            now=_BASE + timedelta(seconds=i),
        )
        await uow_factory.products.add(product)
        products.append(product)
    return products


async def test_first_page_returns_up_to_the_limit_in_order() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    products = await _seed(uow_factory, tenant_id, category_id, 3)

    page = await use_case(tenant_id=tenant_id, category_id=category_id, limit=2)

    assert [p.id for p in page.items] == [products[0].id, products[1].id]
    assert page.next_cursor is not None


async def test_following_the_cursor_reaches_the_last_page() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    products = await _seed(uow_factory, tenant_id, category_id, 3)

    first_page = await use_case(tenant_id=tenant_id, category_id=category_id, limit=2)
    second_page = await use_case(
        tenant_id=tenant_id, category_id=category_id, cursor=first_page.next_cursor, limit=2
    )

    assert [p.id for p in second_page.items] == [products[2].id]
    assert second_page.next_cursor is None


async def test_a_page_that_exactly_fills_the_limit_has_no_next_cursor() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    await _seed(uow_factory, tenant_id, category_id, 2)

    page = await use_case(tenant_id=tenant_id, category_id=category_id, limit=2)

    assert len(page.items) == 2
    assert page.next_cursor is None


async def test_no_category_filter_spans_categories() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    await _seed(uow_factory, tenant_id, new_category_id(), 1)
    await _seed(uow_factory, tenant_id, new_category_id(), 1)

    page = await use_case(tenant_id=tenant_id, limit=10)

    assert len(page.items) == 2
