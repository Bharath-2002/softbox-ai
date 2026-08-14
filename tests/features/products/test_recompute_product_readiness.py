from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.entities.category_spec_version import CategorySpecVersion
from app.entities.product import Product, ProductStatus
from app.features.products.recompute_product_readiness import RecomputeProductReadiness
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_product_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _snapshot(
    *, required_attribute_key: str | None, required_slot_id: str | None
) -> dict[str, Any]:
    attribute_definitions: list[dict[str, Any]] = []
    if required_attribute_key is not None:
        attribute_definitions.append(
            {
                "id": "irrelevant",
                "category_id": "irrelevant",
                "key": required_attribute_key,
                "label": required_attribute_key,
                "help_text": None,
                "data_type": "text",
                "semantic_role": None,
                "is_required": True,
                "is_filterable": False,
                "is_public": True,
                "position": 0,
                "validation": {},
                "ui": {},
                "default_value": None,
            }
        )
    input_image_slots: list[dict[str, Any]] = []
    if required_slot_id is not None:
        input_image_slots.append(
            {
                "id": required_slot_id,
                "category_id": "irrelevant",
                "key": "garment_body",
                "label": "Garment body",
                "description": None,
                "capture_guidance": None,
                "example_asset_id": None,
                "normalisation": {},
                "is_required": True,
                "position": 0,
            }
        )
    return {
        "attribute_definitions": attribute_definitions,
        "variant_axes": [],
        "input_image_slots": input_image_slots,
        "catalog_image_slots": [],
    }


def _use_case() -> tuple[RecomputeProductReadiness, FakeUnitOfWorkFactory, FakeClock]:
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    return RecomputeProductReadiness(uow_factory, clock), uow_factory, clock


async def _seed(
    uow_factory: FakeUnitOfWorkFactory, *, snapshot: dict[str, Any], attributes: dict[str, Any]
) -> tuple[Any, Product]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    user_id = new_user_id()
    spec_version = CategorySpecVersion.create(
        tenant_id,
        category_id,
        version=1,
        snapshot=snapshot,
        published_by=user_id,
        now=_NOW,
    )
    await uow_factory.category_spec_versions.add(spec_version)
    product = Product.create(
        tenant_id,
        category_id,
        spec_version.id,
        attributes=attributes,
        created_by=user_id,
        now=_NOW,
    )
    await uow_factory.products.add(product)
    return tenant_id, product


async def test_a_product_with_every_requirement_satisfied_becomes_ready() -> None:
    use_case, uow_factory, _clock = _use_case()
    tenant_id, product = await _seed(
        uow_factory,
        snapshot=_snapshot(required_attribute_key="fabric", required_slot_id=None),
        attributes={"fabric": "tissue"},
    )

    result = await use_case(tenant_id=tenant_id, product_id=product.id)

    assert result.status == ProductStatus.READY


async def test_a_product_missing_a_required_attribute_stays_draft() -> None:
    use_case, uow_factory, _clock = _use_case()
    tenant_id, product = await _seed(
        uow_factory,
        snapshot=_snapshot(required_attribute_key="fabric", required_slot_id=None),
        attributes={},
    )

    result = await use_case(tenant_id=tenant_id, product_id=product.id)

    assert result.status == ProductStatus.DRAFT


async def test_recomputing_an_already_ready_product_that_regressed_needs_attention() -> None:
    use_case, uow_factory, clock = _use_case()
    tenant_id, product = await _seed(
        uow_factory,
        snapshot=_snapshot(required_attribute_key="fabric", required_slot_id=None),
        attributes={"fabric": "tissue"},
    )
    await use_case(tenant_id=tenant_id, product_id=product.id)
    assert product.status == ProductStatus.READY

    product.attributes = {}
    clock.advance(timedelta(seconds=1))

    result = await use_case(tenant_id=tenant_id, product_id=product.id)

    assert result.status == ProductStatus.NEEDS_ATTENTION


async def test_readiness_is_computed_against_the_pinned_snapshot_not_a_republished_one() -> None:
    """The Gate bullet this test exists for: `ready` reflects the pinned
    spec version, not whatever the category's spec looks like now."""
    use_case, uow_factory, _clock = _use_case()
    tenant_id, product = await _seed(
        uow_factory,
        snapshot=_snapshot(required_attribute_key=None, required_slot_id=None),
        attributes={},
    )
    first_result = await use_case(tenant_id=tenant_id, product_id=product.id)
    assert first_result.status == ProductStatus.READY

    # A new spec version publishes, adding a required field this product
    # does not have - the product's own `spec_version_id` never moves.
    category_id = product.category_id
    new_version = CategorySpecVersion.create(
        tenant_id,
        category_id,
        version=2,
        snapshot=_snapshot(required_attribute_key="fabric", required_slot_id=None),
        published_by=product.created_by,
        now=_NOW,
    )
    await uow_factory.category_spec_versions.add(new_version)

    result = await use_case(tenant_id=tenant_id, product_id=product.id)

    assert result.status == ProductStatus.READY
    assert result.spec_version_id == first_result.spec_version_id


async def test_recomputing_an_unknown_product_is_not_found() -> None:
    use_case, _uow_factory, _clock = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), product_id=new_product_id())
