from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.variant_axis import VariantAxis
from app.features.taxonomy.create_variant_axis_value import CreateVariantAxisValue
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id, new_variant_axis_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_creates_a_value_owned_by_the_axis() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = CreateVariantAxisValue(uow_factory, FakeClock(_NOW))
    tenant_id = new_tenant_id()
    axis = VariantAxis.create(
        tenant_id, new_category_id(), key="colour", label="Colour", affects_imagery=True, now=_NOW
    )
    await uow_factory.variant_axes.add(axis)

    value = await use_case(
        tenant_id=tenant_id,
        axis_id=axis.id,
        value="maroon",
        label="Maroon",
        actor_user_id=new_user_id(),
    )

    assert value.axis_id == axis.id
    stored = await uow_factory.variant_axis_values.get(tenant_id, value.id)
    assert stored is not None and stored.value == "maroon"


async def test_creating_on_an_unknown_axis_is_not_found() -> None:
    use_case = CreateVariantAxisValue(FakeUnitOfWorkFactory(), FakeClock(_NOW))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            axis_id=new_variant_axis_id(),
            value="maroon",
            label="Maroon",
            actor_user_id=new_user_id(),
        )
