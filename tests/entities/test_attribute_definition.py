from __future__ import annotations

import pytest

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
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


@pytest.mark.parametrize(
    "bad_key", ["Fabric", "1fabric", "fabric type", "fabric-type", "fabric.type", ""]
)
def test_a_key_that_is_not_a_safe_identifier_is_rejected(bad_key: str) -> None:
    with pytest.raises(ValidationError, match="Attribute key"):
        AttributeDefinition.create(
            new_tenant_id(),
            new_category_id(),
            key=bad_key,
            label="Fabric",
            data_type=AttributeDataType.TEXT,
            now=utcnow(),
        )


def test_a_lowercase_snake_case_key_is_accepted() -> None:
    definition = AttributeDefinition.create(
        new_tenant_id(),
        new_category_id(),
        key="fabric_type_2",
        label="Fabric type",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )

    assert definition.key == "fabric_type_2"
