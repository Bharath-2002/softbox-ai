from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.entities.product import Product, ProductStatus
from app.entities.product_variant import ProductVariant
from app.features.generation.list_public_catalog_images_for_product import (
    ListPublicCatalogImagesForProduct,
)
from app.shared.errors import NotFoundError
from app.shared.ids import (
    ProductId,
    ProductVariantId,
    TenantId,
    new_asset_id,
    new_catalog_image_slot_id,
    new_category_id,
    new_category_spec_version_id,
    new_generation_item_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed_published_product(
    uow_factory: FakeUnitOfWorkFactory,
) -> tuple[TenantId, ProductId, ProductVariantId]:
    tenant_id = new_tenant_id()
    product = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )
    product.status = ProductStatus.PUBLISHED
    await uow_factory.products.add(product)
    variant = ProductVariant.create(
        tenant_id, product.id, axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    return tenant_id, product.id, variant.id


async def test_lists_only_approved_images() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, product_id, variant_id = await _seed_published_product(uow_factory)
    approved = CatalogImage.create(
        tenant_id,
        variant_id,
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    approved.status = CatalogImageStatus.APPROVED
    pending = CatalogImage.create(
        tenant_id,
        variant_id,
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    await uow_factory.catalog_images.add(approved)
    await uow_factory.catalog_images.add(pending)
    use_case = ListPublicCatalogImagesForProduct(uow_factory)

    images = await use_case(tenant_id=tenant_id, product_id=product_id)

    assert [i.id for i in images] == [approved.id]


async def test_a_draft_products_images_are_not_found() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id = new_tenant_id()
    product = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.products.add(product)
    use_case = ListPublicCatalogImagesForProduct(uow_factory)

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=tenant_id, product_id=product.id)


async def test_an_unknown_products_images_are_not_found() -> None:
    use_case = ListPublicCatalogImagesForProduct(FakeUnitOfWorkFactory())

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), product_id=new_product_id())
