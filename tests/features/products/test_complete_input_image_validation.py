from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.product_input_image import InputImageStatus, ProductInputImage
from app.features.products.complete_input_image_validation import CompleteInputImageValidation
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_asset_id,
    new_input_image_slot_id,
    new_product_id,
    new_product_input_image_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[CompleteInputImageValidation, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CompleteInputImageValidation(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_validating_image(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: object
) -> ProductInputImage:
    image = ProductInputImage.create(
        tenant_id,
        new_product_id(),
        input_image_slot_id=new_input_image_slot_id(),
        asset_id=new_asset_id(),
        created_by=new_user_id(),
        now=_NOW,
    )
    image.start_validating(now=_NOW)
    await uow_factory.product_input_images.add(image)
    return image


async def test_a_passing_verdict_marks_the_image_ready() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    image = await _seed_validating_image(uow_factory, tenant_id)

    result = await use_case(tenant_id=tenant_id, image_id=image.id, passed=True, reason=None)

    assert result.status == InputImageStatus.READY


async def test_a_failing_verdict_rejects_with_the_given_reason() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    image = await _seed_validating_image(uow_factory, tenant_id)

    result = await use_case(
        tenant_id=tenant_id, image_id=image.id, passed=False, reason="too blurry"
    )

    assert result.status == InputImageStatus.REJECTED
    assert result.rejection_reason == "too blurry"


async def test_completing_validation_for_an_unknown_image_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            image_id=new_product_input_image_id(),
            passed=True,
            reason=None,
        )
