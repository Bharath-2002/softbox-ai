from __future__ import annotations

import pytest

from app.entities.variant_axis import VariantAxis, VariantAxisValue
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_category_id, new_tenant_id, new_variant_axis_id


def test_a_new_axis_has_no_version_stamps_yet() -> None:
    axis = VariantAxis.create(
        new_tenant_id(),
        new_category_id(),
        key="colour",
        label="Colour",
        affects_imagery=True,
        now=utcnow(),
    )

    assert axis.introduced_in_version is None
    assert axis.retired_in_version is None


def test_affects_imagery_is_carried_through_as_given() -> None:
    size_axis = VariantAxis.create(
        new_tenant_id(),
        new_category_id(),
        key="size",
        label="Size",
        affects_imagery=False,
        now=utcnow(),
    )
    colour_axis = VariantAxis.create(
        new_tenant_id(),
        new_category_id(),
        key="colour",
        label="Colour",
        affects_imagery=True,
        now=utcnow(),
    )

    assert size_axis.affects_imagery is False
    assert colour_axis.affects_imagery is True


def test_an_axis_key_that_is_not_a_safe_identifier_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Variant axis key"):
        VariantAxis.create(
            new_tenant_id(),
            new_category_id(),
            key="Colour Family",
            label="Colour",
            affects_imagery=True,
            now=utcnow(),
        )


def test_a_value_carries_free_form_metadata() -> None:
    value = VariantAxisValue.create(
        new_tenant_id(),
        new_variant_axis_id(),
        value="maroon",
        label="Maroon",
        now=utcnow(),
        metadata={"hex": "#800000"},
    )

    assert value.metadata == {"hex": "#800000"}


def test_a_value_defaults_to_no_metadata() -> None:
    value = VariantAxisValue.create(
        new_tenant_id(), new_variant_axis_id(), value="maroon", label="Maroon", now=utcnow()
    )

    assert value.metadata == {}
