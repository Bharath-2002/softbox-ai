from __future__ import annotations

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id


def test_a_new_definition_has_no_version_stamps_yet() -> None:
    definition = AttributeDefinition.create(
        new_tenant_id(),
        new_category_id(),
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )

    assert definition.introduced_in_version is None
    assert definition.retired_in_version is None


def test_defaults_are_optional_and_not_required_or_filterable() -> None:
    definition = AttributeDefinition.create(
        new_tenant_id(),
        new_category_id(),
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )

    assert definition.is_required is False
    assert definition.is_filterable is False
    assert definition.is_public is True
    assert definition.semantic_role is None
    assert definition.validation == {}
    assert definition.ui == {}


def test_a_semantic_role_can_be_attached() -> None:
    definition = AttributeDefinition.create(
        new_tenant_id(),
        new_category_id(),
        key="price",
        label="Price",
        data_type=AttributeDataType.MONEY,
        semantic_role=SemanticRole.PRICE,
        is_required=True,
        is_filterable=True,
        now=utcnow(),
    )

    assert definition.semantic_role == SemanticRole.PRICE
    assert definition.is_required is True
    assert definition.is_filterable is True
