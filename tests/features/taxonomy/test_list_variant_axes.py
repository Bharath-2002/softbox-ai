from __future__ import annotations

from app.entities.variant_axis import VariantAxis
from app.features.taxonomy.list_variant_axes import ListVariantAxes
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_lists_only_axes_the_category_itself_owns() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListVariantAxes(uow_factory)
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    other_category_id = new_category_id()
    own = VariantAxis.create(
        tenant_id, category_id, key="colour", label="Colour", affects_imagery=True, now=utcnow()
    )
    other = VariantAxis.create(
        tenant_id, other_category_id, key="size", label="Size", affects_imagery=False, now=utcnow()
    )
    await uow_factory.variant_axes.add(own)
    await uow_factory.variant_axes.add(other)

    listed = await use_case(tenant_id=tenant_id, category_id=category_id)

    assert [a.id for a in listed] == [own.id]
