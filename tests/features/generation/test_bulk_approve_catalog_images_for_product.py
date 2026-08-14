from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.catalog_image import CatalogImage
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.features.generation.bulk_approve_catalog_images_for_product import (
    _BULK_LIMIT,
    BulkApproveCatalogImagesForProduct,
)
from app.shared.errors import ConflictError, NotFoundError
from app.shared.ids import (
    ProductId,
    TenantId,
    new_asset_id,
    new_catalog_image_slot_id,
    new_category_id,
    new_category_spec_version_id,
    new_generation_item_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[BulkApproveCatalogImagesForProduct, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return BulkApproveCatalogImagesForProduct(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_product(uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId) -> ProductId:
    product = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.products.add(product)
    return product.id


async def test_approves_every_pending_approval_image_for_the_product() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product_id = await _seed_product(uow_factory, tenant_id)
    variant = ProductVariant.create(
        tenant_id, product_id, axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)

    images = []
    for i in range(3):
        image = CatalogImage.create(
            tenant_id,
            variant.id,
            new_catalog_image_slot_id(),
            new_asset_id(),
            new_generation_item_id(),
            now=_NOW + timedelta(seconds=i),
        )
        image.mark_qc_passed(qc_result={}, now=_NOW)
        await uow_factory.catalog_images.add(image)
        images.append(image)

    approver = new_user_id()
    count = await use_case(tenant_id=tenant_id, product_id=product_id, approved_by=approver)

    assert count == 3
    for image in images:
        stored = await uow_factory.catalog_images.get(tenant_id, image.id)
        assert stored is not None
        assert stored.status.value == "approved"
        assert stored.approved_by == approver
    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "catalog_image", images[0].id)
    assert len(entries) == 1


async def test_ignores_images_for_a_different_product() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product_id = await _seed_product(uow_factory, tenant_id)
    other_product_id = await _seed_product(uow_factory, tenant_id)
    variant = ProductVariant.create(
        tenant_id, product_id, axis_values={}, created_by=new_user_id(), now=_NOW
    )
    other_variant = ProductVariant.create(
        tenant_id, other_product_id, axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    await uow_factory.product_variants.add(other_variant)

    other_image = CatalogImage.create(
        tenant_id,
        other_variant.id,
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    other_image.mark_qc_passed(qc_result={}, now=_NOW)
    await uow_factory.catalog_images.add(other_image)

    count = await use_case(tenant_id=tenant_id, product_id=product_id, approved_by=new_user_id())

    assert count == 0
    stored = await uow_factory.catalog_images.get(tenant_id, other_image.id)
    assert stored is not None
    assert stored.status.value == "pending_approval"


async def test_no_pending_images_approves_zero() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product_id = await _seed_product(uow_factory, tenant_id)

    count = await use_case(tenant_id=tenant_id, product_id=product_id, approved_by=new_user_id())

    assert count == 0


async def test_an_unknown_product_is_not_found() -> None:
    use_case, _uow_factory = _use_case()
    tenant_id = new_tenant_id()
    fake_product = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=tenant_id, product_id=fake_product.id, approved_by=new_user_id())


async def test_more_pending_images_than_the_bulk_limit_raises_instead_of_truncating() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product_id = await _seed_product(uow_factory, tenant_id)

    for i in range(_BULK_LIMIT + 1):
        variant = ProductVariant.create(
            tenant_id,
            product_id,
            axis_values={"colour": f"c{i}"},
            created_by=new_user_id(),
            now=_NOW,
        )
        await uow_factory.product_variants.add(variant)
        image = CatalogImage.create(
            tenant_id,
            variant.id,
            new_catalog_image_slot_id(),
            new_asset_id(),
            new_generation_item_id(),
            now=_NOW + timedelta(seconds=i),
        )
        image.mark_qc_passed(qc_result={}, now=_NOW)
        await uow_factory.catalog_images.add(image)

    with pytest.raises(ConflictError):
        await use_case(tenant_id=tenant_id, product_id=product_id, approved_by=new_user_id())
