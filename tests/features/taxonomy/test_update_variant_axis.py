from __future__ import annotations

import pytest

from app.entities.variant_axis import VariantAxis
from app.features.taxonomy.update_variant_axis import UpdateVariantAxis
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id, new_variant_axis_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_update_replaces_editable_fields_and_keeps_the_key() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = UpdateVariantAxis(uow_factory, FakeClock(utcnow()))
    tenant_id = new_tenant_id()
    axis = VariantAxis.create(
        tenant_id,
        new_category_id(),
        key="colour",
        label="Colour",
        affects_imagery=True,
        now=utcnow(),
    )
    await uow_factory.variant_axes.add(axis)

    updated = await use_case(
        tenant_id=tenant_id,
        axis_id=axis.id,
        label="Colour (renamed)",
        affects_imagery=False,
        position=2,
        actor_user_id=new_user_id(),
    )

    assert updated.label == "Colour (renamed)"
    assert updated.affects_imagery is False
    assert updated.key == "colour"


async def test_updating_an_unknown_axis_is_not_found() -> None:
    use_case = UpdateVariantAxis(FakeUnitOfWorkFactory(), FakeClock(utcnow()))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            axis_id=new_variant_axis_id(),
            label="X",
            affects_imagery=True,
            position=0,
            actor_user_id=new_user_id(),
        )
