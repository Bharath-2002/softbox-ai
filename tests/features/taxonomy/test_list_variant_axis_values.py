from __future__ import annotations

from app.entities.variant_axis import VariantAxisValue
from app.features.taxonomy.list_variant_axis_values import ListVariantAxisValues
from app.shared.clock import utcnow
from app.shared.ids import new_tenant_id, new_variant_axis_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_lists_only_values_for_the_given_axis() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListVariantAxisValues(uow_factory)
    tenant_id = new_tenant_id()
    axis_id = new_variant_axis_id()
    other_axis_id = new_variant_axis_id()
    own = VariantAxisValue.create(tenant_id, axis_id, value="maroon", label="Maroon", now=utcnow())
    other = VariantAxisValue.create(
        tenant_id, other_axis_id, value="s", label="Small", now=utcnow()
    )
    await uow_factory.variant_axis_values.add(own)
    await uow_factory.variant_axis_values.add(other)

    listed = await use_case(tenant_id=tenant_id, axis_id=axis_id)

    assert [v.id for v in listed] == [own.id]
