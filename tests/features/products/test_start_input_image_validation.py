from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.asset import Asset, AssetKind
from app.entities.product_input_image import InputImageStatus, ProductInputImage
from app.features.products.start_input_image_validation import StartInputImageValidation
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_input_image_slot_id,
    new_product_id,
    new_product_input_image_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[StartInputImageValidation, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return StartInputImageValidation(uow_factory, FakeClock(_NOW)), uow_factory


async def test_starting_validation_transitions_captured_to_validating() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    asset = Asset.create(
        tenant_id,
        storage_key="tenants/x/input/a.jpg",
        sha256="a" * 64,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=204_800,
        kind=AssetKind.INPUT,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(asset)
    image = ProductInputImage.create(
        tenant_id,
        new_product_id(),
        input_image_slot_id=new_input_image_slot_id(),
        asset_id=asset.id,
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.product_input_images.add(image)

    ctx = await use_case(tenant_id=tenant_id, image_id=image.id)

    assert ctx.storage_key == asset.storage_key
    assert ctx.width == 1080
    assert ctx.height == 1350
    assert image.status == InputImageStatus.VALIDATING


async def test_starting_validation_for_an_unknown_image_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), image_id=new_product_input_image_id())
