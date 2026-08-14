from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.entities.product_variant import ProductVariant
from app.features.generation.list_catalog_images_for_review import ListCatalogImagesForReview
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_slot_id,
    new_generation_item_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[ListCatalogImagesForReview, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return ListCatalogImagesForReview(uow_factory), uow_factory


async def _seed(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: object, count: int, *, variant_id: object = None
) -> list[CatalogImage]:
    images = []
    for i in range(count):
        image = CatalogImage.create(
            tenant_id,
            variant_id or new_product_variant_id(),
            new_catalog_image_slot_id(),
            new_asset_id(),
            new_generation_item_id(),
            now=_BASE + timedelta(seconds=i),
        )
        await uow_factory.catalog_images.add(image)
        images.append(image)
    return images


async def test_first_page_returns_up_to_the_limit_in_order() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    images = await _seed(uow_factory, tenant_id, 3)

    page = await use_case(tenant_id=tenant_id, limit=2)

    assert [i.id for i in page.items] == [images[0].id, images[1].id]
    assert page.next_cursor is not None


async def test_following_the_cursor_reaches_the_last_page() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    images = await _seed(uow_factory, tenant_id, 3)

    first_page = await use_case(tenant_id=tenant_id, limit=2)
    second_page = await use_case(tenant_id=tenant_id, cursor=first_page.next_cursor, limit=2)

    assert [i.id for i in second_page.items] == [images[2].id]
    assert second_page.next_cursor is None


async def test_filters_by_status() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    images = await _seed(uow_factory, tenant_id, 2)
    images[0].mark_qc_passed(qc_result={}, now=_BASE)
    await uow_factory.catalog_images.update(images[0])

    page = await use_case(tenant_id=tenant_id, status=CatalogImageStatus.PENDING_APPROVAL)

    assert [i.id for i in page.items] == [images[0].id]


async def test_filters_by_product() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product_id = new_product_id()
    variant = ProductVariant.create(
        tenant_id, product_id, axis_values={}, created_by=new_user_id(), now=_BASE
    )
    await uow_factory.product_variants.add(variant)
    matching = await _seed(uow_factory, tenant_id, 1, variant_id=variant.id)
    await _seed(uow_factory, tenant_id, 1)  # a different, unrelated variant/product

    page = await use_case(tenant_id=tenant_id, product_id=product_id)

    assert [i.id for i in page.items] == [matching[0].id]
