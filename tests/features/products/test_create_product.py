from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.product import ProductStatus
from app.features.products.create_product import CreateProduct
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[CreateProduct, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CreateProduct(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_published_category(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: object
) -> Category:
    category = Category.create(
        tenant_id, key="dresses", name="Dresses", slug="dresses", parent=None, now=_NOW
    )
    spec_version = CategorySpecVersion.create(
        tenant_id,
        category.id,
        version=1,
        snapshot={
            "attribute_definitions": [],
            "variant_axes": [],
            "input_image_slots": [],
            "catalog_image_slots": [],
        },
        published_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.category_spec_versions.add(spec_version)
    category.current_spec_version = spec_version.version
    await uow_factory.categories.add(category)
    return category


def _definitions(tenant_id: object, category_id: object) -> list[AttributeDefinition]:
    return [
        AttributeDefinition.create(
            tenant_id,
            category_id,
            key="product_title",
            label="Title",
            data_type=AttributeDataType.TEXT,
            semantic_role=SemanticRole.TITLE,
            is_required=True,
            now=_NOW,
        ),
        AttributeDefinition.create(
            tenant_id,
            category_id,
            key="product_sku",
            label="SKU",
            data_type=AttributeDataType.TEXT,
            semantic_role=SemanticRole.SKU,
            is_required=True,
            now=_NOW,
        ),
        AttributeDefinition.create(
            tenant_id,
            category_id,
            key="product_price",
            label="Price",
            data_type=AttributeDataType.MONEY,
            semantic_role=SemanticRole.PRICE,
            is_required=True,
            now=_NOW,
        ),
        AttributeDefinition.create(
            tenant_id,
            category_id,
            key="notes",
            label="Notes",
            data_type=AttributeDataType.TEXT,
            is_required=False,
            now=_NOW,
        ),
    ]


async def test_creating_a_product_validates_and_promotes_semantic_columns() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    user_id = new_user_id()
    category = await _seed_published_category(uow_factory, tenant_id)
    for definition in _definitions(tenant_id, category.id):
        await uow_factory.attribute_definitions.add(definition)

    product = await use_case(
        tenant_id=tenant_id,
        category_id=category.id,
        attributes={
            "product_title": "Blue Cotton Dress",
            "product_sku": "BCD-001",
            "product_price": 249900,
        },
        created_by=user_id,
    )

    assert product.title == "Blue Cotton Dress"
    assert product.sku == "BCD-001"
    assert product.price_amount == 249900
    assert product.price_currency is None
    assert product.status == ProductStatus.DRAFT
    assert product.spec_version_id is not None
    stored = await uow_factory.products.get(tenant_id, product.id)
    assert stored is not None


async def test_creating_a_product_missing_a_required_attribute_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category = await _seed_published_category(uow_factory, tenant_id)
    for definition in _definitions(tenant_id, category.id):
        await uow_factory.attribute_definitions.add(definition)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            category_id=category.id,
            attributes={"product_title": "Blue Cotton Dress"},
            created_by=new_user_id(),
        )


async def test_creating_a_product_for_an_unknown_category_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            category_id=new_category_id(),
            attributes={},
            created_by=new_user_id(),
        )


async def test_creating_a_product_for_a_category_with_no_published_spec_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category = Category.create(
        tenant_id, key="dresses", name="Dresses", slug="dresses", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            category_id=category.id,
            attributes={},
            created_by=new_user_id(),
        )
