"""Proves the wiring across three separately-tested use cases actually
connects: the `input_image_slot_id` `CaptureProductInputImage` writes is the
same value `compute_product_readiness` (via `RecomputeProductReadiness`)
looks up when resolving a required slot. Each piece has its own unit tests
already; this is the first test that walks capture -> validate -> recompute
as one chain, which is exactly the shape M5's generation fan-out will rely
on.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.entities.asset import Asset, AssetKind
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.product import Product, ProductStatus
from app.features.products.capture_product_input_image import CaptureProductInputImage
from app.features.products.recompute_product_readiness import RecomputeProductReadiness
from app.shared.ids import new_category_id, new_input_image_slot_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_a_captured_and_validated_image_satisfies_readiness_for_its_slot() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    capture = CaptureProductInputImage(uow_factory, clock)
    recompute = RecomputeProductReadiness(uow_factory, clock)

    tenant_id = new_tenant_id()
    category_id = new_category_id()
    user_id = new_user_id()
    slot_id = new_input_image_slot_id()

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

    image = await capture(
        tenant_id=tenant_id,
        product_id=product.id,
        input_image_slot_id=slot_id,
        asset_id=asset.id,
        created_by=user_id,
    )
    image.start_validating(now=_NOW)
    image.mark_ready(now=_NOW)
    await uow_factory.product_input_images.update(image)

    result = await recompute(tenant_id=tenant_id, product_id=product.id)

    assert result.status == ProductStatus.READY
