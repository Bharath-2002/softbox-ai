from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.entities.asset import Asset, AssetKind
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.product import Product
from app.entities.product_input_image import InputImageStatus
from app.entities.product_variant import ProductVariant
from app.features.products.capture_product_input_image import CaptureProductInputImage
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import (
    InputImageSlotId,
    new_asset_id,
    new_category_id,
    new_input_image_slot_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[CaptureProductInputImage, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CaptureProductInputImage(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_product(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: object, *, slot_id: InputImageSlotId
) -> Product:
    category_id = new_category_id()
    user_id = new_user_id()
    spec_version = CategorySpecVersion.create(
        tenant_id,
        category_id,
        version=1,
        snapshot={
            "attribute_definitions": [],
            "variant_axes": [],
            "input_image_slots": [
                {
                    "id": str(slot_id),
                    "category_id": str(category_id),
                    "key": "front",
                    "label": "Front",
                    "description": None,
                    "capture_guidance": None,
                    "example_asset_id": None,
                    "normalisation": {},
                    "is_required": True,
                    "position": 0,
                }
            ],
            "catalog_image_slots": [],
        },
        published_by=user_id,
        now=_NOW,
    )
    await uow_factory.category_spec_versions.add(spec_version)
    product = Product.create(
        tenant_id, category_id, spec_version.id, attributes={}, created_by=user_id, now=_NOW
    )
    await uow_factory.products.add(product)
    return product


async def _seed_input_asset(uow_factory: FakeUnitOfWorkFactory, tenant_id: object) -> Asset:
    asset = Asset.create(
        tenant_id,
        storage_key=f"tenants/x/input/{uuid.uuid4()}.jpg",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=204_800,
        kind=AssetKind.INPUT,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(asset)
    return asset


async def test_capturing_binds_the_asset_to_the_product_as_captured() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot_id = new_input_image_slot_id()
    product = await _seed_product(uow_factory, tenant_id, slot_id=slot_id)
    asset = await _seed_input_asset(uow_factory, tenant_id)

    image = await use_case(
        tenant_id=tenant_id,
        product_id=product.id,
        input_image_slot_id=slot_id,
        asset_id=asset.id,
        created_by=new_user_id(),
    )

    assert image.status == InputImageStatus.CAPTURED
    assert image.asset_id == asset.id
    assert image.variant_id is None
    stored = await uow_factory.product_input_images.get(tenant_id, image.id)
    assert stored is not None


async def test_capturing_for_a_variant_records_the_variant_id() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot_id = new_input_image_slot_id()
    product = await _seed_product(uow_factory, tenant_id, slot_id=slot_id)
    asset = await _seed_input_asset(uow_factory, tenant_id)
    variant = ProductVariant.create(
        tenant_id, product.id, axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)

    image = await use_case(
        tenant_id=tenant_id,
        product_id=product.id,
        input_image_slot_id=slot_id,
        asset_id=asset.id,
        created_by=new_user_id(),
        variant_id=variant.id,
    )

    assert image.variant_id == variant.id


async def test_capturing_with_a_slot_not_in_the_products_spec_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product = await _seed_product(uow_factory, tenant_id, slot_id=new_input_image_slot_id())
    asset = await _seed_input_asset(uow_factory, tenant_id)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            input_image_slot_id=new_input_image_slot_id(),
            asset_id=asset.id,
            created_by=new_user_id(),
        )


async def test_capturing_a_non_input_asset_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot_id = new_input_image_slot_id()
    product = await _seed_product(uow_factory, tenant_id, slot_id=slot_id)
    template_asset = Asset.create(
        tenant_id,
        storage_key=f"tenants/x/template/{uuid.uuid4()}.jpg",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=204_800,
        kind=AssetKind.TEMPLATE,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(template_asset)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            input_image_slot_id=slot_id,
            asset_id=template_asset.id,
            created_by=new_user_id(),
        )


async def test_capturing_for_an_unknown_product_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    asset = await _seed_input_asset(uow_factory, tenant_id)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            product_id=new_product_id(),
            input_image_slot_id=new_input_image_slot_id(),
            asset_id=asset.id,
            created_by=new_user_id(),
        )


async def test_capturing_with_an_unknown_asset_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot_id = new_input_image_slot_id()
    product = await _seed_product(uow_factory, tenant_id, slot_id=slot_id)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            input_image_slot_id=slot_id,
            asset_id=new_asset_id(),
            created_by=new_user_id(),
        )


async def test_capturing_for_a_variant_belonging_to_a_different_product_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot_id = new_input_image_slot_id()
    product = await _seed_product(uow_factory, tenant_id, slot_id=slot_id)
    other_product = await _seed_product(uow_factory, tenant_id, slot_id=new_input_image_slot_id())
    asset = await _seed_input_asset(uow_factory, tenant_id)
    variant = ProductVariant.create(
        tenant_id, other_product.id, axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            input_image_slot_id=slot_id,
            asset_id=asset.id,
            created_by=new_user_id(),
            variant_id=variant.id,
        )
