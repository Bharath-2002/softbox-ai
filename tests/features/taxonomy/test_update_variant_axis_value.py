from __future__ import annotations

import pytest

from app.entities.variant_axis import VariantAxisValue
from app.features.taxonomy.update_variant_axis_value import UpdateVariantAxisValue
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_tenant_id,
    new_user_id,
    new_variant_axis_id,
    new_variant_axis_value_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_update_replaces_label_and_metadata_and_keeps_the_value() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = UpdateVariantAxisValue(uow_factory, FakeClock(utcnow()))
    tenant_id = new_tenant_id()
    axis_value = VariantAxisValue.create(
        tenant_id, new_variant_axis_id(), value="maroon", label="Maroon", now=utcnow()
    )
    await uow_factory.variant_axis_values.add(axis_value)

    updated = await use_case(
        tenant_id=tenant_id,
        value_id=axis_value.id,
        label="Deep Maroon",
        metadata={"hex": "#5c1a1a"},
        actor_user_id=new_user_id(),
    )

    assert updated.label == "Deep Maroon"
    assert updated.metadata == {"hex": "#5c1a1a"}
    assert updated.value == "maroon"


async def test_updating_an_unknown_value_is_not_found() -> None:
    use_case = UpdateVariantAxisValue(FakeUnitOfWorkFactory(), FakeClock(utcnow()))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            value_id=new_variant_axis_value_id(),
            label="X",
            metadata={},
            actor_user_id=new_user_id(),
        )
