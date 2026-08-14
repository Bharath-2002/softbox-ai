from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category_spec_version import CategorySpecVersion
from app.entities.product import Product
from app.features.products.create_product_variant import CreateProductVariant
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import new_category_id, new_product_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_SNAPSHOT = {
    "attribute_definitions": [],
    "variant_axes": [
        {
            "id": "axis-1",
            "key": "colour",
            "label": "Colour",
            "position": 0,
            "affects_imagery": True,
            "values": [
                {"id": "v1", "value": "maroon", "label": "Maroon", "metadata": {}},
            ],
        }
    ],
    "input_image_slots": [],
    "catalog_image_slots": [],
}


def _use_case() -> tuple[CreateProductVariant, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CreateProductVariant(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_product(uow_factory: FakeUnitOfWorkFactory, tenant_id: object) -> Product:
    category_id = new_category_id()
    user_id = new_user_id()
    spec_version = CategorySpecVersion.create(
        tenant_id, category_id, version=1, snapshot=_SNAPSHOT, published_by=user_id, now=_NOW
    )
    await uow_factory.category_spec_versions.add(spec_version)
    product = Product.create(
        tenant_id, category_id, spec_version.id, attributes={}, created_by=user_id, now=_NOW
    )
    await uow_factory.products.add(product)
    return product


async def test_creating_a_variant_with_a_valid_axis_value_succeeds() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product = await _seed_product(uow_factory, tenant_id)

    variant = await use_case(
        tenant_id=tenant_id,
        product_id=product.id,
        axis_values={"colour": "maroon"},
        created_by=new_user_id(),
    )

    assert variant.axis_values == {"colour": "maroon"}
    assert variant.product_id == product.id
    stored = await uow_factory.product_variants.get(tenant_id, variant.id)
    assert stored is not None


async def test_creating_a_variant_with_an_unknown_axis_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product = await _seed_product(uow_factory, tenant_id)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            axis_values={"fabric": "silk"},
            created_by=new_user_id(),
        )


async def test_creating_a_variant_with_a_disallowed_value_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product = await _seed_product(uow_factory, tenant_id)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            axis_values={"colour": "gold"},
            created_by=new_user_id(),
        )


async def test_creating_a_variant_for_an_unknown_product_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            product_id=new_product_id(),
            axis_values={},
            created_by=new_user_id(),
        )
