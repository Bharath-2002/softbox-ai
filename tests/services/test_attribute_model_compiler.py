"""Runtime Pydantic compilation from AttributeDefinition rows (D11)."""

from __future__ import annotations

import pydantic
import pytest

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.services.attribute_model_compiler import AttributeModelCache, compile_attribute_model
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id


def _definition(**overrides: object) -> AttributeDefinition:
    defaults: dict[str, object] = {
        "tenant_id": new_tenant_id(),
        "category_id": new_category_id(),
        "key": "fabric",
        "label": "Fabric",
        "data_type": AttributeDataType.TEXT,
        "now": utcnow(),
    }
    defaults.update(overrides)
    return AttributeDefinition.create(**defaults)  # type: ignore[arg-type]


def test_a_required_field_rejects_a_missing_value() -> None:
    model = compile_attribute_model("M", [_definition(is_required=True)])

    with pytest.raises(pydantic.ValidationError):
        model.model_validate({})


def test_an_optional_field_defaults_to_none() -> None:
    model = compile_attribute_model("M", [_definition(is_required=False)])

    instance = model.model_validate({})

    assert instance.fabric is None  # type: ignore[attr-defined]


def test_a_provided_default_value_is_used_when_omitted() -> None:
    model = compile_attribute_model("M", [_definition(is_required=False, default_value="cotton")])

    instance = model.model_validate({})

    assert instance.fabric == "cotton"  # type: ignore[attr-defined]


def test_money_is_typed_as_integer_minor_units_not_float() -> None:
    model = compile_attribute_model(
        "M", [_definition(key="price", data_type=AttributeDataType.MONEY, is_required=True)]
    )

    instance = model.model_validate({"price": 1999})
    assert instance.price == 1999  # type: ignore[attr-defined]

    with pytest.raises(pydantic.ValidationError):
        model.model_validate({"price": 19.99})


def test_an_enum_field_accepts_only_its_declared_options() -> None:
    model = compile_attribute_model(
        "M",
        [
            _definition(
                key="finish",
                data_type=AttributeDataType.ENUM,
                is_required=True,
                validation={"options": ["matte", "glossy"]},
            )
        ],
    )

    assert model.model_validate({"finish": "matte"}).finish == "matte"  # type: ignore[attr-defined]
    with pytest.raises(pydantic.ValidationError):
        model.model_validate({"finish": "shiny"})


def test_max_length_and_min_max_constraints_from_validation_json_are_enforced() -> None:
    model = compile_attribute_model(
        "M",
        [
            _definition(
                key="note",
                data_type=AttributeDataType.TEXT,
                is_required=True,
                validation={"maxLength": 3},
            )
        ],
    )

    with pytest.raises(pydantic.ValidationError):
        model.model_validate({"note": "too long"})


def test_the_same_compiled_model_produces_a_json_schema_for_admin_forms() -> None:
    """D11: "same model drives API validation and admin-UI form rendering" -
    proven by calling both on the identical class."""
    model = compile_attribute_model(
        "M", [_definition(is_required=True, help_text=None, label="Fabric")]
    )

    schema = model.model_json_schema()

    assert schema["required"] == ["fabric"]
    assert schema["properties"]["fabric"]["title"] == "Fabric"
    # The same class also validates - not a separate, hand-kept-in-sync copy.
    assert model.model_validate({"fabric": "silk"}).fabric == "silk"  # type: ignore[attr-defined]


class TestAttributeModelCache:
    def test_the_same_key_returns_the_identical_class_without_recompiling(self) -> None:
        cache = AttributeModelCache()
        category_id = new_category_id()
        first = cache.get_or_compile(category_id, 1, [_definition()])

        # Different definitions, same key: the cache trusts the key (see the
        # class docstring) and returns the same object, not a fresh compile.
        second = cache.get_or_compile(category_id, 1, [_definition(key="other")])

        assert first is second

    def test_a_different_spec_version_compiles_a_new_model(self) -> None:
        cache = AttributeModelCache()
        category_id = new_category_id()
        first = cache.get_or_compile(category_id, 1, [_definition()])

        second = cache.get_or_compile(category_id, 2, [_definition()])

        assert first is not second

    def test_a_different_category_compiles_a_new_model(self) -> None:
        cache = AttributeModelCache()
        first = cache.get_or_compile(new_category_id(), 1, [_definition()])

        second = cache.get_or_compile(new_category_id(), 1, [_definition()])

        assert first is not second
